from django.apps import AppConfig


class TimesheetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "timesheets"

    def ready(self):
        from django.db.models.signals import post_save

        from timesheets.periods import join_default_pay_group
        from workforce.models import Worker

        def worker_saved(sender, instance, created, raw=False, **kwargs):
            # Every worker is in exactly one pay group; new ones start in the company default.
            if created and not raw:
                join_default_pay_group(instance)

        post_save.connect(worker_saved, sender=Worker, dispatch_uid="timesheets.join_default_pay_group")
