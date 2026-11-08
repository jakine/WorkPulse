"""Expected hours from schedules, holidays and employment dates.

A WorkCalendar loads everything for a set of workers and a date range once, then answers from memory:
- scheduled_hours: the schedule's hours for that weekday, ignoring holidays and employment
- expected_hours: scheduled hours, but 0 on holidays and outside employment
- norm: what counts as a full day: the scheduled hours, or the schedule's day_hours on days it has none
"""

from calendar import monthrange
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Q

from timesheets.models import Holiday, ScheduleAssignment, WorkScheduleVersion
from workforce.services import overlapping, week_start

ZERO = Decimal("0")
DEFAULT_DAY_HOURS = Decimal("8")


def week_end(day):
    return week_start(day) + timedelta(days=6)


def month_start(day):
    return day.replace(day=1)


def month_end(day):
    return day.replace(day=monthrange(day.year, day.month)[1])


def days_between(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def covers(row, day):
    return (row.start_date is None or row.start_date <= day) and (row.end_date is None or day <= row.end_date)


class WorkCalendar:
    def __init__(self, company, workers, start, end):
        # Whole weeks and months around the range, so fixed pay can divide by a full week or month.
        self.start = min(week_start(start), month_start(start))
        self.end = max(week_end(end), month_end(end))
        self.workers = {worker.pk: worker for worker in workers}
        self.holidays = dict(
            Holiday.objects.filter(company=company, date__range=(self.start, self.end)).values_list("date", "name")
        )
        self.versions = defaultdict(list)
        versions = (
            WorkScheduleVersion.objects.filter(schedule__company=company)
            .select_related("schedule")
            .order_by(F("valid_from").asc(nulls_first=True))
        )
        for version in versions:
            self.versions[version.schedule_id].append(version)
        rows = (
            ScheduleAssignment.objects.filter(company=company)
            .filter(Q(worker__isnull=True) | Q(worker_id__in=list(self.workers)))
            .filter(overlapping(self.start, self.end))
        )
        self.company_rows = []
        self.worker_rows = defaultdict(list)
        for row in rows:
            if row.worker_id is None:
                self.company_rows.append(row)
            else:
                self.worker_rows[row.worker_id].append(row)

    def schedule_id_on(self, worker_id, day):
        for row in self.worker_rows.get(worker_id, ()):
            if covers(row, day):
                return row.schedule_id
        for row in self.company_rows:
            if covers(row, day):
                return row.schedule_id
        return None

    def version_on(self, worker_id, day):
        current = None
        for version in self.versions.get(self.schedule_id_on(worker_id, day), ()):
            if version.valid_from is not None and version.valid_from > day:
                break
            current = version
        return current

    def holiday(self, day):
        return self.holidays.get(day)

    def scheduled_hours(self, worker_id, day):
        version = self.version_on(worker_id, day)
        return version.hours_on(day) if version else ZERO

    def expected_hours(self, worker_id, day):
        if day in self.holidays or not self.workers[worker_id].employed_on(day):
            return ZERO
        return self.scheduled_hours(worker_id, day)

    def day_hours(self, worker_id, day):
        version = self.version_on(worker_id, day)
        return version.day_hours if version else DEFAULT_DAY_HOURS

    def norm(self, worker_id, day):
        scheduled = self.scheduled_hours(worker_id, day)
        if scheduled > 0 and day not in self.holidays:
            return scheduled
        return self.day_hours(worker_id, day)
