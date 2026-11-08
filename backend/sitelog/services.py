from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from operations.models import SiteReport, Workplace, WorkplaceTeam
from sitelog.models import CrewAttendance, DailyLog
from timesheets.locks import ensure_worker_open
from timesheets.models import Leave, OtherWork
from timesheets.schedule import WorkCalendar, days_between
from timesheets.services import check_day_total
from workforce.models import TeamMembership, Worker
from workforce.services import active_on

LOCKED_MESSAGE = "This day is approved. Reopen it before changing it."


def day_is_approved(workplace, work_date):
    return DailyLog.objects.filter(
        workplace=workplace,
        work_date=work_date,
        status=DailyLog.Status.APPROVED,
    ).exists()


def ensure_day_open(workplace, work_date):
    if work_date is not None and day_is_approved(workplace, work_date):
        raise ValidationError({"work_date": LOCKED_MESSAGE})


def locked_message(log):
    return LOCKED_MESSAGE if log.status == DailyLog.Status.APPROVED else None


def log_for(workplace, work_date):
    try:
        with transaction.atomic():
            return DailyLog.objects.get_or_create(workplace=workplace, work_date=work_date)[0]
    except IntegrityError:
        return DailyLog.objects.get(workplace=workplace, work_date=work_date)


def update_day(workplace, work_date, *, weather=None, notes=None):
    ensure_day_open(workplace, work_date)
    log = log_for(workplace, work_date)
    fields = []
    if weather is not None:
        log.weather = weather.strip()
        fields.append("weather")
    if notes is not None:
        log.notes = notes.strip()
        fields.append("notes")
    if fields:
        log.save(update_fields=[*fields, "updated_at"])
    return log


def approve_day(workplace, work_date, user):
    log = log_for(workplace, work_date)
    with transaction.atomic():
        log = DailyLog.objects.select_for_update().get(pk=log.pk)
        if log.status == DailyLog.Status.APPROVED:
            raise ValidationError("This day is already approved.")
        log.status = DailyLog.Status.APPROVED
        log.approved_by = user
        log.approved_at = timezone.now()
        log.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return log


def reopen_day(workplace, work_date):
    log = DailyLog.objects.filter(workplace=workplace, work_date=work_date).first()
    if log is None or log.status != DailyLog.Status.APPROVED:
        raise ValidationError("This day is not approved.")
    log.status = DailyLog.Status.OPEN
    log.approved_by = None
    log.approved_at = None
    log.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return log


def placements_on(workplace, work_date):
    return workplace.workplace_teams.filter(active_on(work_date)).select_related("team__lead_user")


def available_on(worker, day):
    """Employed that day. An inactive worker counts only up to a recorded last working day."""
    return worker.employed_on(day) and (worker.status == Worker.Status.ACTIVE or worker.left_on is not None)


def default_hours(calendar, worker, day):
    expected = calendar.expected_hours(worker.pk, day)
    return expected if expected > 0 else calendar.norm(worker.pk, day)


def set_attendance(*, workplace, work_date, team, workers, hours=None):
    """Replace who was on site with `team` on this project day.

    `hours` maps worker id to hours. New rows without hours get the worker's expected hours; saved rows
    keep theirs unless new hours are sent, so an older client can't reset them."""
    hours = hours or {}
    ensure_day_open(workplace, work_date)
    if work_date > workplace.company.today():
        raise ValidationError({"date": "Crew can only be recorded up to today."})
    if not placements_on(workplace, work_date).filter(team=team).exists():
        raise ValidationError({"team": "That team is not on this project on that date."})
    for worker in workers:
        if worker.company_id != workplace.company_id:
            raise ValidationError({"worker_ids": "Workers must belong to this company."})
    elsewhere = (
        CrewAttendance.objects.filter(workplace=workplace, work_date=work_date, worker__in=workers)
        .exclude(team=team)
        .select_related("worker", "team")
        .first()
    )
    if elsewhere is not None:
        raise ValidationError(
            {"worker_ids": f"{elsewhere.worker.name} is already on {elsewhere.team.name}'s crew that day."}
        )
    day = CrewAttendance.objects.filter(workplace=workplace, work_date=work_date, team=team)
    wanted = {worker.pk for worker in workers}
    with transaction.atomic():
        saved = {row.worker_id: row for row in day.select_for_update().select_related("worker")}
        added = [worker for worker in workers if worker.pk not in saved]
        removed = [row for worker_id, row in saved.items() if worker_id not in wanted]
        changed = [
            row
            for worker_id, row in saved.items()
            if worker_id in wanted and worker_id in hours and hours[worker_id] != row.hours
        ]
        touched = [*added, *(row.worker for row in removed), *(row.worker for row in changed)]
        list(Worker.objects.select_for_update().filter(pk__in=[worker.pk for worker in touched]).order_by("pk"))
        for worker in touched:
            ensure_worker_open(worker, work_date, work_date)
        for worker in added:
            if not available_on(worker, work_date):
                raise ValidationError({"worker_ids": f"{worker.name} wasn't employed on {work_date}."})
        calendar = WorkCalendar(workplace.company, added, work_date, work_date) if added else None
        new_rows = []
        for worker in added:
            value = hours.get(worker.pk) or default_hours(calendar, worker, work_date)
            check_day_total(worker, work_date, value)
            new_rows.append(CrewAttendance(workplace=workplace, work_date=work_date, team=team, worker=worker, hours=value))
        for row in changed:
            row.hours = hours[row.worker_id]
            check_day_total(row.worker, work_date, row.hours, skip_attendance=[row.pk])
        if removed:
            CrewAttendance.objects.filter(pk__in=[row.pk for row in removed]).delete()
        CrewAttendance.objects.bulk_create(new_rows)
        if changed:
            CrewAttendance.objects.bulk_update(changed, ["hours"])
    return day.select_related("worker")


