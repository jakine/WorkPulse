from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from companies.permissions import HasCompanyRole, is_team_lead, lead_projects
from companies.viewsets import CompanyScopedViewSet
from core.services import record_event
from inventory.usage import material_usage
from sitelog.services import ensure_day_open
from operations.models import (
    DurationUnit,
    ProjectScope,
    SheetColumn,
    SheetTextCell,
    SiteReport,
    WorkKind,
    WorkMeasure,
    Workplace,
    WorkplaceTeam,
    WorkType,
    WorkTypeCategory,
)
from operations.progress import portfolio, project_progress
from operations.serializers import (
    AsOfSerializer,
    DateRangeSerializer,
    DurationUnitSerializer,
    KindReorderSerializer,
    ProjectScopeSerializer,
    SheetCellSerializer,
    SheetColumnSerializer,
    SheetTextCellSerializer,
    SiteReportSerializer,
    WorkKindSerializer,
    WorkMeasureSerializer,
    WorkplaceSerializer,
    WorkplaceTeamSerializer,
    WorkTypeCategorySerializer,
    WorkTypeSerializer,
)
from operations.services import (
    create_workplace,
    find_sheet_report,
    resolve_sheet_column,
    upsert_sheet_cell,
    upsert_sheet_text,
    reorder_duration_units,
    reorder_sheet_columns,
    reorder_kinds,
    placement_warnings,
    placements_between,
    reorder_work_categories,
    scopes_with_progress,
    sync_workplace_location,
)


