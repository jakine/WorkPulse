"""Progress, pace and forecasts. Everything here is a sum over SiteReport and CrewAttendance rows."""

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from operations.models import SiteReport, Workplace, WorkType
from operations.services import days_for, scopes_with_progress
from sitelog.models import CrewAttendance
from workforce.models import Team
from workforce.services import week_start

RECENT_WORKING_DAYS = 10
WEEKS_SHOWN = 8
ZERO = Decimal("0.00")
STATUS_ORDER = ("behind", "stalled", "no_plan", "on_track", "not_started", "done")


def is_working_day(day):
    return day.weekday() < 5


def recent_working_days(end, count=RECENT_WORKING_DAYS):
    days, day = [], end
    while len(days) < count:
        if is_working_day(day):
            days.append(day)
        day -= timedelta(days=1)
    return days


def add_working_days(start, count):
    day, left = start, count
    while left > 0:
        day += timedelta(days=1)
        if is_working_day(day):
            left -= 1
    return day


def amount(value):
    return None if value is None else str(Decimal(value).quantize(Decimal("0.01")))


def per(quantity, divisor):
    return amount(quantity / divisor) if divisor else None


def report_rows(reports):
    return list(
        reports.values(
            "id",
            "workplace_id",
            "workplace__work_type_id",
            "team_id",
            "task_id",
            "task__work_type_id",
            "scope_id",
            "scope__work_type_id",
            "work_date",
            "quantity",
            "days",
        )
    )


def work_type_of(row):
    """Same matching as reports_matching_scope: the scope, else the task's work type, else the project's."""
    if row["scope_id"]:
        return row["scope__work_type_id"]
    if row["task_id"]:
        return row["task__work_type_id"]
    return row["workplace__work_type_id"]


def crew_shares(rows):
    """Worker-days behind each report, split by the report's share of the team's day. None without crew records."""
    keys = {(row["workplace_id"], row["team_id"], row["work_date"]) for row in rows if row["team_id"]}
    if not keys:
        return {}
    crew = defaultdict(int)
    attendance = CrewAttendance.objects.filter(
        workplace_id__in={key[0] for key in keys},
        work_date__in={key[2] for key in keys},
    ).values("workplace_id", "team_id", "work_date")
    for row in attendance:
        crew[(row["workplace_id"], row["team_id"], row["work_date"])] += 1
    day_totals = defaultdict(Decimal)
    for row in rows:
        day_totals[(row["workplace_id"], row["team_id"], row["work_date"])] += row["days"]
    shares = {}
    for row in rows:
        key = (row["workplace_id"], row["team_id"], row["work_date"])
        shares[row["id"]] = Decimal(crew[key]) * row["days"] / day_totals[key] if crew.get(key) else None
    return shares


class Tally:
    def __init__(self):
        self.quantity = ZERO
        self.team_days = ZERO
        self.crew_quantity = ZERO
        self.worker_days = ZERO

    def add(self, row, share):
        quantity = row["quantity"] or ZERO
        self.quantity += quantity
        self.team_days += row["days"]
        if share:
            self.crew_quantity += quantity
            self.worker_days += share

    def pace(self):
        return {
            "team_days": amount(self.team_days),
            "per_team_day": per(self.quantity, self.team_days),
            "worker_days": amount(self.worker_days),
            "per_worker_day": per(self.crew_quantity, self.worker_days),
        }


def weekly_series(totals, first_week, weeks):
    return [
        {"week": str(first_week + timedelta(weeks=index)), "quantity": amount(totals.get(first_week + timedelta(weeks=index), ZERO))}
        for index in range(weeks)
    ]


def planned_finish(workplace, scope, first_report):
    length = days_for(scope.length_count, scope.length_unit)
    start = workplace.start_date or first_report
    if length and start:
        return start + timedelta(days=int(length.to_integral_value(rounding=ROUND_CEILING)) - 1)
    return workplace.end_date


def scope_status(remaining, first_report, daily_rate, forecast, finish):
    if remaining <= 0:
        return "done"
    if first_report is None:
        return "not_started"
    if daily_rate <= 0:
        return "stalled"
    if finish is None:
        return "no_plan"
    return "on_track" if forecast <= finish else "behind"


