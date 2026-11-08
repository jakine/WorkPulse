"""The timesheet: for each worker and day, what was expected and what was recorded.

Built from a fixed number of bulk queries and never stored. Pay is calculated from these same rows,
so the timesheet and pay can't disagree.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sitelog.models import CrewAttendance, DailyLog
from timesheets.leave import day_value
from timesheets.models import Holiday, Leave, OtherWork, PayGroupAssignment, TimesheetPeriod
from timesheets.schedule import WorkCalendar, covers, days_between, week_start

ZERO = Decimal("0")
HALF = Decimal("0.5")
ONE = Decimal("1")


def work_value(hours, norm):
    """No hours is no day; up to half a full day is half a day; more is a whole day."""
    if hours <= 0:
        return ZERO
    return HALF if hours <= norm / 2 else ONE


def amount(value):
    """Decimal to a short string: 8, 7.5, 0.25."""
    value = Decimal(value).quantize(Decimal("0.01"))
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass
class Day:
    date: date
    scheduled: Decimal  # the schedule's hours, ignoring holidays and employment
    expected: Decimal  # scheduled hours on working days while employed
    norm: Decimal  # what counts as a full day
    holiday: str | None
    employed: bool
    counted: bool = True  # False on days the worker spent in another pay group
    locked: bool = False  # inside an approved period
    entries: list = field(default_factory=list)
    leave: Leave | None = None  # approved day off
    waiting: Leave | None = None  # day off still waiting for a decision

    @property
    def site_entries(self):
        return [entry for entry in self.entries if entry["type"] == "site"]

    @property
    def worked(self):
        return sum((entry["hours"] for entry in self.entries), ZERO)

    @property
    def work_value(self):
        return work_value(self.worked, self.norm)

    @property
    def leave_value(self):
        return day_value(self.leave) if self.leave is not None and self.expected > 0 else ZERO

    @property
    def off_value(self):
        """The day off actually used: never more than what work left of the day."""
        return min(self.leave_value, ONE - self.work_value)

    @property
    def expected_after_off(self):
        return self.expected * (ONE - self.leave_value)

    @property
    def extra(self):
        return max(ZERO, self.worked - self.expected_after_off)

    def flags(self, today):
        flags = []
        if self.counted and self.date < today and self.expected > 0 and not self.entries and self.leave is None:
            flags.append("missing")
        if self.leave is not None and self.worked > 0 and self.leave_value + self.work_value > ONE:
            flags.append("worked_on_leave")
        return flags


@dataclass
class Row:
    worker: object
    days: list

    def counted(self):
        return [day for day in self.days if day.counted]


def build_timesheet(company, workers, start, end, spans=None, calendar=None):
    """Rows of Days for each worker from start to end.

    spans ({worker_id: [(first, last), ...]}) limits what counts to the days each worker spent in one pay group."""
    workers = list(workers)
    ids = [worker.pk for worker in workers]
    calendar = calendar or WorkCalendar(company, workers, start, end)

    site = defaultdict(list)
    for row in CrewAttendance.objects.filter(worker_id__in=ids, work_date__range=(start, end)).values(
        "id", "worker_id", "work_date", "workplace_id", "team_id", "hours"
    ):
        site[row["worker_id"], row["work_date"]].append(row)
    approved_days = set(
        DailyLog.objects.filter(
            workplace_id__in={row["workplace_id"] for rows in site.values() for row in rows},
            work_date__range=(start, end),
            status=DailyLog.Status.APPROVED,
        ).values_list("workplace_id", "work_date")
    )
    other = defaultdict(list)
    for row in OtherWork.objects.filter(worker_id__in=ids, work_date__range=(start, end)).values(
        "id", "worker_id", "work_date", "kind", "hours", "note"
    ):
        other[row["worker_id"], row["work_date"]].append(row)
    leaves = defaultdict(list)
    for leave in Leave.objects.filter(
        worker_id__in=ids,
        status__in=(Leave.Status.APPROVED, Leave.Status.REQUESTED),
        start_date__lte=end,
        end_date__gte=start,
    ).select_related("leave_type"):
        leaves[leave.worker_id].append(leave)

    stretches = defaultdict(list)
    for stretch in PayGroupAssignment.objects.filter(worker_id__in=ids):
        stretches[stretch.worker_id].append(stretch)
    approved = defaultdict(list)
    for period in TimesheetPeriod.objects.filter(
        pay_group_id__in={stretch.pay_group_id for rows in stretches.values() for stretch in rows},
        status=TimesheetPeriod.Status.APPROVED,
        start_date__lte=end,
        end_date__gte=start,
    ):
        approved[period.pay_group_id].append(period)

    rows = []
    for worker in workers:
        days = []
        for day in days_between(start, end):
            group = next((stretch.pay_group_id for stretch in stretches[worker.pk] if covers(stretch, day)), None)
            entry = Day(
                date=day,
                scheduled=calendar.scheduled_hours(worker.pk, day),
                expected=calendar.expected_hours(worker.pk, day),
                norm=calendar.norm(worker.pk, day),
                holiday=calendar.holiday(day),
                employed=worker.employed_on(day),
                counted=spans is None or any(first <= day <= last for first, last in spans.get(worker.pk, ())),
                locked=any(period.start_date <= day <= period.end_date for period in approved.get(group, ())),
            )
            for row in site[worker.pk, day]:
                entry.entries.append(
                    {
                        "type": "site",
                        "id": row["id"],
                        "workplace": row["workplace_id"],
                        "team": row["team_id"],
                        "hours": row["hours"],
                        "day_approved": (row["workplace_id"], day) in approved_days,
                    }
                )
            for row in other[worker.pk, day]:
                entry.entries.append(
                    {"type": "other", "id": row["id"], "kind": row["kind"], "hours": row["hours"], "note": row["note"]}
                )
            for leave in leaves[worker.pk]:
                if covers(leave, day):
                    if leave.status == Leave.Status.APPROVED:
                        entry.leave = leave
                    else:
                        entry.waiting = leave
            days.append(entry)
        rows.append(Row(worker=worker, days=days))
    return rows


def totals(days, today):
    result = {
        "days": ZERO,
        "hours": ZERO,
        "expected": ZERO,
        "extra": ZERO,
        "paid_off": ZERO,
        "unpaid_off": ZERO,
        "off": defaultdict(lambda: ZERO),
        "holidays": 0,
        "missing": 0,
        "worked_on_leave": 0,
    }
    for day in days:
        result["days"] += day.work_value
        result["hours"] += day.worked
        result["expected"] += day.expected
        result["extra"] += day.extra
        if day.off_value > 0:
            result["off"][day.leave.leave_type.code] += day.off_value
            result["paid_off" if day.leave.leave_type.paid else "unpaid_off"] += day.off_value
        if day.holiday and day.scheduled > 0 and day.employed:
            result["holidays"] += 1
        flags = day.flags(today)
        result["missing"] += "missing" in flags
        result["worked_on_leave"] += "worked_on_leave" in flags
    return result


def weekly(days):
    weeks = defaultdict(lambda: {"days": ZERO, "hours": ZERO, "extra": ZERO})
    for day in days:
        week = weeks[week_start(day.date)]
        week["days"] += day.work_value
        week["hours"] += day.worked
        week["extra"] += day.extra
    return [{"week": str(start), **{key: amount(value) for key, value in week.items()}} for start, week in sorted(weeks.items())]


def cell_json(day, today, project_names):
    """`editable`: hours can be typed straight into the cell (not on a full day off or an unworked holiday)."""
    site = day.site_entries
    editable = (
        day.counted
        and not day.locked
        and day.employed
        and day.date <= today
        and len(site) == len(day.entries) <= 1
        and not any(entry["day_approved"] for entry in site)
        and not (day.leave is not None and not day.leave.half_day)
        and not (day.holiday and not day.worked)
    )
    off = None
    shown = day.leave or day.waiting
    if shown is not None:
        off = {
            "code": shown.leave_type.code,
            "name": shown.leave_type.name,
            "paid": shown.leave_type.paid,
            "half_day": shown.half_day,
            "status": shown.status,
        }
    return {
        "expected": amount(day.expected),
        "worked": amount(day.worked),
        "extra": amount(day.extra),
        "entries": [
            {
                **entry,
                "hours": amount(entry["hours"]),
                **({"project_name": project_names.get(entry["workplace"], "")} if entry["type"] == "site" else {}),
            }
            for entry in day.entries
        ],
        "off": off,
        "flags": day.flags(today),
        "locked": day.locked,
        "counted": day.counted,
        "editable": editable,
    }


def sheet_json(company, rows, start, end, project_names):
    today = company.today()
    holidays = dict(Holiday.objects.filter(company=company, date__range=(start, end)).values_list("date", "name"))
    workers = []
    daily = defaultdict(lambda: {"people": 0, "hours": ZERO})
    for row in rows:
        cells = {}
        for day in row.days:
            if day.entries or day.leave or day.waiting or (day.counted and day.expected > 0):
                cells[str(day.date)] = cell_json(day, today, project_names)
            if day.counted and day.worked > 0:
                daily[str(day.date)]["people"] += 1
                daily[str(day.date)]["hours"] += day.worked
        counted = row.counted()
        total = totals(counted, today)
        workers.append(
            {
                "worker": row.worker.pk,
                "name": row.worker.name,
                "team": row.worker.team_id,
                "team_name": row.worker.team.name if row.worker.team_id else "",
                "team_number": row.worker.team.number if row.worker.team_id else None,
                "cells": cells,
                "totals": {
                    **{key: amount(total[key]) for key in ("days", "hours", "expected", "extra", "paid_off", "unpaid_off")},
                    "off": {code: amount(value) for code, value in total["off"].items()},
                    **{key: total[key] for key in ("holidays", "missing", "worked_on_leave")},
                },
                "weeks": weekly(counted),
            }
        )
    return {
        "start": str(start),
        "end": str(end),
        "today": str(today),
        "days": [
            {"date": str(day), "weekday": day.weekday(), "holiday": holidays.get(day)} for day in days_between(start, end)
        ],
        "projects": {str(key): value for key, value in project_names.items()},
        "workers": workers,
        "daily": {key: {"people": value["people"], "hours": amount(value["hours"])} for key, value in daily.items()},
    }
