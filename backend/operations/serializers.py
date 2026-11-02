from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import serializers

from companies.permissions import is_team_lead
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
from operations.services import days_for, done_for_scope, measure_symbol_for, prepare_sheet_column, prepare_site_report
from sitelog.services import ensure_day_open
from workforce.models import Team
from workforce.services import ranges_overlap


class WorkplaceSerializer(serializers.ModelSerializer):
    work_type_name = serializers.CharField(source="work_type.name", read_only=True, allow_null=True)
    work_type_category_name = serializers.CharField(source="work_type.category.name", read_only=True, allow_null=True)
    measure_symbol = serializers.CharField(source="work_type.measure.symbol", read_only=True, allow_null=True)
    length_unit_name = serializers.CharField(source="length_unit.name", read_only=True, allow_null=True)
    length_days = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    remaining_days = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    done_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    days_worked = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    progress_percent = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True, allow_null=True)
    teams_needed = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Workplace
        fields = [
            "id",
            "name",
            "address",
            "status",
            "start_date",
            "end_date",
            "length_count",
            "length_unit",
            "length_unit_name",
            "length_days",
            "remaining_days",
            "work_type",
            "work_type_name",
            "work_type_category_name",
            "measure_symbol",
            "planned_quantity",
            "done_quantity",
            "days_worked",
            "remaining_quantity",
            "progress_percent",
            "teams_needed",
        ]

    def validate_work_type(self, work_type):
        if work_type is None:
            return work_type
        if work_type.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Work type must belong to this company.")
        return work_type

    def validate_length_unit(self, length_unit):
        if length_unit is None:
            return length_unit
        if length_unit.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Duration unit must belong to this company.")
        return length_unit

    def validate(self, attrs):
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "End date must be on or after the start date."})
        length_count = attrs.get("length_count", getattr(self.instance, "length_count", None))
        length_unit = attrs.get("length_unit", getattr(self.instance, "length_unit", None))
        if bool(length_count) != bool(length_unit):
            raise serializers.ValidationError(
                {"length_unit": "Set both the project length and its duration unit."}
            )
        planned = attrs.get("planned_quantity", getattr(self.instance, "planned_quantity", None))
        if planned is not None and planned <= 0:
            raise serializers.ValidationError({"planned_quantity": "Planned amount must be greater than zero."})
        return attrs

    def to_representation(self, instance):
        days = getattr(instance, "days_worked", None)
        if days is None:
            days = instance.reports.aggregate(days=Coalesce(Sum("days"), Decimal("0.00")))["days"]
        instance.days_worked = days or Decimal("0.00")
        instance.length_days = days_for(instance.length_count, instance.length_unit)
        instance.remaining_days = (
            instance.length_days - instance.days_worked if instance.length_days is not None else None
        )
        scopes = list(instance.scopes.all())
        instance.teams_needed = sum((scope.teams_needed or 0) for scope in scopes) or None
        if scopes:
            measure_ids = {scope.work_type.measure_id for scope in scopes}
            if len(measure_ids) > 1:
                instance.done_quantity = None
                instance.remaining_quantity = None
                instance.progress_percent = None
            else:
                planned = sum((scope.planned_quantity for scope in scopes), Decimal("0.00"))
                done = sum((done_for_scope(scope) for scope in scopes), Decimal("0.00"))
                instance.done_quantity = done
                instance.remaining_quantity = planned - done
                instance.progress_percent = (done / planned * Decimal("100")).quantize(Decimal("0.01")) if planned else None
                instance.measure_symbol = scopes[0].work_type.measure.symbol
        else:
            done = getattr(instance, "done_quantity", None)
            if done is None:
                done = instance.reports.aggregate(done=Coalesce(Sum("quantity"), Decimal("0.00")))["done"]
            instance.done_quantity = done or Decimal("0.00")
            if instance.planned_quantity:
                instance.remaining_quantity = instance.planned_quantity - instance.done_quantity
                instance.progress_percent = (
                    instance.done_quantity / instance.planned_quantity * Decimal("100")
                ).quantize(Decimal("0.01"))
            else:
                instance.remaining_quantity = None
                instance.progress_percent = None
        return super().to_representation(instance)


class AsOfSerializer(serializers.Serializer):
    as_of = serializers.DateField(required=False)


class PeriodSerializer(serializers.Serializer):
    """Reads ?from=&to= (``from`` cannot be a class attribute name)."""

    def get_fields(self):
        return {"from": serializers.DateField(required=False), "to": serializers.DateField(required=False)}


