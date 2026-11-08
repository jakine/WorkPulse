"""Approved periods freeze everything inside them.

Every write that can change past hours, days off or expected hours asks here first. end=None means
"from start on", for changes such as a new schedule that last until further notice.
"""

from datetime import date

from rest_framework.exceptions import ValidationError

from timesheets.models import PayGroupAssignment, TimesheetPeriod


def locked_message(period):
    return f"Hours for {period.label()} are approved. Reopen that period first."


def _approved(queryset, start, end):
    queryset = queryset.filter(status=TimesheetPeriod.Status.APPROVED, end_date__gte=start or date.min)
    if end is not None:
        queryset = queryset.filter(start_date__lte=end)
    return queryset.select_related("pay_group").order_by("start_date")


def locked_period_for(worker, start, end=None):
    """The first approved period that holds the worker on a day between start and end."""
    start = start or date.min
    for stretch in PayGroupAssignment.objects.filter(worker=worker):
        first = max(start, stretch.start_date) if stretch.start_date else start
        if end is None:
            last = stretch.end_date
        else:
            last = min(end, stretch.end_date) if stretch.end_date else end
        if last is not None and last < first:
            continue
        period = _approved(TimesheetPeriod.objects.filter(pay_group_id=stretch.pay_group_id), first, last).first()
        if period is not None:
            return period
    return None


def ensure_worker_open(worker, start, end=None):
    period = locked_period_for(worker, start, end)
    if period is not None:
        raise ValidationError(locked_message(period))


def ensure_group_open(pay_group, start, end=None):
    period = _approved(pay_group.periods.all(), start, end).first()
    if period is not None:
        raise ValidationError(locked_message(period))


def ensure_company_open(company, start, end=None):
    """For changes that reach every worker, such as holidays and the company-wide schedule."""
    period = _approved(TimesheetPeriod.objects.filter(company=company), start, end).first()
    if period is not None:
        raise ValidationError(locked_message(period))