def _with_progress(queryset):
    done = (
        SiteReport.objects.filter(workplace=OuterRef("pk"))
        .values("workplace")
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    days = (
        SiteReport.objects.filter(workplace=OuterRef("pk"))
        .values("workplace")
        .annotate(total=Sum("days"))
        .values("total")
    )
    scopes = scopes_with_progress(ProjectScope.objects.select_related("work_type__measure"))
    return queryset.select_related("work_type__category", "work_type__measure", "length_unit").prefetch_related(
        Prefetch("scopes", queryset=scopes)
    ).annotate(
        done_quantity=Coalesce(
            Subquery(done, output_field=DecimalField(max_digits=12, decimal_places=2)),
            Decimal("0.00"),
        ),
        days_worked=Coalesce(
            Subquery(days, output_field=DecimalField(max_digits=8, decimal_places=2)),
            Decimal("0.00"),
        ),
    )


def _with_scope_progress(columns):
    scopes = scopes_with_progress(ProjectScope.objects.select_related("work_type__measure"))
    return columns.prefetch_related(Prefetch("scope", queryset=scopes))


class WorkplaceViewSet(CompanyScopedViewSet):
    serializer_class = WorkplaceSerializer
    queryset = _with_progress(Workplace.objects.all())
    lead_actions = ("sheet",)

    def scope_for_lead(self, queryset):
        return queryset.filter(pk__in=lead_projects(self.request).values("pk"))

    def perform_create(self, serializer):
        workplace = create_workplace(self.request.company, **serializer.validated_data)
        serializer.instance = _with_progress(Workplace.objects.filter(pk=workplace.pk)).get()

    def perform_update(self, serializer):
        workplace = serializer.save()
        sync_workplace_location(workplace)
        serializer.instance = _with_progress(Workplace.objects.filter(pk=workplace.pk)).get()

    def retrieve(self, request, *args, **kwargs):
        workplace = self.get_object()
        data = self.get_serializer(workplace).data
        teams = workplace.workplace_teams.select_related("team__lead_user", "workplace")
        data["teams"] = WorkplaceTeamSerializer(teams, many=True, context={"request": request}).data
        scopes = scopes_with_progress(
            workplace.scopes.select_related("work_type__category", "work_type__measure", "length_unit")
        )
        data["scopes"] = ProjectScopeSerializer(scopes, many=True, context={"request": request}).data
        columns = _with_scope_progress(workplace.sheet_columns.select_related("team"))
        data["sheet_columns"] = SheetColumnSerializer(columns, many=True, context={"request": request}).data
        texts = SheetTextCell.objects.filter(column__workplace=workplace)
        data["sheet_texts"] = SheetTextCellSerializer(texts, many=True, context={"request": request}).data
        return Response(data)

    @action(detail=True, methods=["get"])
    def materials(self, request, pk=None):
        return Response(material_usage(self.get_object()))

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        workplace = self.get_object()
        query = AsOfSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(project_progress(workplace, query.validated_data.get("as_of") or request.company.today()))

    @action(detail=True, methods=["post"])
    def sheet(self, request, pk=None):
        workplace = self.get_object()
        serializer = SheetCellSerializer(data=request.data, context={"request": request, "workplace": workplace})
        serializer.is_valid(raise_exception=True)
        column = serializer.validated_data["column"]
        work_date = serializer.validated_data["work_date"]
        if column.kind == SheetColumn.Kind.TEXT:
            cell = upsert_sheet_text(
                column=column,
                work_date=work_date,
                text=serializer.validated_data.get("text", ""),
            )
            if cell is None:
                return Response({"deleted": True, "kind": "text"})
            return Response(SheetTextCellSerializer(cell, context={"request": request}).data)
        team, scope = resolve_sheet_column(
            column,
            workplace,
            team=serializer.validated_data.get("team"),
            scope=serializer.validated_data.get("scope"),
        )
        existing = find_sheet_report(workplace, team, work_date, scope)
        report = upsert_sheet_cell(
            workplace=workplace,
            team=team,
            work_date=work_date,
            scope=scope,
            quantity=serializer.validated_data.get("quantity"),
            note=serializer.validated_data.get("note", ""),
        )
        if report is None:
            if existing is not None:
                record_event(
                    request,
                    "report.deleted",
                    existing,
                    project=workplace,
                    data={"work_date": str(existing.work_date)},
                )
            return Response({"deleted": True, "kind": column.kind})
        record_event(
            request,
            "report.updated" if existing is not None else "report.created",
            report,
            project=workplace,
            data={"work_date": str(report.work_date), "quantity": str(report.quantity)},
        )
        return Response(SiteReportSerializer(report, context={"request": request}).data)


class WorkplaceTeamViewSet(CompanyScopedViewSet):
    serializer_class = WorkplaceTeamSerializer
    queryset = WorkplaceTeam.objects.select_related("workplace", "team__lead_user")
    company_lookup = "workplace__company"

    def scope_for_lead(self, queryset):
        return queryset.filter(workplace__in=lead_projects(self.request).values("pk"))

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        workplace_id = params.get("workplace")
        team_id = params.get("team")
        if workplace_id:
            queryset = queryset.filter(workplace_id=workplace_id)
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        if params.get("active_from") or params.get("active_to"):
            dates = DateRangeSerializer(data=params)
            dates.is_valid(raise_exception=True)
            queryset = placements_between(
                queryset,
                dates.validated_data.get("active_from"),
                dates.validated_data.get("active_to"),
            )
        return queryset

    def _record(self, verb, placement):
        record_event(
            self.request,
            verb,
            placement,
            project=placement.workplace,
            data={
                "team": placement.team.name,
                "start_date": str(placement.start_date),
                "end_date": str(placement.end_date) if placement.end_date else "",
            },
        )

    def perform_create(self, serializer):
        placement = serializer.save()
        self._record("team.placed", placement)
        self.warnings = placement_warnings(placement)

    def perform_update(self, serializer):
        placement = serializer.save()
        self._record("team.placement_changed", placement)
        self.warnings = placement_warnings(placement)

    def perform_destroy(self, instance):
        self._record("team.removed", instance)
        instance.delete()

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data["warnings"] = self.warnings
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        response.data["warnings"] = self.warnings
        return response


class DurationUnitViewSet(CompanyScopedViewSet):
    serializer_class = DurationUnitSerializer
    queryset = DurationUnit.objects.all()
    pagination_class = None

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = KindReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        units = reorder_duration_units(request.company, serializer.validated_data["ids"])
        return Response(DurationUnitSerializer(units, many=True, context={"request": request}).data)


class SheetColumnViewSet(CompanyScopedViewSet):
    serializer_class = SheetColumnSerializer
    queryset = _with_scope_progress(SheetColumn.objects.select_related("workplace", "team"))
    company_lookup = "workplace__company"
    pagination_class = None

    def scope_for_lead(self, queryset):
        return queryset.filter(workplace__in=lead_projects(self.request).values("pk"))

    def get_queryset(self):
        queryset = super().get_queryset()
        workplace_id = self.request.query_params.get("workplace")
        if workplace_id:
            queryset = queryset.filter(workplace_id=workplace_id)
        return queryset

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = KindReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workplace_id = request.data.get("workplace") or request.query_params.get("workplace")
        workplace = Workplace.objects.filter(pk=workplace_id, company=request.company).first()
        if workplace is None:
            return Response({"workplace": "Choose a project."}, status=400)
        columns = reorder_sheet_columns(workplace, serializer.validated_data["ids"])
        return Response(SheetColumnSerializer(columns, many=True, context={"request": request}).data)


class ProjectScopeViewSet(CompanyScopedViewSet):
    serializer_class = ProjectScopeSerializer
    queryset = scopes_with_progress(
        ProjectScope.objects.select_related(
            "workplace",
            "work_type__category",
            "work_type__measure",
            "length_unit",
        )
    )
    company_lookup = "workplace__company"

    def scope_for_lead(self, queryset):
        return queryset.filter(workplace__in=lead_projects(self.request).values("pk"))

    def get_queryset(self):
        queryset = super().get_queryset()
        workplace_id = self.request.query_params.get("workplace")
        if workplace_id:
            queryset = queryset.filter(workplace_id=workplace_id)
        return queryset


class WorkKindViewSet(CompanyScopedViewSet):
    serializer_class = WorkKindSerializer
    queryset = WorkKind.objects.all()
    pagination_class = None

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = KindReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kinds = reorder_kinds(request.company, serializer.validated_data["ids"])
        return Response(WorkKindSerializer(kinds, many=True, context={"request": request}).data)


class WorkMeasureViewSet(CompanyScopedViewSet):
    serializer_class = WorkMeasureSerializer
    queryset = WorkMeasure.objects.select_related("kind")


class WorkTypeCategoryViewSet(CompanyScopedViewSet):
    serializer_class = WorkTypeCategorySerializer
    queryset = WorkTypeCategory.objects.all()
    pagination_class = None

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = KindReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        categories = reorder_work_categories(request.company, serializer.validated_data["ids"])
        return Response(WorkTypeCategorySerializer(categories, many=True, context={"request": request}).data)


class WorkTypeViewSet(CompanyScopedViewSet):
    serializer_class = WorkTypeSerializer
    queryset = WorkType.objects.select_related("category", "measure__kind")


class SiteReportViewSet(CompanyScopedViewSet):
    serializer_class = SiteReportSerializer
    queryset = SiteReport.objects.select_related(
        "workplace__work_type__measure",
        "team",
        "task__work_type__measure",
        "scope__work_type__measure",
    )
    company_lookup = "workplace__company"
    lead_actions = ("create", "update", "partial_update")

    def scope_for_lead(self, queryset):
        return queryset.filter(workplace__in=lead_projects(self.request).values("pk"))

    def get_queryset(self):
        queryset = super().get_queryset()
        workplace_id = self.request.query_params.get("workplace")
        if workplace_id:
            queryset = queryset.filter(workplace_id=workplace_id)
        task_id = self.request.query_params.get("task")
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        return queryset

    def perform_create(self, serializer):
        report = serializer.save()
        record_event(
            self.request,
            "report.created",
            report,
            project=report.workplace,
            data={"work_date": str(report.work_date), "quantity": str(report.quantity)},
        )

    def perform_update(self, serializer):
        report = serializer.save()
        record_event(
            self.request,
            "report.updated",
            report,
            project=report.workplace,
            data={"work_date": str(report.work_date), "quantity": str(report.quantity)},
        )

    def perform_destroy(self, instance):
        ensure_day_open(instance.workplace, instance.work_date)
        record_event(
            self.request,
            "report.deleted",
            instance,
            project=instance.workplace,
            data={"work_date": str(instance.work_date)},
        )
        instance.delete()


class ProgressOverviewView(APIView):
    permission_classes = [IsAuthenticated, HasCompanyRole]

    def get(self, request):
        query = AsOfSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        workplaces = Workplace.objects.filter(company=request.company)
        if is_team_lead(request):
            workplaces = workplaces.filter(pk__in=lead_projects(request).values("pk"))
        return Response(portfolio(workplaces, query.validated_data.get("as_of") or request.company.today()))
