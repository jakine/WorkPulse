from django.db import migrations

DEFAULT_LEAVE_TYPES = (
    ("Vacation", "V", True, True),
    ("Sick", "S", True, False),
    ("Unpaid leave", "U", False, False),
    ("Absent (no notice)", "A", False, False),
    ("Other paid", "P", True, False),
)


def create_default_leave_types(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    LeaveType = apps.get_model("timesheets", "LeaveType")
    for company in Company.objects.all():
        for position, (name, code, paid, allowance) in enumerate(DEFAULT_LEAVE_TYPES):
            LeaveType.objects.get_or_create(
                company=company,
                name=name,
                defaults={"code": code, "paid": paid, "uses_allowance": allowance, "position": position},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("timesheets", "0003_days_off"),
    ]

    operations = [
        migrations.RunPython(create_default_leave_types, migrations.RunPython.noop),
    ]
