"""Pay groups and their periods: which cycle a worker is settled on, and approving a cycle's hours."""

from collections import defaultdict
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from timesheets.locks import ensure_group_open, ensure_worker_open
from timesheets.models import Leave, PayGroup, PayGroupAssignment, TimesheetPeriod
from timesheets.schedule import month_end, month_start, week_start
from workforce.models import Worker
from workforce.services import overlapping

DEFAULT_PAY_GROUP_NAME = "Monthly"
TWO_WEEK_ANCHOR = date(2024, 1, 1)  # a Monday, used when a two-week group has no anchor of its own


def default_pay_group(company):
    group = PayGroup.objects.filter(company=company, is_default=True).first()
    if group is None:
        group = PayGroup.objects.create(
            company=company,
            name=DEFAULT_PAY_GROUP_NAME,
            cycle=PayGroup.Cycle.MONTHLY,
            is_default=True,
        )
    return group


def join_default_pay_group(worker):
    if not PayGroupAssignment.objects.filter(worker=worker).exists():
        PayGroupAssignment.objects.create(
            company_id=worker.company_id,
            worker=worker,
            pay_group=default_pay_group(worker.company),
            start_date=worker.hired_on,
        )


def cycle_bounds(group, day):
    if group.cycle == PayGroup.Cycle.WEEKLY:
        start = week_start(day)
        return start, start + timedelta(days=6)
    if group.cycle == PayGroup.Cycle.TWO_WEEKS:
        anchor = week_start(group.anchor_date or TWO_WEEK_ANCHOR)
        start = day - timedelta(days=(day - anchor).days % 14)
        return start, start + timedelta(days=13)
    return month_start(day), month_end(day)


def period_bounds(group, day):
    """The group's period around `day`. Saved periods win, so a cycle change starts after the last one."""
    saved = group.periods.filter(start_date__lte=day, end_date__gte=day).first()
    if saved is not None:
        return saved.start_date, saved.end_date
    start, end = cycle_bounds(group, day)
    before = group.periods.filter(end_date__lt=day, end_date__gte=start).order_by("-end_date").first()
    if before is not None:
        start = before.end_date + timedelta(days=1)
    after = group.periods.filter(start_date__gt=day, start_date__lte=end).order_by("start_date").first()
    if after is not None:
        end = after.start_date - timedelta(days=1)
    return start, end


def group_spans(group, start, end):
    """{worker: [(first, last), ...]}: the days of start..end each worker spent in the group."""
    rows = PayGroupAssignment.objects.filter(overlapping(start, end), pay_group=group).select_related("worker")
    spans = defaultdict(list)
    for row in rows:
        spans[row.worker].append((max(start, row.start_date or start), min(end, row.end_date or end)))
    return spans


def move_to_pay_group(worker, group, start_date):
    """Settle the worker on another group's cycle from start_date. Approved periods are never touched."""
    if group.company_id != worker.company_id:
        raise ValidationError({"pay_group": "Pay group must belong to this company."})
    ensure_worker_open(worker, start_date)
    ensure_group_open(group, start_date)
    with transaction.atomic():
        Worker.objects.select_for_update().get(pk=worker.pk)
        rows = PayGroupAssignment.objects.filter(worker=worker).select_related("pay_group")
        current = rows.filter(end_date__isnull=True).first()
        if current is not None and current.pay_group_id == group.pk:
            return current
        if current is not None:
            if current.start_date is not None and start_date < current.start_date:
                raise ValidationError(
                    {"start_date": f"{worker.name} has been in {current.pay_group.name} since {current.start_date}. Choose that day or later."}
                )
            if current.start_date == start_date:
                current.delete()
            else:
                current.end_date = start_date - timedelta(days=1)
                current.save(update_fields=["end_date"])
        return PayGroupAssignment.objects.create(
            company_id=worker.company_id, worker=worker, pay_group=group, start_date=start_date
        )


def approve_period(group, start, end, user):
    if (start, end) != period_bounds(group, start):
        raise ValidationError("That isn't one of this group's periods.")
    if end >= group.company.today():
        raise ValidationError("A period can be approved once it is over.")
    workers = list(group_spans(group, start, end))
    waiting = Leave.objects.filter(
        worker__in=workers,
        status=Leave.Status.REQUESTED,
        start_date__lte=end,
        end_date__gte=start,
    ).count()
    if waiting:
        raise ValidationError(
            f"{waiting} day-off request{'s' if waiting != 1 else ''} in this period "
            f"{'are' if waiting != 1 else 'is'} still waiting. Approve or reject first."
        )
    with transaction.atomic():
        period, _ = TimesheetPeriod.objects.select_for_update().get_or_create(
            pay_group=group,
            start_date=start,
            defaults={"company": group.company, "end_date": end},
        )
        if period.status == TimesheetPeriod.Status.APPROVED:
            raise ValidationError("This period is already approved.")
        period.end_date = end
        period.status = TimesheetPeriod.Status.APPROVED
        period.approved_by = user
        period.approved_at = timezone.now()
        period.save(update_fields=["end_date", "status", "approved_by", "approved_at"])
    return period


def reopen_period(period):
    if period.status != TimesheetPeriod.Status.APPROVED:
        raise ValidationError("This period isn't approved.")
    pay_run = getattr(period, "pay_run", None)
    if pay_run is not None and pay_run.status == "approved":
        raise ValidationError("Pay for this period is approved. The owner must reopen pay first.")
    period.status = TimesheetPeriod.Status.OPEN
    period.approved_by = None
    period.approved_at = None
    period.save(update_fields=["status", "approved_by", "approved_at"])
    return period


def has_approved_periods(company):
    return TimesheetPeriod.objects.filter(company=company, status=TimesheetPeriod.Status.APPROVED).exists()


def pay_group_for(worker):
    """The worker's current pay group, and since when."""
    row = PayGroupAssignment.objects.filter(worker=worker, end_date__isnull=True).select_related("pay_group").first()
    if row is None:
        return None
    return {"id": row.pay_group_id, "name": row.pay_group.name, "cycle": row.pay_group.cycle, "since": row.start_date}


def last_finished_periods(company):
    """For each group, the most recent period that is over, and whether its hours are approved."""
    today = company.today()
    result = []
    for group in PayGroup.objects.filter(company=company):
        current_start, _ = period_bounds(group, today)
        start, end = period_bounds(group, current_start - timedelta(days=1))
        saved = group.periods.filter(start_date=start).first()
        result.append(
            {
                "pay_group": group.pk,
                "name": group.name,
                "start": str(start),
                "end": str(end),
                "status": saved.status if saved else TimesheetPeriod.Status.OPEN,
            }
        )
    return result
