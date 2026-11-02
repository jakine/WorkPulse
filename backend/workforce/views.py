from datetime import timedelta

from django.db.models import Count, Q
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from companies.permissions import is_team_lead
from companies.viewsets import CompanyScopedViewSet
from core.services import record_event
from operations.progress import WEEKS_SHOWN, team_performance, week_start
from operations.serializers import PeriodSerializer, WorkplaceTeamSerializer
from workforce.models import Team, Worker, WorkerType
from workforce.serializers import (
    TeamMembershipSerializer,
    TeamSerializer,
    WorkerMoveSerializer,
    WorkerSerializer,
    WorkerTypeSerializer,
)
from workforce.services import move_worker


class WorkerTypeViewSet(CompanyScopedViewSet):
    serializer_class = WorkerTypeSerializer
    queryset = WorkerType.objects.all()


class TeamViewSet(CompanyScopedViewSet):
    serializer_class = TeamSerializer
    queryset = (
        Team.objects.select_related("lead_user")
        .annotate(member_count=Count("memberships", filter=Q(memberships__end_date__isnull=True), distinct=True))
        .order_by("number", "name")
    )

    def retrieve(self, request, *args, **kwargs):
        team = self.get_object()
        data = self.get_serializer(team).data
        stretches = team.memberships.select_related("worker__worker_type", "team")
        data["members"] = TeamMembershipSerializer(stretches.filter(end_date__isnull=True), many=True).data
        data["past_members"] = TeamMembershipSerializer(stretches.filter(end_date__isnull=False), many=True).data
        placements = team.workplace_assignments.select_related("workplace", "team__lead_user").order_by("-start_date")
        data["placements"] = WorkplaceTeamSerializer(placements, many=True, context={"request": request}).data
        return Response(data)

    @action(detail=True, methods=["get"])
    def performance(self, request, pk=None):
        team = self.get_object()
        if is_team_lead(request) and team.lead_user_id != request.user.id:
            raise PermissionDenied("You can only see the performance of a team you lead.")
        period = PeriodSerializer(data=request.query_params)
        period.is_valid(raise_exception=True)
        end = period.validated_data.get("to") or request.company.today()
        start = period.validated_data.get("from") or week_start(end) - timedelta(weeks=WEEKS_SHOWN - 1)
        if end < start:
            raise ValidationError({"to": "The end of the range must be on or after its start."})
        return Response(team_performance(team, start, end))


class WorkerViewSet(CompanyScopedViewSet):
    serializer_class = WorkerSerializer
    queryset = Worker.objects.select_related("team", "worker_type")

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        team_id = self.request.query_params.get("team")
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        return queryset

    def _detail(self, worker):
        data = self.get_serializer(worker).data
        stretches = worker.memberships.select_related("worker__worker_type", "team")
        data["memberships"] = TeamMembershipSerializer(stretches, many=True).data
        return data

    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        worker = self.get_object()
        serializer = WorkerMoveSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        team = serializer.validated_data["team"]
        on_date = serializer.validated_data["on_date"]
        before = worker.team.name if worker.team_id else ""
        worker = move_worker(worker, team, on_date)
        record_event(
            request,
            "worker.moved",
            worker,
            data={"from": before, "to": team.name if team else "", "on": str(on_date)},
        )
        return Response(self._detail(self.get_queryset().get(pk=worker.pk)))
