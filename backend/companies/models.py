from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.utils.timezone import localdate


class Company(models.Model):
    name = models.CharField(max_length=200)
    timezone = models.CharField(max_length=64, default="UTC")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def today(self):
        return localdate(timezone=ZoneInfo(self.timezone))


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        TEAM_LEAD = "team_lead", "Team lead"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="unique_membership"),
        ]
        ordering = ["company__name"]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"
