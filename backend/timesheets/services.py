from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from sitelog.models import CrewAttendance
from timesheets.locks import ensure_company_open, ensure_worker_open
from timesheets.models import WEEKDAYS, Holiday, Leave, OtherWork, ScheduleAssignment, WorkSchedule, WorkScheduleVersion
from timesheets.schedule import WorkCalendar, covers
from workforce.models import Worker

MAX_DAY_HOURS = Decimal("24")

DEFAULT_SCHEDULE_NAME = "Standard"


def create_default_schedule(company):
    """Mon–Fri 8 h for everyone, unless the company already has a default."""
    schedule, _ = WorkSchedule.objects.get_or_create(company=company, name=DEFAULT_SCHEDULE_NAME)
    if not schedule.versions.exists():
        WorkScheduleVersion.objects.create(schedule=schedule, **{day: Decimal("8") for day in WEEKDAYS[:5]})
    if not ScheduleAssignment.objects.filter(company=company, worker__isnull=True).exists():
        ScheduleAssignment.objects.create(company=company, schedule=schedule)
    return schedule


def check_hours(hours):
    if not any(hours.get(day) for day in WEEKDAYS):
        raise ValidationError({"hours": "Give at least one day some hours."})


def create_schedule(company, name, hours, day_hours):
    check_hours(hours)
    with transaction.atomic():
        schedule = WorkSchedule.objects.create(company=company, name=name)
        WorkScheduleVersion.objects.create(schedule=schedule, day_hours=day_hours, **hours)
    return schedule


def change_schedule_hours(schedule, valid_from, hours, day_hours):
    """New hours from valid_from on. Days before it keep the hours they had."""
    check_hours(hours)
    ensure_company_open(schedule.company, valid_from)
    version, _ = WorkScheduleVersion.objects.update_or_create(
        schedule=schedule,
        valid_from=valid_from,
        defaults={**hours, "day_hours": day_hours},
    )
    return version


def assign_schedule(company, schedule, workers, start_date):
    """Put `workers` on `schedule` from start_date. workers=None changes the company-wide default;
    schedule=None sends workers back to the company default."""
    if schedule is not None and schedule.company_id != company.id:
        raise ValidationError({"schedule": "Schedule must belong to this company."})
    if workers is None and schedule is None:
        raise ValidationError({"schedule": "Choose the schedule everyone follows."})
    if workers is None:
        ensure_company_open(company, start_date)
    else:
        for worker in workers:
            ensure_worker_open(worker, start_date)
    with transaction.atomic():
        for worker in [None] if workers is None else workers:
            _switch_schedule(company, worker, schedule, start_date)


def _switch_schedule(company, worker, schedule, start_date):
    label = worker.name if worker else "Everyone"
    rows = ScheduleAssignment.objects.select_for_update().select_related("schedule").filter(company=company, worker=worker)
    current = rows.filter(end_date__isnull=True).first()
    if current is not None and current.schedule_id == getattr(schedule, "id", None):
        return
    if current is None and schedule is None:
        return
    if current is not None:
        if current.start_date is not None and start_date < current.start_date:
            raise ValidationError(
                {"start_date": f"{label} has followed {current.schedule.name} since {current.start_date}. Choose that day or later."}
            )
        if current.start_date == start_date:
            current.delete()
        else:
            current.end_date = start_date - timedelta(days=1)
            current.save(update_fields=["end_date"])
    else:
        last = rows.filter(end_date__isnull=False).order_by("-end_date").first()
        if last is not None and start_date <= last.end_date:
            raise ValidationError(
                {"start_date": f"{label} followed {last.schedule.name} until {last.end_date}. Choose a later day."}
            )
    if schedule is not None:
        ScheduleAssignment.objects.create(company=company, worker=worker, schedule=schedule, start_date=start_date)


def schedule_for(worker, day):
    """The schedule a worker follows on `day`, and whether it is their own or the company default."""
    calendar = WorkCalendar(worker.company, [worker], day, day)
    version = calendar.version_on(worker.pk, day)
    if version is None:
        return None
    return {
        "schedule": version.schedule_id,
        "name": version.schedule.name,
        "own": any(covers(row, day) for row in calendar.worker_rows.get(worker.pk, ())),
        "hours": {name: str(getattr(version, name)) for name in WEEKDAYS},
        "day_hours": str(version.day_hours),
    }


