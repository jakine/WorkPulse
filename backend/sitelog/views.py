from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from companies.permissions import HasCompanyRole, is_team_lead, lead_projects, project_for, visible_projects
from companies.viewsets import CompanyScopedViewSet
from core.services import record_event
from inventory.models import StockMovement
from inventory.serializers import StockMovementSerializer
from operations.models import SiteReport
from operations.serializers import SiteReportSerializer
from sitelog.models import CrewAttendance, DailyLog, DailyLogIssue
from sitelog.serializers import (
    AttendanceSerializer,
    DailyLogIssueSerializer,
    DailyLogSerializer,
    DayQuerySerializer,
    DayUpdateSerializer,
    MissingQuerySerializer,
    ReopenSerializer,
)
from sitelog.services import (
    approve_day,
    available_on,
    default_hours,
    ensure_day_open,
    log_for,
    missing_reports,
    placements_on,
    reopen_day,
    set_attendance,
    update_day,
)
from timesheets.leave import approved_off
from timesheets.schedule import WorkCalendar
from workforce.models import Team, Worker
from workforce.services import team_members_on


def off_label(leave, sees_type):
    """Leads only see the kind of day off for their own team's workers."""
    if leave is None:
        return None
    if not sees_type:
        return {"code": "", "name": "Off", "half_day": leave.half_day}
    return {"code": leave.leave_type.code, "name": leave.leave_type.name, "half_day": leave.half_day}


class DailyLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCompanyRole]
    serializer_class = DailyLogSerializer
    lead_actions = ("day", "attendance")

    def get_queryset(self):
        queryset = DailyLog.objects.filter(workplace__in=visible_projects(self.request)).select_related(
            "workplace", "approved_by"
        )
        params = self.request.query_params
        if params.get("workplace"):
            queryset = queryset.filter(workplace_id=params["workplace"])
        if params.get("from"):
            queryset = queryset.filter(work_date__gte=params["from"])
        if params.get("to"):
            queryset = queryset.filter(work_date__lte=params["to"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset

    def _day(self, request, workplace, work_date):
        log = DailyLog.objects.filter(workplace=workplace, work_date=work_date).select_related("approved_by").first()
        reports = SiteReport.objects.filter(workplace=workplace, work_date=work_date).select_related(
            "workplace__work_type__measure", "team", "task__work_type__measure", "scope__work_type__measure"
        )
        hours = {}
        attendance = list(CrewAttendance.objects.filter(workplace=workplace, work_date=work_date).select_related("worker"))
        for row in attendance:
            hours[row.team_id, row.worker_id] = row.hours
        reported = {report.team_id for report in reports}
        off = approved_off(Worker.objects.filter(company=workplace.company), work_date)
        crews = []
        for placement in placements_on(workplace, work_date):
            team = placement.team
            members = [worker for worker in team_members_on(team, work_date).order_by("name") if available_on(worker, work_date)]
            member_ids = {worker.pk for worker in members}
            extras = [row.worker for row in attendance if row.team_id == team.pk and row.worker_id not in member_ids]
            crews.append((team, members + extras, member_ids))
        everyone = {worker.pk: worker for _, crew, _ in crews for worker in crew}
        calendar = WorkCalendar(workplace.company, everyone.values(), work_date, work_date)
        teams = []
        for team, crew, member_ids in crews:
            sees_type = not is_team_lead(request) or team.lead_user_id == request.user.id
            teams.append(
                {
                    "team": team.pk,
                    "team_number": team.number,
                    "team_name": team.name,
                    "lead_user": team.lead_user_id,
                    "reported": team.pk in reported,
                    "present_count": sum(1 for worker in crew if (team.pk, worker.pk) in hours),
                    "crew": [
                        {
                            "worker": worker.pk,
                            "name": worker.name,
                            "member": worker.pk in member_ids,
                            "present": (team.pk, worker.pk) in hours,
                            "hours": str(hours[team.pk, worker.pk]) if (team.pk, worker.pk) in hours else None,
                            "expected_hours": str(default_hours(calendar, worker, work_date)),
                            "off": off_label(off.get(worker.pk), sees_type),
                        }
                        for worker in crew
                    ],
                }
            )
        issues = log.issues.select_related("created_by") if log else []
        materials = StockMovement.objects.filter(
            workplace=workplace,
            happened_on=work_date,
            kind=StockMovement.Kind.CONSUME,
        ).select_related("lot__item", "from_location", "to_location", "workplace", "scope__work_type", "recorded_by")
        return {
            "workplace": workplace.pk,
            "workplace_name": workplace.name,
            "date": str(work_date),
            "log": DailyLogSerializer(log).data if log else None,
            "status": log.status if log else DailyLog.Status.OPEN,
            "teams": teams,
            "reports": SiteReportSerializer(reports, many=True, context={"request": request}).data,
            "issues": DailyLogIssueSerializer(issues, many=True).data,
            "materials": StockMovementSerializer(materials, many=True, context={"request": request}).data,
        }

    @action(detail=False, methods=["get", "patch"])
    def day(self, request):
        if request.method == "GET":
            query = DayQuerySerializer(data=request.query_params)
            query.is_valid(raise_exception=True)
            workplace = project_for(request, query.validated_data["workplace"])
            return Response(self._day(request, workplace, query.validated_data["date"]))
        serializer = DayUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workplace = project_for(request, data["workplace"])
        update_day(workplace, data["date"], weather=data.get("weather"), notes=data.get("notes"))
        return Response(self._day(request, workplace, data["date"]))

    @action(detail=False, methods=["post"])
    def approve(self, request):
        query = DayQuerySerializer(data=request.data)
        query.is_valid(raise_exception=True)
        workplace = project_for(request, query.validated_data["workplace"])
        work_date = query.validated_data["date"]
        log = approve_day(workplace, work_date, request.user)
        record_event(request, "day.approved", log, project=workplace, data={"work_date": str(work_date)})
        return Response(self._day(request, workplace, work_date))

    @action(detail=False, methods=["post"])
    def reopen(self, request):
        serializer = ReopenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workplace = project_for(request, data["workplace"])
        log = reopen_day(workplace, data["date"])
        record_event(
            request,
            "day.reopened",
            log,
            project=workplace,
            data={"work_date": str(data["date"]), "reason": data["reason"]},
        )
        return Response(self._day(request, workplace, data["date"]))

    @action(detail=False, methods=["put"])
    def attendance(self, request):
        serializer = AttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workplace = project_for(request, data["workplace"])
        team = Team.objects.filter(company=request.company, pk=data["team"]).first()
        if team is None:
            raise NotFound("Team not found.")
        if is_team_lead(request) and team.lead_user_id != request.user.id:
            raise PermissionDenied("You can only record the crew of a team you lead.")
        workers = list(Worker.objects.filter(company=request.company, pk__in=data["worker_ids"]))
        if len(workers) != len(set(data["worker_ids"])):
            return Response({"worker_ids": ["Choose workers from this company."]}, status=400)
        set_attendance(workplace=workplace, work_date=data["date"], team=team, workers=workers, hours=data.get("hours"))
        return Response(self._day(request, workplace, data["date"]))

    @action(detail=False, methods=["get"])
    def missing(self, request):
        query = MissingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        work_date = query.validated_data.get("date") or request.company.today()
        rows = missing_reports(visible_projects(request), work_date)
        if is_team_lead(request):
            rows = [row for row in rows if row.team.lead_user_id == request.user.id]
        return Response(
            {
                "date": str(work_date),
                "results": [
                    {
                        "workplace": row.workplace_id,
                        "workplace_name": row.workplace.name,
                        "team": row.team_id,
                        "team_number": row.team.number,
                        "team_name": row.team.name,
                        "lead_user_email": row.team.lead_user.email if row.team.lead_user_id else "",
                    }
                    for row in rows
                ],
            }
        )


class DailyLogIssueViewSet(CompanyScopedViewSet):
    serializer_class = DailyLogIssueSerializer
    queryset = DailyLogIssue.objects.select_related("log__workplace", "created_by")
    company_lookup = "log__workplace__company"
    lead_actions = ("create", "update", "partial_update", "destroy")

    def scope_for_lead(self, queryset):
        return queryset.filter(log__workplace__in=lead_projects(self.request).values("pk"))

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("workplace"):
            queryset = queryset.filter(log__workplace_id=params["workplace"])
        if params.get("open") == "1":
            queryset = queryset.filter(resolved=False)
        return queryset

    def _check_author(self, issue):
        if is_team_lead(self.request) and issue.created_by_id != self.request.user.id:
            raise PermissionDenied("You can only change issues you added.")

    def perform_create(self, serializer):
        workplace = project_for(self.request, serializer.validated_data.pop("workplace"))
        work_date = serializer.validated_data.pop("work_date")
        ensure_day_open(workplace, work_date)
        issue = serializer.save(log=log_for(workplace, work_date), created_by=self.request.user)
        record_event(self.request, "issue.added", issue.log, project=workplace, data={"kind": issue.kind})

    def perform_update(self, serializer):
        self._check_author(serializer.instance)
        ensure_day_open(serializer.instance.log.workplace, serializer.instance.log.work_date)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_author(instance)
        ensure_day_open(instance.log.workplace, instance.log.work_date)
        instance.delete()
