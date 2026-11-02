from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class DailyLog(models.Model):
    """One project day. Reports and crew live on workplace + date; the log holds the day's notes and approval."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        APPROVED = "approved", "Approved"

    workplace = models.ForeignKey(
        "operations.Workplace",
        on_delete=models.CASCADE,
        related_name="daily_logs",
    )
    work_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    weather = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_daily_logs",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "id"]
        constraints = [
            models.UniqueConstraint(fields=["workplace", "work_date"], name="unique_daily_log_per_project_day"),
        ]

    def __str__(self):
        return f"{self.workplace} {self.work_date}"


class DailyLogIssue(models.Model):
    class Kind(models.TextChoices):
        DELAY = "delay", "Delay"
        WEATHER = "weather", "Weather"
        MATERIAL = "material", "Material missing"
        ACCESS = "access", "No access"
        SAFETY = "safety", "Safety"
        OTHER = "other", "Other"

    log = models.ForeignKey(DailyLog, on_delete=models.CASCADE, related_name="issues")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=300)
    hours_lost = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    resolved = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_log_issues",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.description}"


class CrewAttendance(models.Model):
    """A worker was on site with a team on a project day."""

    workplace = models.ForeignKey(
        "operations.Workplace",
        on_delete=models.CASCADE,
        related_name="attendance",
    )
    work_date = models.DateField()
    team = models.ForeignKey("workforce.Team", on_delete=models.CASCADE, related_name="attendance")
    worker = models.ForeignKey("workforce.Worker", on_delete=models.CASCADE, related_name="attendance")

    class Meta:
        ordering = ["work_date", "team__number", "worker__name"]
        constraints = [
            models.UniqueConstraint(fields=["worker", "workplace", "work_date"], name="unique_attendance_per_worker_day"),
        ]
        indexes = [
            models.Index(fields=["workplace", "work_date"]),
        ]

    def __str__(self):
        return f"{self.worker} @ {self.workplace} {self.work_date}"
