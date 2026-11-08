import csv
import io
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from payroll.calc import calculate, money
from payroll.models import PayAdjustment, PayLine, PayRate, PayRun, PaySettings, Payment
from timesheets.models import TimesheetPeriod
from timesheets.periods import group_spans
from timesheets.schedule import WorkCalendar
from timesheets.sheet import amount, build_timesheet

ZERO = Decimal("0")
BOM = "\ufeff"


def pay_settings(company):
    return PaySettings.objects.get_or_create(company=company)[0]


def owed(workers):
    """{worker_id: approved pay minus everything handed over so far}. Negative means the worker owes."""
    nets = dict(
        PayLine.objects.filter(worker__in=workers, pay_run__status=PayRun.Status.APPROVED)
        .values("worker_id")
        .annotate(total=Sum("net"))
        .values_list("worker_id", "total")
    )
    paid = dict(
        Payment.objects.filter(worker__in=workers).values("worker_id").annotate(total=Sum("amount")).values_list("worker_id", "total")
    )
    return {worker.pk: (nets.get(worker.pk) or ZERO) - (paid.get(worker.pk) or ZERO) for worker in workers}


def live_lines(group, start, end):
    """Pay for every worker in the group's period, calculated now from the timesheet.

    Returns [(worker, Line, adjustments)] for workers with a rate or something that needs one."""
    company = group.company
    spans = group_spans(group, start, end)
    workers = sorted(spans, key=lambda worker: worker.name)
    calendar = WorkCalendar(company, workers, start, end)
    rows = build_timesheet(company, workers, start, end, {worker.pk: days for worker, days in spans.items()}, calendar)
    rates = defaultdict(list)
    for rate in PayRate.objects.filter(worker__in=workers).order_by("start_date"):
        rates[rate.worker_id].append(rate)
    adjustments = defaultdict(list)
    for adjustment in PayAdjustment.objects.filter(worker__in=workers, pay_line__isnull=True, date__lte=end):
        adjustments[adjustment.worker_id].append(adjustment)
    settings = pay_settings(company)
    result = []
    for row in rows:
        worker = row.worker
        line = calculate(worker.pk, row.counted(), rates[worker.pk], adjustments[worker.pk], calendar, settings)
        if line.pay_type or line.missing_rate or adjustments[worker.pk]:
            result.append((worker, line, adjustments[worker.pk]))
    return result


def line_fields(line):
    return {
        "pay_type": line.pay_type,
        "rate": line.rate,
        "days": line.days,
        "hours": line.hours,
        "extra_hours": line.extra_hours,
        "paid_off_days": line.paid_off_days,
        "unpaid_off_days": line.unpaid_off_days,
        "holidays": line.holidays,
        "base": line.base,
        "extra_pay": line.extra_pay,
        "off_pay": line.off_pay,
        "holiday_pay": line.holiday_pay,
        "bonuses": line.bonuses,
        "deductions": line.deductions,
        "gross": line.gross,
        "net": line.net,
    }


def approve_pay(group, start, end, user):
    period = TimesheetPeriod.objects.filter(pay_group=group, start_date=start, end_date=end).first()
    if period is None or period.status != TimesheetPeriod.Status.APPROVED:
        raise ValidationError("Approve the hours for this period first.")
    lines = live_lines(group, start, end)
    missing = [worker.name for worker, line, _ in lines if line.missing_rate]
    if missing:
        raise ValidationError(f"Give {', '.join(missing)} a pay rate first.")
    balances = owed([worker for worker, _, _ in lines])
    with transaction.atomic():
        run, _ = PayRun.objects.select_for_update().get_or_create(period=period, defaults={"company": group.company})
        if run.status == PayRun.Status.APPROVED:
            raise ValidationError("Pay for this period is already approved.")
        for worker, line, adjustments in lines:
            before = balances[worker.pk]
            saved = PayLine.objects.create(
                pay_run=run,
                worker=worker,
                **line_fields(line),
                balance_before=before,
                to_pay=before + line.net,
                breakdown={"segments": line.segments, "warnings": line.warnings, "unrecorded": line.unrecorded},
            )
            PayAdjustment.objects.filter(pk__in=[adjustment.pk for adjustment in adjustments]).update(pay_line=saved)
        run.status = PayRun.Status.APPROVED
        run.approved_by = user
        run.approved_at = timezone.now()
        run.save(update_fields=["status", "approved_by", "approved_at"])
    return run


def reopen_pay(run):
    if run.status != PayRun.Status.APPROVED:
        raise ValidationError("This pay isn't approved.")
    later = PayRun.objects.filter(
        period__pay_group=run.period.pay_group,
        status=PayRun.Status.APPROVED,
        period__start_date__gt=run.period.start_date,
    )
    if later.exists():
        raise ValidationError("Reopen the later pay of this group first.")
    with transaction.atomic():
        PayAdjustment.objects.filter(pay_line__pay_run=run).update(pay_line=None)
        run.lines.all().delete()
        run.status = PayRun.Status.DRAFT
        run.approved_by = None
        run.approved_at = None
        run.save(update_fields=["status", "approved_by", "approved_at"])
    return run


def ensure_rate_open(worker, start_date):
    """Rates can't start inside pay that is already approved."""
    last = (
        PayLine.objects.filter(worker=worker, pay_run__status=PayRun.Status.APPROVED)
        .select_related("pay_run__period")
        .order_by("-pay_run__period__end_date")
        .first()
    )
    if last is not None and start_date <= last.pay_run.period.end_date:
        raise ValidationError(
            {"start_date": f"Pay up to {last.pay_run.period.end_date} is approved. A new rate must start after it."}
        )


def safe_cell(value):
    """Text cells that start like a formula are prefixed, so a spreadsheet shows them instead of running them."""
    text = str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


EXPORT_COLUMNS = [
    ("Worker", None),
    ("Pay type", "pay_type"),
    ("Rate", "rate"),
    ("Days", "days"),
    ("Hours", "hours"),
    ("Extra hours", "extra_hours"),
    ("Paid days off", "paid_off_days"),
    ("Unpaid days off", "unpaid_off_days"),
    ("Holidays", "holidays"),
    ("Base", "base"),
    ("Extra hours pay", "extra_pay"),
    ("Days off pay", "off_pay"),
    ("Holiday pay", "holiday_pay"),
    ("Bonuses", "bonuses"),
    ("Deductions", "deductions"),
    ("Gross", "gross"),
    ("Net", "net"),
    ("Owed before", "balance_before"),
    ("To pay", "to_pay"),
]


MONEY_COLUMNS = {"rate", "base", "extra_pay", "off_pay", "holiday_pay", "bonuses", "deductions", "gross", "net", "balance_before", "to_pay"}


def export_csv(run):
    """UTF-8 with a byte-order mark, so names with ë or ç open correctly in Excel."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for label, _ in EXPORT_COLUMNS])
    for line in run.lines.select_related("worker"):
        cells = [safe_cell(line.worker.name)]
        for _, key in EXPORT_COLUMNS[1:]:
            value = getattr(line, key)
            if key == "pay_type":
                cells.append(safe_cell(line.get_pay_type_display()))
            elif key in MONEY_COLUMNS:
                cells.append(str(money(value)))
            else:
                cells.append(amount(value))
        writer.writerow(cells)
    return BOM + buffer.getvalue()
