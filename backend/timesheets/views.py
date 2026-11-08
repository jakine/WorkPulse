from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Exists, F, OuterRef, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from companies.permissions import HasCompanyRole, is_team_lead, lead_teams, project_for
from companies.viewsets import CompanyScopedViewSet
from core.services import record_event
from operations.serializers import PeriodSerializer
from operations.models import Workplace, WorkplaceTeam
from sitelog.services import fill_from_schedule, set_worker_hours, team_on
from timesheets.leave import cancel_leave, decide_leave, leave_balances, leave_days, off_by_team
from timesheets.locks import ensure_company_open
from timesheets.models import (
    WEEKDAYS,
    Holiday,
    Leave,
    LeaveType,
    OtherWork,
    PayGroup,
    ScheduleAssignment,
    TimesheetPeriod,
    WorkSchedule,
    period_label,
)
from timesheets.periods import (
    approve_period,
    group_spans,
    last_finished_periods,
    move_to_pay_group,
    period_bounds,
    reopen_period,
)
from timesheets.schedule import WorkCalendar, week_start
from timesheets.sheet import build_timesheet, cell_json, sheet_json
from timesheets.serializers import (
    ApplyScheduleSerializer,
    CellSerializer,
    CopyHolidaysSerializer,
    FillSerializer,
    HolidaySerializer,
    LeavePreviewSerializer,
    LeaveSerializer,
    LeaveTypeSerializer,
    OtherWorkSerializer,
    PayGroupSerializer,
    PeriodApproveSerializer,
    ScheduleAssignmentSerializer,
    ScheduleHoursSerializer,
    TimesheetPeriodSerializer,
    TimesheetQuerySerializer,
    WorkScheduleSerializer,
    WorkerDaySerializer,
    YearSerializer,
)
from timesheets.services import assign_schedule, change_schedule_hours, copy_holidays, delete_other_work
from workforce.models import Team, TeamMembership, Worker
from workforce.services import active_on, overlapping, team_members_on


def target_workers(request, data):
    """None means everyone; otherwise the chosen workers or a team's members on the start date."""
    if data.get("everyone"):
        return None
    if data.get("team"):
        team = Team.objects.filter(company=request.company, pk=data["team"]).first()
        if team is None:
            raise NotFound("Team not found.")
        return list(team_members_on(team, data["start_date"]))
    ids = set(data.get("worker_ids") or [])
    workers = list(Worker.objects.filter(company=request.company, pk__in=ids))
    if len(workers) != len(ids):
        raise ValidationError({"worker_ids": "Choose workers from this company."})
    return workers


def target_label(request, data, workers):
    if workers is None:
        return "Everyone"
    if data.get("team"):
        return Team.objects.get(company=request.company, pk=data["team"]).name
    return ", ".join(worker.name for worker in workers)


