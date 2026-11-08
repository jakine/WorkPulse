from django.db import migrations


def create_default_pay_groups(apps, schema_editor):
    """Every existing company gets a monthly group, and every worker starts in it."""
    Company = apps.get_model("companies", "Company")
    PayGroup = apps.get_model("timesheets", "PayGroup")
    PayGroupAssignment = apps.get_model("timesheets", "PayGroupAssignment")
    Worker = apps.get_model("workforce", "Worker")
    for company in Company.objects.all():
        group = PayGroup.objects.filter(company=company, is_default=True).first()
        if group is None:
            group = PayGroup.objects.create(company=company, name="Monthly", cycle="monthly", is_default=True)
        for worker in Worker.objects.filter(company=company):
            if not PayGroupAssignment.objects.filter(worker=worker, end_date__isnull=True).exists():
                PayGroupAssignment.objects.create(company=company, worker=worker, pay_group=group)


class Migration(migrations.Migration):
    dependencies = [
        ("timesheets", "0005_hours_and_pay_groups"),
    ]

    operations = [
        migrations.RunPython(create_default_pay_groups, migrations.RunPython.noop),
    ]
