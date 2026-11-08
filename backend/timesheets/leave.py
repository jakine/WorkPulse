"""Days off: requests, decisions, day counts and yearly balances.

The number of days is never stored. It is counted from the worker's expected hours, so weekends,
holidays and days outside employment never count.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from timesheets.locks import ensure_worker_open
from timesheets.models import Leave, LeaveType
from timesheets.schedule import WorkCalendar, covers, days_between
from workforce.models import TeamMembership, Worker

DEFAULT_LEAVE_TYPES = (
    # name, code, paid, uses allowance
    ("Vacation", "V", True, True),
    ("Sick", "S", True, False),
    ("Unpaid leave", "U", False, False),
    ("Absent (no notice)", "A", False, False),
    ("Other paid", "P", True, False),
)
ACTIVE = (Leave.Status.REQUESTED, Leave.Status.APPROVED)
ZERO = Decimal("0")


def create_default_leave_types(company):
    return [
        LeaveType.objects.get_or_create(
            company=company,
            name=name,
            defaults={"code": code, "paid": paid, "uses_allowance": allowance, "position": position},
        )[0]
        for position, (name, code, paid, allowance) in enumerate(DEFAULT_LEAVE_TYPES)
    ]


def day_value(leave):
    return Decimal("0.5") if leave.half_day else Decimal("1")


def leave_days(calendar, leave, start=None, end=None):
    """Working days the day off covers, optionally only those between start and end."""
    first = max(leave.start_date, start) if start else leave.start_date
    last = min(leave.end_date, end) if end else leave.end_date
    value = day_value(leave)
    return sum(
        (value for day in days_between(first, last) if calendar.expected_hours(leave.worker_id, day) > 0),
        ZERO,
    )


def allowance_for(worker, company):
    return worker.leave_allowance if worker.leave_allowance is not None else company.leave_days_per_year


def check_leave(leave):
    worker = leave.worker
    if worker.company_id != leave.company_id or leave.leave_type.company_id != leave.company_id:
        raise ValidationError("Worker and type must belong to this company.")
    if leave.end_date < leave.start_date:
        raise ValidationError({"end_date": "The last day can't be before the first."})
    if leave.half_day and leave.start_date != leave.end_date:
        raise ValidationError({"half_day": "A half day off is a single day."})
    if (worker.hired_on and leave.start_date < worker.hired_on) or (worker.left_on and leave.end_date > worker.left_on):
        raise ValidationError({"start_date": f"{worker.name} isn't employed on all of those days."})
    clash = (
        Leave.objects.filter(
            worker=worker,
            status__in=ACTIVE,
            start_date__lte=leave.end_date,
            end_date__gte=leave.start_date,
        )
        .exclude(pk=leave.pk)
        .select_related("leave_type")
        .first()
    )
    if clash is not None:
        raise ValidationError(
            {"start_date": f"{worker.name} already has {clash.leave_type.name.lower()} from {clash.start_date} to {clash.end_date}."}
        )
    calendar = WorkCalendar(leave.company, [worker], leave.start_date, leave.end_date)
    if leave_days(calendar, leave) == 0:
        raise ValidationError({"start_date": "There are no working days in that range."})


def request_leave(*, company, worker, leave_type, start_date, end_date, half_day=False, note="", user, approve=False):
    if leave_type.archived:
        raise ValidationError({"leave_type": "That type is no longer used."})
    leave = Leave(
        company=company,
        worker=worker,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        half_day=half_day,
        note=note.strip(),
        requested_by=user,
    )
    with transaction.atomic():
        Worker.objects.select_for_update().get(pk=worker.pk)
        ensure_worker_open(worker, start_date, end_date)
        check_leave(leave)
        if approve:
            leave.status = Leave.Status.APPROVED
            leave.decided_by = user
            leave.decided_at = timezone.now()
        leave.save()
    return leave


def decide_leave(leave, user, approve):
    if leave.status != Leave.Status.REQUESTED:
        raise ValidationError("This day off has already been decided.")
    with transaction.atomic():
        Worker.objects.select_for_update().get(pk=leave.worker_id)
        if approve:
            ensure_worker_open(leave.worker, leave.start_date, leave.end_date)
            check_leave(leave)
        leave.status = Leave.Status.APPROVED if approve else Leave.Status.REJECTED
        leave.decided_by = user
        leave.decided_at = timezone.now()
        leave.save(update_fields=["status", "decided_by", "decided_at"])
    return leave


def cancel_leave(leave, user):
    if leave.status not in ACTIVE:
        raise ValidationError("This day off is already closed.")
    if leave.status == Leave.Status.APPROVED:
        ensure_worker_open(leave.worker, leave.start_date, leave.end_date)
    leave.status = Leave.Status.CANCELLED
    leave.decided_by = user
    leave.decided_at = timezone.now()
    leave.save(update_fields=["status", "decided_by", "decided_at"])
    return leave


def leave_balances(company, workers, year, today):
    """Allowance, used (up to today), planned (later this year), waiting and left, per worker.

    Days off that cross New Year count in the year each day falls in."""
    workers = list(workers)
    start, end = date(year, 1, 1), date(year, 12, 31)
    calendar = WorkCalendar(company, workers, start, end)
    rows = {
        worker.pk: {
            "worker": worker.pk,
            "name": worker.name,
            "allowance": allowance_for(worker, company),
            "used": ZERO,
            "planned": ZERO,
            "waiting": ZERO,
            "by_type": defaultdict(lambda: ZERO),
        }
        for worker in workers
    }
    leaves = Leave.objects.filter(
        worker__in=workers,
        status__in=ACTIVE,
        start_date__lte=end,
        end_date__gte=start,
    ).select_related("leave_type")
    for leave in leaves:
        row = rows[leave.worker_id]
        for day in days_between(max(leave.start_date, start), min(leave.end_date, end)):
            if calendar.expected_hours(leave.worker_id, day) <= 0:
                continue
            value = day_value(leave)
            if leave.status == Leave.Status.REQUESTED:
                if leave.leave_type.uses_allowance:
                    row["waiting"] += value
                continue
            row["by_type"][leave.leave_type.code] += value
            if leave.leave_type.uses_allowance:
                row["used" if day <= today else "planned"] += value
    result = []
    for row in rows.values():
        left = row["allowance"] - row["used"] - row["planned"]
        result.append(
            {
                **{key: row[key] for key in ("worker", "name")},
                **{key: str(row[key]) for key in ("allowance", "used", "planned", "waiting")},
                "left": str(left),
                "by_type": {code: str(value) for code, value in row["by_type"].items()},
            }
        )
    return sorted(result, key=lambda row: row["name"])


def approved_off(workers, day):
    """Approved days off covering `day`, by worker id."""
    leaves = Leave.objects.filter(
        worker__in=workers,
        status=Leave.Status.APPROVED,
        start_date__lte=day,
        end_date__gte=day,
    ).select_related("leave_type")
    return {leave.worker_id: leave for leave in leaves}


def off_by_team(company, start, end):
    """How many members of each team are on an approved day off, per day: {team_id: {"YYYY-MM-DD": count}}."""
    leaves = list(
        Leave.objects.filter(
            company=company,
            status=Leave.Status.APPROVED,
            start_date__lte=end,
            end_date__gte=start,
        ).select_related("worker")
    )
    workers = {leave.worker_id: leave.worker for leave in leaves}
    calendar = WorkCalendar(company, workers.values(), start, end)
    stretches = defaultdict(list)
    for stretch in TeamMembership.objects.filter(worker_id__in=list(workers)):
        stretches[stretch.worker_id].append(stretch)
    counts = defaultdict(lambda: defaultdict(int))
    for leave in leaves:
        for day in days_between(max(start, leave.start_date), min(end, leave.end_date)):
            if calendar.expected_hours(leave.worker_id, day) <= 0:
                continue
            team = next((row.team_id for row in stretches[leave.worker_id] if covers(row, day)), None)
            if team is not None:
                counts[team][str(day)] += 1
    return {team: dict(days) for team, days in counts.items()}
