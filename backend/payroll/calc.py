"""Gross pay from timesheet days. Pure functions over Day rows and rates: no queries.

Day rate: a worked day earns the rate (half a day earns half). Paid days off earn it too, and so do
holidays on scheduled weekdays when the company pays them.

Fixed weekly or monthly: the amount is shared evenly over the scheduled days of each whole week or
month, holidays included. Every scheduled day while employed earns its share; unpaid days off come off.
Someone hired on the 15th therefore earns about half a month.

Extra hours are counted day by day and never offset against short days. Amounts keep full precision
and are rounded to cents once per component.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from payroll.models import PayAdjustment, PayRate
from timesheets.leave import day_value
from timesheets.schedule import days_between, month_end, month_start, week_end, week_start
from timesheets.sheet import amount as plain

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
FIXED = (PayRate.PayType.WEEKLY, PayRate.PayType.MONTHLY)


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def rate_on(rates, day):
    """The rate in force on `day`; rates are sorted by start_date."""
    current = None
    for rate in rates:
        if rate.start_date > day:
            break
        current = rate
    return current


def bucket_of(pay_type, day):
    if pay_type == PayRate.PayType.WEEKLY:
        return week_start(day), week_end(day)
    return month_start(day), month_end(day)


def unpaid_value(day):
    """How much of a scheduled day an unpaid day off takes. A holiday inside an unpaid day off is unpaid too."""
    leave = day.leave
    if leave is None or leave.leave_type.paid:
        return ZERO
    if day.holiday and day.scheduled > 0:
        return day_value(leave)
    return day.off_value


@dataclass
class Line:
    pay_type: str = ""
    rate: Decimal = ZERO
    days: Decimal = ZERO
    hours: Decimal = ZERO
    extra_hours: Decimal = ZERO
    paid_off_days: Decimal = ZERO
    unpaid_off_days: Decimal = ZERO
    holidays: Decimal = ZERO
    base: Decimal = ZERO
    extra_pay: Decimal = ZERO
    off_pay: Decimal = ZERO
    holiday_pay: Decimal = ZERO
    bonuses: Decimal = ZERO
    deductions: Decimal = ZERO
    unrecorded: int = 0
    missing_rate: bool = False
    segments: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def rounded(self):
        for name in ("base", "extra_pay", "off_pay", "holiday_pay", "bonuses", "deductions"):
            setattr(self, name, money(getattr(self, name)))
        return self

    @property
    def gross(self):
        return self.base + self.extra_pay + self.off_pay + self.holiday_pay + self.bonuses

    @property
    def net(self):
        return self.gross - self.deductions


def calculate(worker_id, days, rates, adjustments, calendar, settings):
    """One worker's pay for the given (counted) days. `calendar` must cover whole weeks and months around them."""
    line = Line()
    multiplier = settings.extra_hours_multiplier
    shares = defaultdict(lambda: ZERO)  # (rate id, bucket) -> scheduled days earned
    extra_by_bucket = defaultdict(lambda: ZERO)  # (rate id, bucket) -> extra hours of fixed-pay days
    buckets_seen = defaultdict(set)  # (rate id, bucket) -> employed days in it, for the no-schedule fallback
    used = {}

    for day in days:
        line.days += day.work_value
        line.hours += day.worked
        if day.off_value > 0:
            if day.leave.leave_type.paid:
                line.paid_off_days += day.off_value
            else:
                line.unpaid_off_days += day.off_value
        holiday_off = day.holiday and day.scheduled > 0 and day.employed and not day.worked and unpaid_value(day) == 0
        rate = rate_on(rates, day.date)
        if rate is None:
            if day.work_value > 0 or day.off_value > 0 or holiday_off:
                line.missing_rate = True
            continue
        if rate.pay_type == PayRate.PayType.NOT_PAID_HERE:
            continue
        used[rate.pk] = rate
        line.pay_type, line.rate = rate.pay_type, rate.amount
        if holiday_off:
            line.holidays += ONE

        if rate.pay_type == PayRate.PayType.DAILY:
            line.base += day.work_value * rate.amount
            if day.off_value > 0 and day.leave.leave_type.paid:
                line.off_pay += day.off_value * rate.amount
            if holiday_off and settings.pay_holidays_for_day_rate:
                line.holiday_pay += rate.amount
            extra = max(ZERO, day.worked - day.norm)
            line.extra_hours += extra
            if extra > 0 and multiplier is not None:
                line.extra_pay += extra * rate.amount * multiplier / calendar.day_hours(worker_id, day.date)
            continue

        bucket = bucket_of(rate.pay_type, day.date)
        if day.employed:
            buckets_seen[rate.pk, bucket].add(day.date)
        if day.scheduled > 0 and day.employed:
            shares[rate.pk, bucket] += ONE - unpaid_value(day)
            if not day.entries and day.leave is None and not day.holiday:
                line.unrecorded += 1
        line.extra_hours += day.extra
        if day.extra > 0:
            extra_by_bucket[rate.pk, bucket] += day.extra

    for key, employed_days in buckets_seen.items():
        rate_id, (first, last) = key
        rate = used[rate_id]
        scheduled = sum(1 for each in days_between(first, last) if calendar.scheduled_hours(worker_id, each) > 0)
        if scheduled:
            units, out_of = shares.get(key, ZERO), Decimal(scheduled)
        else:
            # No schedule at all in this week or month: share the amount over calendar days instead.
            units, out_of = Decimal(len(employed_days)), Decimal((last - first).days + 1)
            line.warnings.append(f"No scheduled days from {first} to {last}; paid by calendar days.")
        if units == 0:
            continue
        value = rate.amount * units / out_of
        line.base += value
        line.segments.append(
            {
                "pay_type": rate.pay_type,
                "amount": str(rate.amount),
                "from": str(first),
                "to": str(last),
                "days": plain(units),
                "out_of": plain(out_of),
                "value": str(money(value)),
            }
        )

    if multiplier is not None:
        for (rate_id, (first, last)), hours in extra_by_bucket.items():
            scheduled_hours = sum((calendar.scheduled_hours(worker_id, each) for each in days_between(first, last)), ZERO)
            if scheduled_hours == 0:
                line.warnings.append(f"No scheduled hours from {first} to {last}; extra hours there are not paid.")
                continue
            line.extra_pay += hours * used[rate_id].amount * multiplier / scheduled_hours

    for adjustment in adjustments:
        if adjustment.kind == PayAdjustment.Kind.BONUS:
            line.bonuses += adjustment.amount
        else:
            line.deductions += adjustment.amount
    return line.rounded()