def team_on(worker, day):
    """The team the worker was in on `day`, from their membership history (not the cached current team)."""
    stretch = TeamMembership.objects.filter(worker=worker).filter(active_on(day)).select_related("team").first()
    return stretch.team if stretch else None


def crew_of(workplace, work_date, team):
    return list(
        Worker.objects.filter(attendance__workplace=workplace, attendance__work_date=work_date, attendance__team=team)
    )


def set_worker_hours(*, worker, work_date, hours, workplace=None):
    """One worker's site hours for a day, from the timesheet. 0 takes them off that project's crew.

    Without a project: the day's single crew row, or the one project the worker's team was placed on."""
    rows = list(CrewAttendance.objects.filter(worker=worker, work_date=work_date).select_related("workplace", "team"))
    if workplace is not None:
        row = next((row for row in rows if row.workplace_id == workplace.pk), None)
    elif len(rows) > 1:
        raise ValidationError({"hours": "This day has hours on more than one project. Change them in the day panel."})
    else:
        row = rows[0] if rows else None
    if row is not None:
        crew = crew_of(row.workplace, work_date, row.team)
        if hours == 0:
            crew = [member for member in crew if member.pk != worker.pk]
            return set_attendance(workplace=row.workplace, work_date=work_date, team=row.team, workers=crew)
        return set_attendance(
            workplace=row.workplace, work_date=work_date, team=row.team, workers=crew, hours={worker.pk: hours}
        )
    if hours == 0:
        return None
    team = team_on(worker, work_date)
    if team is None:
        raise ValidationError({"hours": f"{worker.name} wasn't in a team on {work_date}. Record other work instead."})
    placements = WorkplaceTeam.objects.filter(team=team).filter(active_on(work_date)).select_related("workplace")
    if workplace is not None:
        placements = placements.filter(workplace=workplace)
    placements = list(placements)
    if not placements:
        raise ValidationError({"workplace": f"{team.name} wasn't on a project on {work_date}. Record other work instead."})
    if len(placements) > 1:
        raise ValidationError({"workplace": "Pick the project in the day panel."})
    target = placements[0].workplace
    crew = crew_of(target, work_date, team)
    return set_attendance(
        workplace=target, work_date=work_date, team=team, workers=[*crew, worker], hours={worker.pk: hours}
    )


def first_message(error):
    detail = error.detail
    while isinstance(detail, (list, dict)):
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail)


def fill_from_schedule(worker, start, end):
    """Record the scheduled hours on the team's project for past days that have nothing yet.

    Skips days off, holidays, days that already have hours, and days the team wasn't on exactly one project."""
    end = min(end, worker.company.today())
    calendar = WorkCalendar(worker.company, [worker], start, end)
    recorded = set(
        CrewAttendance.objects.filter(worker=worker, work_date__range=(start, end)).values_list("work_date", flat=True)
    ) | set(OtherWork.objects.filter(worker=worker, work_date__range=(start, end)).values_list("work_date", flat=True))
    leaves = list(
        Leave.objects.filter(worker=worker, status=Leave.Status.APPROVED, start_date__lte=end, end_date__gte=start)
    )
    filled, skipped = 0, []
    for day in days_between(start, end):
        expected = calendar.expected_hours(worker.pk, day)
        if expected <= 0 or day in recorded:
            continue
        leave = next((leave for leave in leaves if leave.covers(day)), None)
        if leave is not None and not leave.half_day:
            continue
        try:
            with transaction.atomic():
                set_worker_hours(worker=worker, work_date=day, hours=expected / 2 if leave else expected)
            filled += 1
        except ValidationError as error:
            skipped.append({"date": str(day), "reason": first_message(error)})
    return {"filled": filled, "skipped": skipped}


def missing_reports(workplaces, work_date):
    """Placements on active projects that have no report from that team on work_date."""
    placements = (
        WorkplaceTeam.objects.filter(workplace__in=workplaces, workplace__status=Workplace.Status.ACTIVE)
        .filter(active_on(work_date))
        .select_related("workplace", "team__lead_user")
        .order_by("workplace__name", "team__number")
    )
    reported = set(
        SiteReport.objects.filter(workplace__in=workplaces, work_date=work_date).values_list("workplace_id", "team_id")
    )
    return [row for row in placements if (row.workplace_id, row.team_id) not in reported]