def copy_holidays(company, from_year, to_year):
    """Copy holidays to another year on the same dates. Moveable feasts need fixing by hand.
    Days inside approved periods are skipped."""
    created = 0
    for holiday in Holiday.objects.filter(company=company, date__year=from_year):
        try:
            day = holiday.date.replace(year=to_year)
            ensure_company_open(company, day, day)
        except (ValueError, ValidationError):
            continue
        created += Holiday.objects.get_or_create(company=company, date=day, defaults={"name": holiday.name})[1]
    return created


def hours_on_day(worker, day, skip_attendance=()):
    """Hours already recorded for a worker on a day, across projects and other work."""
    site = (
        CrewAttendance.objects.filter(worker=worker, work_date=day)
        .exclude(pk__in=skip_attendance)
        .aggregate(total=Sum("hours"))["total"]
    )
    other = OtherWork.objects.filter(worker=worker, work_date=day).aggregate(total=Sum("hours"))["total"]
    return (site or Decimal("0")) + (other or Decimal("0"))


def check_day_total(worker, day, adding, skip_attendance=()):
    if hours_on_day(worker, day, skip_attendance) + adding > MAX_DAY_HOURS:
        raise ValidationError({"hours": f"That would give {worker.name} more than 24 hours on {day}."})


def check_can_record(worker, day):
    if day > worker.company.today():
        raise ValidationError({"work_date": "Hours can only be recorded up to today."})
    if not worker.employed_on(day):
        raise ValidationError({"work_date": f"{worker.name} wasn't employed on {day}."})


def save_other_work(entry, user):
    """Record work done away from projects."""
    worker = entry.worker
    with transaction.atomic():
        Worker.objects.select_for_update().get(pk=worker.pk)
        ensure_worker_open(worker, entry.work_date, entry.work_date)
        check_can_record(worker, entry.work_date)
        check_day_total(worker, entry.work_date, entry.hours)
        if OtherWork.objects.filter(worker=worker, work_date=entry.work_date, kind=entry.kind).exists():
            raise ValidationError({"kind": "This kind of work is already recorded that day. Change its hours instead."})
        entry.created_by = user
        entry.note = entry.note.strip()
        entry.save()
    return entry


def delete_other_work(entry):
    ensure_worker_open(entry.worker, entry.work_date, entry.work_date)
    entry.delete()


def _changed_days(old, new, open_start):
    """The days whose employment changes when a hire or leaving date moves from old to new.
    Returns (start, end); None means open-ended on that side."""
    one = timedelta(days=1)
    if open_start:  # hired_on: empty means "since always"
        if old is None or new is None:
            return None, (old or new) - one
        return min(old, new), max(old, new) - one
    if old is None or new is None:  # left_on: empty means "still employed"
        return (old or new) + one, None
    return min(old, new) + one, max(old, new)


def check_employment_change(worker, hired_on, left_on):
    """Moving the hire or leaving date may not strand recorded days or touch approved periods."""
    if hired_on != worker.hired_on:
        ensure_worker_open(worker, *_changed_days(worker.hired_on, hired_on, open_start=True))
    if left_on != worker.left_on:
        ensure_worker_open(worker, *_changed_days(worker.left_on, left_on, open_start=False))
    active = (Leave.Status.REQUESTED, Leave.Status.APPROVED)
    if hired_on is not None:
        early = [
            CrewAttendance.objects.filter(worker=worker, work_date__lt=hired_on).order_by("work_date").first(),
            OtherWork.objects.filter(worker=worker, work_date__lt=hired_on).order_by("work_date").first(),
        ]
        days = [row.work_date for row in early if row] + list(
            Leave.objects.filter(worker=worker, status__in=active, start_date__lt=hired_on).values_list("start_date", flat=True)[:1]
        )
        if days:
            raise ValidationError({"hired_on": f"{worker.name} has a day recorded on {min(days)}, before that."})
    if left_on is not None:
        late = [
            CrewAttendance.objects.filter(worker=worker, work_date__gt=left_on).order_by("-work_date").first(),
            OtherWork.objects.filter(worker=worker, work_date__gt=left_on).order_by("-work_date").first(),
        ]
        days = [row.work_date for row in late if row] + list(
            Leave.objects.filter(worker=worker, status__in=active, end_date__gt=left_on).values_list("end_date", flat=True)[:1]
        )
        if days:
            raise ValidationError({"left_on": f"{worker.name} has a day recorded on {max(days)}, after that."})