def project_progress(workplace, as_of):
    scopes = list(scopes_with_progress(workplace.scopes.select_related("work_type__measure", "length_unit")))
    scope_by_type = {scope.work_type_id: scope for scope in scopes}
    rows = report_rows(SiteReport.objects.filter(workplace=workplace, work_date__lte=as_of))
    shares = crew_shares(rows)
    recent = set(recent_working_days(as_of))
    first_week = week_start(as_of) - timedelta(weeks=WEEKS_SHOWN - 1)
    teams = {team.pk: team for team in Team.objects.filter(pk__in={row["team_id"] for row in rows if row["team_id"]})}

    tallies = {scope.pk: Tally() for scope in scopes}
    by_team = {scope.pk: defaultdict(Tally) for scope in scopes}
    weekly = {scope.pk: defaultdict(Decimal) for scope in scopes}
    recent_quantity = defaultdict(Decimal)
    first_report = {}
    for row in rows:
        scope = scope_by_type.get(work_type_of(row))
        if scope is None:
            continue
        share = shares.get(row["id"])
        tallies[scope.pk].add(row, share)
        if row["team_id"]:
            by_team[scope.pk][row["team_id"]].add(row, share)
        quantity = row["quantity"] or ZERO
        if row["work_date"] in recent:
            recent_quantity[scope.pk] += quantity
        if row["work_date"] >= first_week:
            weekly[scope.pk][week_start(row["work_date"])] += quantity
        if scope.pk not in first_report or row["work_date"] < first_report[scope.pk]:
            first_report[scope.pk] = row["work_date"]

    results = []
    for scope in scopes:
        done = scope.done_total
        remaining = scope.planned_quantity - done
        daily_rate = recent_quantity[scope.pk] / RECENT_WORKING_DAYS
        forecast = None
        if remaining > 0 and daily_rate > 0:
            forecast = add_working_days(as_of, int((remaining / daily_rate).to_integral_value(rounding=ROUND_CEILING)))
        finish = planned_finish(workplace, scope, first_report.get(scope.pk))
        tally = tallies[scope.pk]
        results.append(
            {
                "scope": scope.pk,
                "work_type": scope.work_type_id,
                "work_type_name": scope.work_type.name,
                "measure_symbol": scope.work_type.measure.symbol,
                "planned": amount(scope.planned_quantity),
                "done": amount(done),
                "remaining": amount(max(remaining, ZERO)),
                "percent": amount(min(done / scope.planned_quantity * 100, Decimal("100"))),
                "recent_daily_rate": amount(daily_rate),
                "forecast_finish": str(forecast) if forecast else None,
                "planned_finish": str(finish) if finish else None,
                "status": scope_status(remaining, first_report.get(scope.pk), daily_rate, forecast, finish),
                **tally.pace(),
                "weekly": weekly_series(weekly[scope.pk], first_week, WEEKS_SHOWN),
                "by_team": [
                    {
                        "team": team_id,
                        "team_number": teams[team_id].number,
                        "team_name": teams[team_id].name,
                        "quantity": amount(team_tally.quantity),
                        "share_percent": per(team_tally.quantity * 100, tally.quantity),
                        **team_tally.pace(),
                    }
                    for team_id, team_tally in sorted(by_team[scope.pk].items(), key=lambda item: -item[1].quantity)
                ],
            }
        )
    return {"as_of": str(as_of), "recent_working_days": RECENT_WORKING_DAYS, "scopes": results}


def team_performance(team, start, end):
    rows = report_rows(SiteReport.objects.filter(team=team, work_date__gte=start, work_date__lte=end))
    shares = crew_shares(rows)
    work_types = {
        work_type.pk: work_type
        for work_type in WorkType.objects.filter(pk__in={work_type_of(row) for row in rows}).select_related("measure")
    }
    first_week = week_start(start)
    weeks = (week_start(end) - first_week).days // 7 + 1
    tallies = defaultdict(Tally)
    weekly = defaultdict(lambda: defaultdict(Decimal))
    projects = defaultdict(lambda: {"reports": 0, "last_report": None})
    for row in rows:
        work_type_id = work_type_of(row)
        project = projects[row["workplace_id"]]
        project["reports"] += 1
        project["last_report"] = max(filter(None, [project["last_report"], row["work_date"]]))
        if work_type_id is None:
            continue
        tallies[work_type_id].add(row, shares.get(row["id"]))
        weekly[work_type_id][week_start(row["work_date"])] += row["quantity"] or ZERO
    names = dict(Workplace.objects.filter(pk__in=projects.keys()).values_list("pk", "name"))
    return {
        "team": team.pk,
        "from": str(start),
        "to": str(end),
        "days_reported": len({row["work_date"] for row in rows}),
        "crew_days": CrewAttendance.objects.filter(team=team, work_date__gte=start, work_date__lte=end).count(),
        "work_types": [
            {
                "work_type": work_type_id,
                "name": work_types[work_type_id].name,
                "measure_symbol": work_types[work_type_id].measure.symbol,
                "quantity": amount(tally.quantity),
                **tally.pace(),
                "weekly": weekly_series(weekly[work_type_id], first_week, weeks),
            }
            for work_type_id, tally in sorted(tallies.items(), key=lambda item: work_types[item[0]].name)
        ],
        "projects": [
            {"workplace": workplace_id, "name": names.get(workplace_id, ""), **values, "last_report": str(values["last_report"])}
            for workplace_id, values in sorted(projects.items(), key=lambda item: item[1]["last_report"], reverse=True)
        ],
    }


def portfolio(workplaces, as_of):
    results = []
    for workplace in workplaces.filter(status=Workplace.Status.ACTIVE).order_by("name"):
        scopes = project_progress(workplace, as_of)["scopes"]
        statuses = {scope["status"] for scope in scopes}
        forecasts = [scope["forecast_finish"] for scope in scopes if scope["forecast_finish"]]
        results.append(
            {
                "workplace": workplace.pk,
                "name": workplace.name,
                "status": next((status for status in STATUS_ORDER if status in statuses), "no_scopes"),
                "scopes_behind": sum(1 for scope in scopes if scope["status"] == "behind"),
                "forecast_finish": max(forecasts) if forecasts else None,
                "scopes": [
                    {
                        "scope": scope["scope"],
                        "work_type_name": scope["work_type_name"],
                        "measure_symbol": scope["measure_symbol"],
                        "percent": scope["percent"],
                        "status": scope["status"],
                    }
                    for scope in scopes
                ],
            }
        )
    return {"as_of": str(as_of), "results": results}
