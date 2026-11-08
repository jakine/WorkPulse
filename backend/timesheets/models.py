from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def hours_field(**kwargs):
    return models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))],
        **kwargs,
    )


class WorkSchedule(models.Model):
    """A named weekly pattern of hours, e.g. "Standard" or "Six days". Its hours live in dated versions."""

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="work_schedules")
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_work_schedule_name"),
        ]

    def __str__(self):
        return self.name


class WorkScheduleVersion(models.Model):
    """Hours per weekday from valid_from on. valid_from is empty for the first version."""

    schedule = models.ForeignKey(WorkSchedule, on_delete=models.CASCADE, related_name="versions")
    valid_from = models.DateField(null=True, blank=True)
    mon = hours_field(default=Decimal("0"))
    tue = hours_field(default=Decimal("0"))
    wed = hours_field(default=Decimal("0"))
    thu = hours_field(default=Decimal("0"))
    fri = hours_field(default=Decimal("0"))
    sat = hours_field(default=Decimal("0"))
    sun = hours_field(default=Decimal("0"))
    day_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("8"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("24"))],
        help_text="A full day for this schedule, used on days it has no hours.",
    )

    class Meta:
        ordering = [models.F("valid_from").asc(nulls_first=True)]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "valid_from"],
                nulls_distinct=False,
                name="unique_schedule_version_start",
            ),
        ]

    def __str__(self):
        return f"{self.schedule} from {self.valid_from or 'the start'}"

    def hours_on(self, day):
        return getattr(self, WEEKDAYS[day.weekday()])

    @property
    def week_hours(self):
        return sum((getattr(self, name) for name in WEEKDAYS), Decimal("0"))


class ScheduleAssignment(models.Model):
    """The schedule a worker follows over a stretch of time. worker is empty for the company-wide default."""

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="schedule_assignments")
    schedule = models.ForeignKey(WorkSchedule, on_delete=models.RESTRICT, related_name="assignments")
    worker = models.ForeignKey(
        "workforce.Worker",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="schedule_assignments",
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = [models.F("start_date").desc(nulls_last=True), "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker"],
                condition=models.Q(end_date__isnull=True, worker__isnull=False),
                name="one_open_schedule_per_worker",
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(end_date__isnull=True, worker__isnull=True),
                name="one_open_company_schedule",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="schedule_assignment_dates_in_order",
            ),
        ]

    def __str__(self):
        return f"{self.worker or 'Everyone'} on {self.schedule}"


class Holiday(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="holidays")
    date = models.DateField()
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["company", "date"], name="unique_holiday_per_day"),
        ]

    def __str__(self):
        return f"{self.date} {self.name}"


class LeaveType(models.Model):
    """A kind of day off. paid and uses_allowance are fixed once a day off uses the type; archive it instead."""

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="leave_types")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=2)
    paid = models.BooleanField(default=True)
    uses_allowance = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_leave_type_name"),
            models.UniqueConstraint(fields=["company", "code"], name="unique_leave_type_code"),
        ]

    def __str__(self):
        return self.name


class Leave(models.Model):
    """A day off, or a run of days off, for one worker."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Waiting"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="days_off")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.RESTRICT, related_name="days_off")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.RESTRICT, related_name="days_off")
    start_date = models.DateField()
    end_date = models.DateField()
    half_day = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    note = models.CharField(max_length=300, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_days_off",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_days_off",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [models.Index(fields=["worker", "start_date"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="leave_dates_in_order"),
            models.CheckConstraint(
                condition=models.Q(half_day=False) | models.Q(end_date=models.F("start_date")),
                name="half_day_is_one_day",
            ),
        ]

    def __str__(self):
        return f"{self.worker} {self.leave_type} {self.start_date}–{self.end_date}"


class OtherWork(models.Model):
    """Hours a worker worked away from any project: at the yard, in the office, travelling or training."""

    class Kind(models.TextChoices):
        YARD = "yard", "Yard"
        OFFICE = "office", "Office"
        TRAVEL = "travel", "Travel"
        TRAINING = "training", "Training"
        OTHER = "other", "Other"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="other_work")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.RESTRICT, related_name="other_work")
    work_date = models.DateField()
    hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(Decimal("24"))],
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.YARD)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="other_work_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-work_date", "worker__name"]
        indexes = [models.Index(fields=["worker", "work_date"])]
        constraints = [
            models.UniqueConstraint(fields=["worker", "work_date", "kind"], name="one_other_work_kind_per_day"),
        ]

    def __str__(self):
        return f"{self.worker} {self.kind} {self.work_date} {self.hours} h"


class PayGroup(models.Model):
    """Workers settled on the same cycle, e.g. a weekly crew or monthly staff. Hours are approved per group."""

    class Cycle(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        TWO_WEEKS = "two_weeks", "Every two weeks"
        MONTHLY = "monthly", "Monthly"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="pay_groups")
    name = models.CharField(max_length=100)
    cycle = models.CharField(max_length=20, choices=Cycle.choices, default=Cycle.MONTHLY)
    anchor_date = models.DateField(null=True, blank=True, help_text="A Monday that starts a two-week cycle.")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_pay_group_name"),
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(is_default=True),
                name="one_default_pay_group",
            ),
        ]

    def __str__(self):
        return self.name


class PayGroupAssignment(models.Model):
    """The pay group a worker is in over a stretch of time."""

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="pay_group_assignments")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.CASCADE, related_name="pay_group_assignments")
    pay_group = models.ForeignKey(PayGroup, on_delete=models.RESTRICT, related_name="assignments")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = [models.F("start_date").desc(nulls_last=True), "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker"],
                condition=models.Q(end_date__isnull=True),
                name="one_open_pay_group_per_worker",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="pay_group_assignment_dates_in_order",
            ),
        ]

    def __str__(self):
        return f"{self.worker} in {self.pay_group}"


class TimesheetPeriod(models.Model):
    """One cycle of a pay group. Approving it locks the hours, days off and schedules of its workers inside it."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        APPROVED = "approved", "Approved"

    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="timesheet_periods")
    pay_group = models.ForeignKey(PayGroup, on_delete=models.RESTRICT, related_name="periods")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_timesheet_periods",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["pay_group", "start_date"], name="unique_period_start_per_group"),
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="period_dates_in_order"),
        ]

    def __str__(self):
        return f"{self.pay_group} {self.start_date}–{self.end_date}"

    def label(self):
        return f"{self.pay_group.name}, {period_label(self.start_date, self.end_date)}"


def period_label(start, end):
    if start.year != end.year:
        return f"{start:%-d %b %Y} – {end:%-d %b %Y}"
    if start.month != end.month:
        return f"{start:%-d %b} – {end:%-d %b %Y}"
    return f"{start.day}–{end:%-d %b %Y}"
