from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from workforce.models import TeamMembership, Worker


def ranges_overlap(start_a, end_a, start_b, end_b):
    end_a = end_a or date.max
    end_b = end_b or date.max
    return start_a <= end_b and start_b <= end_a


def week_start(day):
    return day - timedelta(days=day.weekday())


def overlapping(start, end, prefix=""):
    """Q for rows with optional start_date/end_date that overlap start..end."""
    return (Q(**{f"{prefix}start_date__isnull": True}) | Q(**{f"{prefix}start_date__lte": end})) & (
        Q(**{f"{prefix}end_date__isnull": True}) | Q(**{f"{prefix}end_date__gte": start})
    )


def active_on(on_date, prefix=""):
    """Q for rows with optional start_date/end_date that cover on_date."""
    return overlapping(on_date, on_date, prefix)


def team_members_on(team, on_date):
    return Worker.objects.filter(Q(memberships__team=team) & active_on(on_date, "memberships__")).distinct()


def move_worker(worker, team, on_date):
    """Close the worker's open team stretch the day before on_date and open one in `team` (None leaves the team)."""
    if team is not None and team.company_id != worker.company_id:
        raise ValidationError({"team": "Team must belong to this company."})
    if on_date > worker.company.today():
        raise ValidationError({"on_date": "Record moves up to today."})
    with transaction.atomic():
        worker = Worker.objects.select_for_update().select_related("company").get(pk=worker.pk)
        current = worker.memberships.select_related("team").filter(end_date__isnull=True).first()
        if current is not None and current.team_id == getattr(team, "id", None):
            return worker
        if current is not None:
            if current.start_date is not None and on_date < current.start_date:
                raise ValidationError(
                    {"on_date": f"{worker.name} joined {current.team.name} on {current.start_date}. Choose that day or later."}
                )
            if current.start_date == on_date:
                current.delete()
            else:
                current.end_date = on_date - timedelta(days=1)
                current.save(update_fields=["end_date"])
        else:
            last = worker.memberships.select_related("team").filter(end_date__isnull=False).order_by("-end_date").first()
            if last is not None and on_date <= last.end_date:
                raise ValidationError(
                    {"on_date": f"{worker.name} was in {last.team.name} until {last.end_date}. Choose a later day."}
                )
        if team is not None:
            TeamMembership.objects.create(worker=worker, team=team, start_date=on_date)
        worker.team = team
        worker.save(update_fields=["team"])
    return worker