class WorkScheduleViewSet(CompanyScopedViewSet):
    serializer_class = WorkScheduleSerializer
    queryset = WorkSchedule.objects.all()
    http_method_names = ["get", "post", "delete", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        default = ScheduleAssignment.objects.filter(schedule=OuterRef("pk"), worker__isnull=True, end_date__isnull=True)
        return (
            super()
            .get_queryset()
            .prefetch_related("versions")
            .annotate(
                is_default=Exists(default),
                worker_count=Count(
                    "assignments",
                    filter=Q(assignments__end_date__isnull=True, assignments__worker__isnull=False),
                ),
            )
        )

    def _fresh(self, schedule):
        return Response(self.get_serializer(self.get_queryset().get(pk=schedule.pk)).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save(company=request.company)
        response = self._fresh(schedule)
        response.status_code = 201
        return response

    @action(detail=True, methods=["post"])
    def versions(self, request, pk=None):
        """Change the hours from a date on."""
        schedule = self.get_object()
        serializer = ScheduleHoursSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        valid_from = data.get("valid_from")
        change_schedule_hours(schedule, valid_from, {name: data[name] for name in WEEKDAYS}, data["day_hours"])
        record_event(request, "schedule.changed", schedule, data={"from": str(valid_from or "")})
        return self._fresh(schedule)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        schedule = self.get_object()
        serializer = ApplyScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workers = target_workers(request, data)
        assign_schedule(request.company, schedule, workers, data["start_date"])
        record_event(
            request,
            "schedule.applied",
            schedule,
            data={"to": target_label(request, data, workers), "from": str(data["start_date"])},
        )
        return self._fresh(schedule)

    @action(detail=False, methods=["post"])
    def reset(self, request):
        """Send workers back to the company default schedule from a date."""
        serializer = ApplyScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("everyone"):
            raise ValidationError("Choose a team or some workers.")
        workers = target_workers(request, data)
        assign_schedule(request.company, None, workers, data["start_date"])
        return Response({"workers": len(workers)})


class ScheduleAssignmentViewSet(CompanyScopedViewSet):
    serializer_class = ScheduleAssignmentSerializer
    queryset = ScheduleAssignment.objects.select_related("schedule", "worker")
    http_method_names = ["get", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        worker = self.request.query_params.get("worker")
        return queryset.filter(worker_id=worker) if worker else queryset


class HolidayViewSet(CompanyScopedViewSet):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    http_method_names = ["get", "post", "delete", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        year = self.request.query_params.get("year")
        if year:
            queryset = queryset.filter(date__year=year)
        return queryset

    def perform_create(self, serializer):
        day = serializer.validated_data["date"]
        ensure_company_open(self.request.company, day, day)
        super().perform_create(serializer)

    def perform_destroy(self, instance):
        ensure_company_open(self.request.company, instance.date, instance.date)
        instance.delete()

    @action(detail=False, methods=["post"], url_path="copy-year")
    def copy_year(self, request):
        serializer = CopyHolidaysSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response({"created": copy_holidays(request.company, data["from_year"], data["to_year"])})


class LeaveTypeViewSet(CompanyScopedViewSet):
    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.all()
    pagination_class = None


def leads_worker(request, worker, day):
    return TeamMembership.objects.filter(worker=worker, team__in=lead_teams(request)).filter(active_on(day)).exists()


def leave_event(leave):
    # No type or note: whether a day off is sick leave is nobody else's business.
    return {"worker": leave.worker.name, "from": str(leave.start_date), "to": str(leave.end_date)}


class LeaveViewSet(CompanyScopedViewSet):
    serializer_class = LeaveSerializer
    queryset = Leave.objects.select_related("company", "worker", "leave_type")
    http_method_names = ["get", "post", "head", "options"]
    lead_actions = ("create", "cancel")

    def scope_for_lead(self, queryset):
        """Days off of people who were in one of the lead's teams at the time."""
        return queryset.filter(
            Q(worker__memberships__team__in=lead_teams(self.request))
            & overlapping(F("start_date"), F("end_date"), "worker__memberships__")
        ).distinct()

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("worker"):
            queryset = queryset.filter(worker_id=params["worker"])
        if params.get("status"):
            queryset = queryset.filter(status__in=params["status"].split(","))
        if params.get("from"):
            queryset = queryset.filter(end_date__gte=params["from"])
        if params.get("to"):
            queryset = queryset.filter(start_date__lte=params["to"])
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        context = self.get_serializer_context()
        if rows:
            workers = {leave.worker_id: leave.worker for leave in rows}.values()
            start = min(leave.start_date for leave in rows)
            end = max(leave.end_date for leave in rows)
            context["calendar"] = WorkCalendar(request.company, workers, start, end)
        data = self.get_serializer(rows, many=True, context=context).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    def perform_create(self, serializer):
        data = serializer.validated_data
        if is_team_lead(self.request) and not leads_worker(self.request, data["worker"], data["start_date"]):
            raise PermissionDenied("You can only ask for days off for people in your team.")
        leave = serializer.save(company=self.request.company)
        verb = "leave.approved" if leave.status == Leave.Status.APPROVED else "leave.requested"
        record_event(self.request, verb, leave, data=leave_event(leave))

    def _decide(self, request, approve):
        leave = decide_leave(self.get_object(), request.user, approve=approve)
        record_event(request, "leave.approved" if approve else "leave.rejected", leave, data=leave_event(leave))
        return Response(self.get_serializer(leave).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, True)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, False)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        leave = self.get_object()
        if is_team_lead(request) and (leave.requested_by_id != request.user.id or leave.status != Leave.Status.REQUESTED):
            raise PermissionDenied("You can only withdraw your own requests that are still waiting.")
        cancel_leave(leave, request.user)
        record_event(request, "leave.cancelled", leave, data=leave_event(leave))
        return Response(self.get_serializer(leave).data)

    @action(detail=False, methods=["get"])
    def preview(self, request):
        """Days a request would take, the holidays inside it and the vacation left after it."""
        query = LeavePreviewSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        if data["end_date"] < data["start_date"]:
            raise ValidationError({"end_date": "The last day can't be before the first."})
        worker = Worker.objects.filter(company=request.company, pk=data["worker"]).first()
        if worker is None:
            raise NotFound("Worker not found.")
        if is_team_lead(request) and not leads_worker(request, worker, data["start_date"]):
            raise PermissionDenied("You can only ask for days off for people in your team.")
        leave_type = None
        if data.get("leave_type"):
            leave_type = LeaveType.objects.filter(company=request.company, pk=data["leave_type"]).first()
        leave = Leave(
            company=request.company,
            worker=worker,
            start_date=data["start_date"],
            end_date=data["end_date"],
            half_day=data["half_day"] and data["start_date"] == data["end_date"],
        )
        calendar = WorkCalendar(request.company, [worker], leave.start_date, leave.end_date)
        days = leave_days(calendar, leave)
        left_after = None
        if leave_type is not None and leave_type.uses_allowance:
            year = leave.start_date.year
            balance = leave_balances(request.company, [worker], year, request.company.today())[0]
            this_year = leave_days(calendar, leave, end=date(year, 12, 31))
            left_after = str(Decimal(balance["left"]) - this_year)
        holidays = [
            {"date": str(day), "name": name}
            for day, name in sorted(calendar.holidays.items())
            if leave.start_date <= day <= leave.end_date
        ]
        return Response({"days": str(days), "holidays": holidays, "left_after": left_after})

    @action(detail=False, methods=["get"])
    def balances(self, request):
        query = YearSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        year = query.validated_data.get("year") or request.company.today().year
        workers = Worker.objects.filter(company=request.company).exclude(left_on__lt=date(year, 1, 1))
        workers = workers.exclude(hired_on__gt=date(year, 12, 31))
        if is_team_lead(request):
            workers = workers.filter(team__in=lead_teams(request))
        if query.validated_data.get("worker"):
            workers = workers.filter(pk=query.validated_data["worker"])
        return Response(leave_balances(request.company, workers, year, request.company.today()))

    @action(detail=False, methods=["get"], url_path="by-team")
    def by_team(self, request):
        period = PeriodSerializer(data=request.query_params)
        period.is_valid(raise_exception=True)
        start = period.validated_data.get("from") or request.company.today()
        end = period.validated_data.get("to") or start + timedelta(days=27)
        if end < start:
            raise ValidationError({"to": "The end of the range must be on or after its start."})
        return Response(off_by_team(request.company, start, end))


def lead_workers(request, queryset, start, end):
    """Workers who were in one of the lead's teams at some point between start and end."""
    stretches = TeamMembership.objects.filter(overlapping(start, end), team__in=lead_teams(request))
    return queryset.filter(pk__in=stretches.values("worker_id"))


def period_json(group, start, end):
    saved = group.periods.filter(start_date=start).select_related("approved_by").first()
    return {
        "id": saved.pk if saved else None,
        "start": str(start),
        "end": str(end),
        "label": period_label(start, end),
        "status": saved.status if saved else TimesheetPeriod.Status.OPEN,
        "approved_by_email": saved.approved_by.email if saved and saved.approved_by else "",
        "approved_at": saved.approved_at if saved else None,
        "over": end < group.company.today(),
    }


class TimesheetViewSet(viewsets.ViewSet):
    """Read for everyone in scope; only managers change hours here. Leads record hours in the daily log."""

    permission_classes = [IsAuthenticated, HasCompanyRole]

    def _worker(self, request, worker_id):
        worker = Worker.objects.filter(company=request.company, pk=worker_id).select_related("company", "team").first()
        if worker is None:
            raise NotFound("Worker not found.")
        return worker

    def _project_names(self, request, workers, start, end):
        return dict(
            Workplace.objects.filter(
                company=request.company,
                attendance__worker__in=workers,
                attendance__work_date__range=(start, end),
            )
            .values_list("id", "name")
            .distinct()
        )

    def list(self, request):
        query = TimesheetQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        today = request.company.today()
        group = None
        if data.get("pay_group"):
            group = PayGroup.objects.filter(company=request.company, pk=data["pay_group"]).first()
            if group is None:
                raise NotFound("Pay group not found.")
        if data.get("from") and data.get("to"):
            start, end = data["from"], data["to"]
        elif group is not None:
            start, end = period_bounds(group, data.get("date") or today)
        else:
            start = week_start(data.get("date") or today)
            end = start + timedelta(days=6)
        if end < start or (end - start).days > 62:
            raise ValidationError({"to": "Show between one day and two months at a time."})

        workers = (
            Worker.objects.filter(company=request.company)
            .exclude(hired_on__gt=end)
            .exclude(left_on__lt=start)
            .filter(Q(status=Worker.Status.ACTIVE) | Q(left_on__isnull=False))
            .select_related("company", "team")
        )
        spans = None
        if group is not None:
            by_worker = group_spans(group, start, end)
            spans = {worker.pk: worker_spans for worker, worker_spans in by_worker.items()}
            workers = workers.filter(pk__in=list(spans))
        if data.get("team"):
            stretches = TeamMembership.objects.filter(overlapping(start, end), team_id=data["team"])
            workers = workers.filter(pk__in=stretches.values("worker_id"))
        if data.get("worker"):
            workers = workers.filter(pk=data["worker"])
        if is_team_lead(request):
            workers = lead_workers(request, workers, start, end)
        workers = list(workers.order_by(F("team__number").asc(nulls_last=True), "name"))
        rows = build_timesheet(request.company, workers, start, end, spans)
        payload = sheet_json(request.company, rows, start, end, self._project_names(request, workers, start, end))
        if group is not None:
            payload["pay_group"] = {"id": group.pk, "name": group.name, "cycle": group.cycle}
            payload["period"] = period_json(group, start, end)
        return Response(payload)

    @action(detail=False, methods=["get"])
    def day(self, request):
        """Everything for one worker on one day, for the day panel."""
        query = WorkerDaySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        worker = self._worker(request, query.validated_data["worker"])
        day = query.validated_data["date"]
        if is_team_lead(request) and not lead_workers(request, Worker.objects.filter(pk=worker.pk), day, day).exists():
            raise NotFound("Worker not found.")
        row = build_timesheet(request.company, [worker], day, day)[0]
        team = team_on(worker, day)
        placements = []
        if team is not None:
            placements = [
                {"workplace": placement.workplace_id, "name": placement.workplace.name, "team": team.pk, "team_name": team.name}
                for placement in WorkplaceTeam.objects.filter(team=team).filter(active_on(day)).select_related("workplace")
            ]
        return Response(
            {
                "worker": worker.pk,
                "name": worker.name,
                "date": str(day),
                "holiday": row.days[0].holiday,
                "cell": cell_json(row.days[0], request.company.today(), self._project_names(request, [worker], day, day)),
                "placements": placements,
                "other_kinds": OtherWork.Kind.choices,
            }
        )

    @action(detail=False, methods=["put"])
    def cell(self, request):
        serializer = CellSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        worker = self._worker(request, data["worker"])
        workplace = project_for(request, data["workplace"]) if data.get("workplace") else None
        set_worker_hours(worker=worker, work_date=data["date"], hours=data["hours"], workplace=workplace)
        row = build_timesheet(request.company, [worker], data["date"], data["date"])[0]
        names = self._project_names(request, [worker], data["date"], data["date"])
        return Response(cell_json(row.days[0], request.company.today(), names))

    @action(detail=False, methods=["post"])
    def fill(self, request):
        serializer = FillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["to"] < data["from"] or (data["to"] - data["from"]).days > 62:
            raise ValidationError({"to": "Fill between one day and two months at a time."})
        worker = self._worker(request, data["worker"])
        return Response(fill_from_schedule(worker, data["from"], data["to"]))


class OtherWorkViewSet(CompanyScopedViewSet):
    serializer_class = OtherWorkSerializer
    queryset = OtherWork.objects.select_related("worker")
    http_method_names = ["get", "post", "delete", "head", "options"]
    pagination_class = None

    def scope_for_lead(self, queryset):
        return queryset.filter(worker__memberships__team__in=lead_teams(self.request)).distinct()

    def perform_destroy(self, instance):
        delete_other_work(instance)


class PayGroupViewSet(CompanyScopedViewSet):
    serializer_class = PayGroupSerializer
    queryset = PayGroup.objects.all()
    pagination_class = None

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(member_count=Count("assignments", filter=Q(assignments__end_date__isnull=True)))
        )

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Move workers into this group from a date."""
        group = self.get_object()
        serializer = ApplyScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("everyone"):
            raise ValidationError("Choose a team or some workers.")
        workers = target_workers(request, data)
        for worker in workers:
            move_to_pay_group(worker, group, data["start_date"])
        record_event(
            request,
            "pay_group.joined",
            group,
            data={"to": target_label(request, data, workers), "from": str(data["start_date"])},
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=group.pk)).data)

    @action(detail=True, methods=["post"], url_path="make-default")
    def make_default(self, request, pk=None):
        """New workers join the default group."""
        group = self.get_object()
        PayGroup.objects.filter(company=request.company, is_default=True).exclude(pk=group.pk).update(is_default=False)
        group.is_default = True
        group.save(update_fields=["is_default"])
        return Response(self.get_serializer(self.get_queryset().get(pk=group.pk)).data)


class TimesheetPeriodViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCompanyRole]
    serializer_class = TimesheetPeriodSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = TimesheetPeriod.objects.filter(company=self.request.company).select_related("pay_group", "approved_by")
        if self.request.query_params.get("pay_group"):
            queryset = queryset.filter(pay_group_id=self.request.query_params["pay_group"])
        return queryset

    @action(detail=False, methods=["get"])
    def due(self, request):
        return Response(last_finished_periods(request.company))

    @action(detail=False, methods=["post"])
    def approve(self, request):
        serializer = PeriodApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        group = PayGroup.objects.filter(company=request.company, pk=data["pay_group"]).first()
        if group is None:
            raise NotFound("Pay group not found.")
        period = approve_period(group, data["start_date"], data["end_date"], request.user)
        record_event(request, "period.approved", period, data={"period": period.label()})
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        period = reopen_period(self.get_object())
        record_event(request, "period.reopened", period, data={"period": period.label()})
        return Response(self.get_serializer(period).data)
