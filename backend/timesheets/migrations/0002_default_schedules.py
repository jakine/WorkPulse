from decimal import Decimal

from django.db import migrations

WORKDAYS = ("mon", "tue", "wed", "thu", "fri")


def create_default_schedules(apps, schema_editor):
    """Every existing company starts with Mon–Fri 8 h for everyone."""
    Company = apps.get_model("companies", "Company")
    WorkSchedule = apps.get_model("timesheets", "WorkSchedule")
    WorkScheduleVersion = apps.get_model("timesheets", "WorkScheduleVersion")
    ScheduleAssignment = apps.get_model("timesheets", "ScheduleAssignment")
    for company in Company.objects.all():
        schedule, _ = WorkSchedule.objects.get_or_create(company=company, name="Standard")
        if not WorkScheduleVersion.objects.filter(schedule=schedule).exists():
            WorkScheduleVersion.objects.create(schedule=schedule, **{day: Decimal("8") for day in WORKDAYS})
        if not ScheduleAssignment.objects.filter(company=company, worker__isnull=True).exists():
            ScheduleAssignment.objects.create(company=company, schedule=schedule)


class Migration(migrations.Migration):
    dependencies = [
        ("timesheets", "0001_schedules"),
    ]

    operations = [
        migrations.RunPython(create_default_schedules, migrations.RunPython.noop),
    ]
