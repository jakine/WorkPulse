from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from operations.models import SiteReport, Workplace, WorkplaceTeam
from sitelog.models import CrewAttendance, DailyLog
from workforce.models import Worker
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


def set_attendance(*, workplace, work_date, team, workers):
    """Replace who was on site with `team` on this project day."""
    ensure_day_open(workplace, work_date)
    if not placements_on(workplace, work_date).filter(team=team).exists():
        raise ValidationError({"team": "That team is not on this project on that date."})
    for worker in workers:
        if worker.company_id != workplace.company_id:
            raise ValidationError({"worker_ids": "Workers must belong to this company."})
        if worker.status != Worker.Status.ACTIVE:
            raise ValidationError({"worker_ids": f"{worker.name} is marked inactive."})
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
    with transaction.atomic():
        day.exclude(worker__in=workers).delete()
        recorded = set(day.values_list("worker_id", flat=True))
        CrewAttendance.objects.bulk_create(
            CrewAttendance(workplace=workplace, work_date=work_date, team=team, worker=worker)
            for worker in workers
            if worker.pk not in recorded
        )
    return day.select_related("worker")


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