class DateRangeSerializer(serializers.Serializer):
    active_from = serializers.DateField(required=False)
    active_to = serializers.DateField(required=False)

    def validate(self, attrs):
        start, end = attrs.get("active_from"), attrs.get("active_to")
        if start and end and end < start:
            raise serializers.ValidationError({"active_to": "The end of the range must be on or after its start."})
        return attrs


class WorkplaceTeamSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_number = serializers.IntegerField(source="team.number", read_only=True)
    worker_count = serializers.IntegerField(source="team.worker_count", read_only=True)
    lead_note = serializers.CharField(source="team.lead_note", read_only=True)
    lead_user = serializers.IntegerField(source="team.lead_user_id", read_only=True, allow_null=True)
    lead_user_email = serializers.SerializerMethodField()
    workplace_name = serializers.CharField(source="workplace.name", read_only=True)

    class Meta:
        model = WorkplaceTeam
        fields = [
            "id",
            "workplace",
            "workplace_name",
            "team",
            "team_name",
            "team_number",
            "worker_count",
            "lead_note",
            "lead_user",
            "lead_user_email",
            "start_date",
            "end_date",
        ]

    def get_lead_user_email(self, obj):
        if obj.team.lead_user_id is None:
            return ""
        return obj.team.lead_user.email

    def validate(self, attrs):
        workplace = attrs.get("workplace") or self.instance.workplace
        team = attrs.get("team") or self.instance.team
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        company = self.context["request"].company
        if workplace.company_id != company.id:
            raise serializers.ValidationError({"workplace": "Project must belong to this company."})
        if team.company_id != company.id:
            raise serializers.ValidationError({"team": "Team must belong to this company."})
        if end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "End date must be on or after the start date."})
        existing = WorkplaceTeam.objects.filter(workplace=workplace, team=team)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        for row in existing:
            if ranges_overlap(row.start_date, row.end_date, start_date, end_date):
                raise serializers.ValidationError("This team is already on that project for those dates.")
        return attrs


class WorkKindSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkKind
        fields = ["id", "name", "position"]

    def validate_name(self, name):
        name = name.strip()
        existing = WorkKind.objects.filter(company=self.context["request"].company, name__iexact=name)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("A kind with that name already exists.")
        return name


class KindReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class DurationUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = DurationUnit
        fields = ["id", "name", "symbol", "days_per_unit", "timeline_step", "position"]

    def validate_name(self, name):
        name = name.strip()
        existing = DurationUnit.objects.filter(company=self.context["request"].company, name__iexact=name)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("A duration unit with that name already exists.")
        return name

    def validate_symbol(self, symbol):
        symbol = symbol.strip()
        if not symbol:
            raise serializers.ValidationError("Enter a symbol, such as day or week.")
        return symbol

    def validate_days_per_unit(self, days_per_unit):
        if days_per_unit is None or days_per_unit <= 0:
            raise serializers.ValidationError("Days per unit must be greater than zero.")
        return days_per_unit


class ProjectScopeSerializer(serializers.ModelSerializer):
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    work_type_category_name = serializers.CharField(source="work_type.category.name", read_only=True)
    measure_symbol = serializers.CharField(source="work_type.measure.symbol", read_only=True)
    length_unit_name = serializers.CharField(source="length_unit.name", read_only=True, allow_null=True)
    length_days = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    done_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    teams_placed = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProjectScope
        fields = [
            "id",
            "workplace",
            "work_type",
            "work_type_name",
            "work_type_category_name",
            "measure_symbol",
            "planned_quantity",
            "done_quantity",
            "remaining_quantity",
            "length_count",
            "length_unit",
            "length_unit_name",
            "length_days",
            "teams_needed",
            "teams_placed",
            "position",
        ]

    def to_representation(self, instance):
        done = done_for_scope(instance)
        instance.length_days = days_for(instance.length_count, instance.length_unit)
        instance.done_quantity = done
        instance.remaining_quantity = instance.planned_quantity - done
        teams_placed = getattr(instance, "teams_placed_total", None)
        if teams_placed is None:
            teams_placed = instance.workplace.workplace_teams.count()
        instance.teams_placed = teams_placed
        return super().to_representation(instance)

    def validate_work_type(self, work_type):
        if work_type.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Work type must belong to this company.")
        return work_type

    def validate_length_unit(self, length_unit):
        if length_unit is None:
            return length_unit
        if length_unit.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Duration unit must belong to this company.")
        return length_unit

    def validate(self, attrs):
        workplace = attrs.get("workplace") or getattr(self.instance, "workplace", None)
        if workplace is None:
            raise serializers.ValidationError({"workplace": "Choose a project."})
        if workplace.company_id != self.context["request"].company.id:
            raise serializers.ValidationError({"workplace": "Project must belong to this company."})
        length_count = attrs.get("length_count", getattr(self.instance, "length_count", None))
        length_unit = attrs.get("length_unit", getattr(self.instance, "length_unit", None))
        if bool(length_count) != bool(length_unit):
            raise serializers.ValidationError({"length_unit": "Set both the scope length and its duration unit."})
        work_type = attrs.get("work_type", getattr(self.instance, "work_type", None))
        existing = ProjectScope.objects.filter(workplace=workplace, work_type=work_type)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError({"work_type": "That work type is already a line on this project."})
        return attrs


