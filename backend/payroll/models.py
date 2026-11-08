"""Pay: rates, bonuses and deductions, payments, and the pay lines frozen when a period's pay is approved.

Only the owner sees any of this (companies.permissions.CanSeePay)."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

MONEY = {"max_digits": 12, "decimal_places": 2}
DAYS = {"max_digits": 6, "decimal_places": 2, "default": Decimal("0")}


class PaySettings(models.Model):
    company = models.OneToOneField("companies.Company", on_delete=models.CASCADE, related_name="pay_settings")
    currency = models.CharField(max_length=3, default="EUR")
    extra_hours_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Empty: extra hours are not paid. 1.00 pays them at the normal rate, 1.50 at time and a half.",
    )
    pay_holidays_for_day_rate = models.BooleanField(default=True)

    def __str__(self):
        return f"Pay settings for {self.company}"


class PayRate(models.Model):
    """What a worker earns from start_date on. The latest rate starting on or before a day applies."""

    class PayType(models.TextChoices):
        DAILY = "daily", "Per day"
        WEEKLY = "weekly", "Per week"
        MONTHLY = "monthly", "Per month"
        NOT_PAID_HERE = "not_paid_here", "Not paid through WorkPulse"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="pay_rates")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.RESTRICT, related_name="pay_rates")
    start_date = models.DateField()
    pay_type = models.CharField(max_length=20, choices=PayType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pay_rates_set"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date"]
        constraints = [
            models.UniqueConstraint(fields=["worker", "start_date"], name="one_pay_rate_per_start"),
        ]

    def __str__(self):
        return f"{self.worker} {self.amount} {self.pay_type} from {self.start_date}"


class PayRun(models.Model):
    """The pay for one approved period of a pay group. Approving it freezes its lines."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="pay_runs")
    period = models.OneToOneField("timesheets.TimesheetPeriod", on_delete=models.RESTRICT, related_name="pay_run")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_pay_runs"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period__start_date"]

    def __str__(self):
        return f"Pay for {self.period}"


class PayLine(models.Model):
    """One worker's pay for a run, as approved. The only stored calculated numbers in WorkPulse."""

    pay_run = models.ForeignKey(PayRun, on_delete=models.CASCADE, related_name="lines")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.RESTRICT, related_name="pay_lines")
    pay_type = models.CharField(max_length=20, choices=PayRate.PayType.choices)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    days = models.DecimalField(**DAYS)
    hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    extra_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    paid_off_days = models.DecimalField(**DAYS)
    unpaid_off_days = models.DecimalField(**DAYS)
    holidays = models.DecimalField(**DAYS)
    base = models.DecimalField(**MONEY)
    extra_pay = models.DecimalField(**MONEY)
    off_pay = models.DecimalField(**MONEY)
    holiday_pay = models.DecimalField(**MONEY)
    bonuses = models.DecimalField(**MONEY)
    deductions = models.DecimalField(**MONEY)
    gross = models.DecimalField(**MONEY)
    net = models.DecimalField(**MONEY)
    balance_before = models.DecimalField(**MONEY)
    to_pay = models.DecimalField(**MONEY)
    breakdown = models.JSONField(default=dict)

    class Meta:
        ordering = ["worker__name"]
        constraints = [
            models.UniqueConstraint(fields=["pay_run", "worker"], name="one_pay_line_per_worker"),
        ]

    def __str__(self):
        return f"{self.worker} {self.net}"


class PayAdjustment(models.Model):
    """A bonus or a deduction. It goes into the first pay run approved after its date, then can't change."""

    class Kind(models.TextChoices):
        BONUS = "bonus", "Bonus"
        DEDUCTION = "deduction", "Deduction"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="pay_adjustments")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.RESTRICT, related_name="pay_adjustments")
    date = models.DateField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    note = models.CharField(max_length=300, blank=True)
    pay_line = models.ForeignKey(
        PayLine, null=True, blank=True, on_delete=models.SET_NULL, related_name="adjustments"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pay_adjustments_made"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.worker} {self.kind} {self.amount}"


class Payment(models.Model):
    """Money handed to a worker: an advance on any day, or wages after pay is approved."""

    class Kind(models.TextChoices):
        ADVANCE = "advance", "Advance"
        WAGES = "wages", "Wages"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        OTHER = "other", "Other"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="payments")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.RESTRICT, related_name="payments")
    paid_on = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.WAGES)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments_made"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-id"]
        indexes = [models.Index(fields=["worker", "paid_on"])]

    def __str__(self):
        return f"{self.worker} {self.amount} on {self.paid_on}"
