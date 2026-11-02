from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class WorkerType(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="worker_types",
    )
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_worker_type_name"),
        ]

    def __str__(self):
        return self.name


class Team(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="teams",
    )
    number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    name = models.CharField(max_length=200)
    worker_count = models.PositiveIntegerField(default=0)
    lead_note = models.CharField(max_length=300, blank=True)
    lead_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="led_teams",
    )

    class Meta:
        ordering = ["number", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_team_name"),
            models.UniqueConstraint(fields=["company", "number"], name="unique_team_number"),
        ]

    def __str__(self):
        return f"{self.number} {self.name}"


class Worker(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="workers",
    )
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    worker_type = models.ForeignKey(
        WorkerType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workers",
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    """One stretch of time a worker spent in a team. start_date is empty when it began before records were kept."""

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="memberships")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = [models.F("start_date").desc(nulls_last=True), "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker"],
                condition=models.Q(end_date__isnull=True),
                name="one_open_team_per_worker",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="team_membership_dates_in_order",
            ),
        ]

    def __str__(self):
        return f"{self.worker} in {self.team}"