class WorkMeasureSerializer(serializers.ModelSerializer):
    kind_name = serializers.CharField(source="kind.name", read_only=True)

    class Meta:
        model = WorkMeasure
        fields = ["id", "name", "symbol", "kind", "kind_name"]

    def validate_name(self, name):
        name = name.strip()
        existing = WorkMeasure.objects.filter(company=self.context["request"].company, name__iexact=name)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("A measure with that name already exists.")
        return name

    def validate_symbol(self, symbol):
        symbol = symbol.strip()
        if not symbol:
            raise serializers.ValidationError("Enter a symbol, such as m².")
        return symbol

    def validate_kind(self, kind):
        if kind.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Kind must belong to this company.")
        return kind


class WorkTypeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkTypeCategory
        fields = ["id", "name", "position"]

    def validate_name(self, name):
        name = name.strip()
        existing = WorkTypeCategory.objects.filter(company=self.context["request"].company, name__iexact=name)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("A category with that name already exists.")
        return name


class WorkTypeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    measure_name = serializers.CharField(source="measure.name", read_only=True)
    measure_symbol = serializers.CharField(source="measure.symbol", read_only=True)
    measure_kind = serializers.CharField(source="measure.kind.name", read_only=True)

    class Meta:
        model = WorkType
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "measure",
            "measure_name",
            "measure_symbol",
            "measure_kind",
        ]

    def validate_name(self, name):
        name = name.strip()
        existing = WorkType.objects.filter(company=self.context["request"].company, name__iexact=name)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("A work type with that name already exists.")
        return name

    def validate_category(self, category):
        if category.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Category must belong to this company.")
        return category

    def validate_measure(self, measure):
        if measure.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Measure must belong to this company.")
        return measure


class SheetColumnSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    scope_name = serializers.CharField(source="scope.work_type.name", read_only=True, allow_null=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    team_number = serializers.IntegerField(source="team.number", read_only=True, allow_null=True)
    measure_symbol = serializers.CharField(read_only=True, allow_null=True)
    planned_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    done_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = SheetColumn
        fields = [
            "id",
            "workplace",
            "kind",
            "name",
            "label",
            "scope",
            "scope_name",
            "team",
            "team_name",
            "team_number",
            "measure_symbol",
            "planned_quantity",
            "done_quantity",
            "remaining_quantity",
            "position",
        ]
        read_only_fields = ["position"]

    def get_label(self, obj):
        if obj.name:
            return obj.name
        if obj.kind == SheetColumn.Kind.WORK_TYPE and obj.scope_id:
            return obj.scope.work_type.name
        if obj.kind == SheetColumn.Kind.TEAM and obj.team_id:
            return f"{obj.team.number} · {obj.team.name}"
        return obj.get_kind_display()

    def to_representation(self, instance):
        if instance.scope_id:
            done = done_for_scope(instance.scope)
            instance.measure_symbol = instance.scope.work_type.measure.symbol
            instance.planned_quantity = instance.scope.planned_quantity
            instance.done_quantity = done
            instance.remaining_quantity = instance.scope.planned_quantity - done
        else:
            instance.measure_symbol = None
            instance.planned_quantity = None
            instance.done_quantity = None
            instance.remaining_quantity = None
        return super().to_representation(instance)

    def validate(self, attrs):
        workplace = attrs.get("workplace") or getattr(self.instance, "workplace", None)
        if workplace is None:
            raise serializers.ValidationError({"workplace": "Choose a project."})
        if workplace.company_id != self.context["request"].company.id:
            raise serializers.ValidationError({"workplace": "Project must belong to this company."})
        return prepare_sheet_column(attrs, workplace, instance=self.instance)

    def create(self, validated_data):
        workplace = validated_data["workplace"]
        validated_data["position"] = workplace.sheet_columns.count()
        return super().create(validated_data)


class SheetTextCellSerializer(serializers.ModelSerializer):
    class Meta:
        model = SheetTextCell
        fields = ["id", "column", "work_date", "text"]


class SheetCellSerializer(serializers.Serializer):
    column = serializers.PrimaryKeyRelatedField(queryset=SheetColumn.objects.all())
    work_date = serializers.DateField()
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), required=False, allow_null=True)
    scope = serializers.PrimaryKeyRelatedField(queryset=ProjectScope.objects.all(), required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    text = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        workplace = self.context["workplace"]
        column = attrs["column"]
        if column.workplace_id != workplace.id:
            raise serializers.ValidationError({"column": "Column must belong to this project."})
        team = attrs.get("team") or column.team
        if column.kind == SheetColumn.Kind.WORK_TYPE:
            if team is None:
                raise serializers.ValidationError({"team": "Choose the team filling this column."})
            if team.company_id != workplace.company_id:
                raise serializers.ValidationError({"team": "Team must belong to this company."})
            if not workplace.workplace_teams.filter(team=team).exists():
                raise serializers.ValidationError({"team": "That team is not on this project."})
        if column.kind == SheetColumn.Kind.TEAM:
            team = column.team
            scope = attrs.get("scope")
            if scope is None:
                raise serializers.ValidationError({"scope": "Choose the work type for this column."})
            if scope.workplace_id != workplace.id:
                raise serializers.ValidationError({"scope": "Work type must belong to this project."})
        if team is not None and is_team_lead(self.context["request"]) and team.lead_user_id != self.context["request"].user.id:
            raise serializers.ValidationError({"team": "You can only fill reports for a team you lead."})
        return attrs


class SiteReportSerializer(serializers.ModelSerializer):
    workplace_name = serializers.CharField(source="workplace.name", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    team_number = serializers.IntegerField(source="team.number", read_only=True, allow_null=True)
    measure_symbol = serializers.SerializerMethodField()
    task_title = serializers.CharField(source="task.title", read_only=True, allow_null=True)
    scope_name = serializers.CharField(source="scope.work_type.name", read_only=True, allow_null=True)

    class Meta:
        model = SiteReport
        fields = [
            "id",
            "workplace",
            "workplace_name",
            "team",
            "team_number",
            "team_name",
            "task",
            "task_title",
            "scope",
            "scope_name",
            "work_date",
            "days",
            "quantity",
            "measure_symbol",
            "note",
        ]

    def get_measure_symbol(self, obj):
        return measure_symbol_for(task=obj.task, workplace=obj.workplace, scope=obj.scope)

    def run_validators(self, value):
        # Say the day is locked before the generic "must make a unique set" check can answer.
        workplace = value.get("workplace") or getattr(self.instance, "workplace", None)
        if workplace is not None and workplace.company_id == self.context["request"].company.id:
            ensure_day_open(workplace, value.get("work_date", getattr(self.instance, "work_date", None)))
        super().run_validators(value)

    def validate(self, attrs):
        request = self.context["request"]
        workplace = attrs.get("workplace") or getattr(self.instance, "workplace", None)
        company = request.company
        if workplace.company_id != company.id:
            raise serializers.ValidationError({"workplace": "Project must belong to this company."})
        team = attrs["team"] if "team" in attrs else getattr(self.instance, "team", None)
        if team is not None and team.company_id != company.id:
            raise serializers.ValidationError({"team": "Team must belong to this company."})
        if is_team_lead(request) and (team is None or team.lead_user_id != request.user.id):
            raise serializers.ValidationError({"team": "You can only fill reports for a team you lead."})
        task = attrs["task"] if "task" in attrs else getattr(self.instance, "task", None)
        if task is not None and task.project_id != workplace.id:
            raise serializers.ValidationError({"task": "Task must belong to this project."})
        if task is not None and task.team_id and team is not None and task.team_id != team.id:
            raise serializers.ValidationError({"task": "That task is assigned to another team."})
        return prepare_site_report(attrs, instance=self.instance)

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError("That team already has a report for that work type on this date.") from exc
