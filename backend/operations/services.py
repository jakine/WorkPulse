from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from inventory.models import Location
from operations.models import (
    DurationUnit,
    ProjectScope,
    SheetColumn,
    SheetTextCell,
    SiteReport,
    WorkKind,
    WorkMeasure,
    WorkTypeCategory,
    Workplace,
    WorkplaceTeam,
)
from sitelog.services import ensure_day_open
from workforce.services import active_on

DEFAULT_KINDS = ("Area", "Volume", "Length", "Count", "Weight", "Time")

DEFAULT_MEASURES = (
    ("Square meters", "m²", "Area"),
    ("Cubic meters", "m³", "Volume"),
    ("Linear meters", "m", "Length"),
    ("Pieces", "pcs", "Count"),
    ("Tonnes", "t", "Weight"),
    ("Days", "days", "Time"),
)


def create_default_kinds(company):
    return [
        WorkKind.objects.get_or_create(
            company=company,
            name=name,
            defaults={"position": position},
        )[0]
        for position, name in enumerate(DEFAULT_KINDS)
    ]


def create_default_measures(company):
    kinds = {kind.name: kind for kind in create_default_kinds(company)}
    return [
        WorkMeasure.objects.get_or_create(
            company=company,
            name=name,
            defaults={"symbol": symbol, "kind": kinds[kind_name]},
        )[0]
        for name, symbol, kind_name in DEFAULT_MEASURES
    ]


DEFAULT_DURATION_UNITS = (
    ("Day", "day", Decimal("1.00"), DurationUnit.TimelineStep.DAY),
    ("Week", "week", Decimal("7.00"), DurationUnit.TimelineStep.WEEK),
    ("Month", "month", Decimal("30.00"), DurationUnit.TimelineStep.MONTH),
)


def create_default_duration_units(company):
    return [
        DurationUnit.objects.get_or_create(
            company=company,
            name=name,
            defaults={"symbol": symbol, "days_per_unit": days, "timeline_step": step, "position": position},
        )[0]
        for position, (name, symbol, days, step) in enumerate(DEFAULT_DURATION_UNITS)
    ]


def default_duration_unit(company, symbol="day"):
    create_default_duration_units(company)
    return DurationUnit.objects.get(company=company, symbol=symbol)


def days_for(count, unit):
    if not count or unit is None:
        return None
    return (Decimal(count) * unit.days_per_unit).quantize(Decimal("0.01"))


def reorder_duration_units(company, ids):
    units = {unit.pk: unit for unit in DurationUnit.objects.filter(company=company)}
    ordered = [units[unit_id] for unit_id in ids if unit_id in units]
    seen = {unit.pk for unit in ordered}
    ordered.extend(unit for unit in DurationUnit.objects.filter(company=company) if unit.pk not in seen)
    with transaction.atomic():
        for index, unit in enumerate(ordered):
            if unit.position != index:
                unit.position = index
                unit.save(update_fields=["position"])
    return DurationUnit.objects.filter(company=company)


def reports_matching_scope(scope):
    return SiteReport.objects.filter(
        Q(scope=scope)
        | Q(scope__isnull=True, workplace=scope.workplace, task__work_type=scope.work_type)
        | Q(
            scope__isnull=True,
            workplace=scope.workplace,
            task__isnull=True,
            workplace__work_type=scope.work_type,
        )
    )


def done_for_scope(scope):
    done = getattr(scope, "done_total", None)
    if done is not None:
        return done
    return reports_matching_scope(scope).aggregate(total=Coalesce(Sum("quantity"), Decimal("0.00")))["total"]


def scopes_with_progress(queryset):
    """Annotate done_total (same match as reports_matching_scope) and teams_placed_total in one query."""
    done = (
        SiteReport.objects.filter(workplace=OuterRef("workplace"))
        .filter(
            Q(scope=OuterRef("pk"))
            | Q(scope__isnull=True, task__work_type=OuterRef("work_type"))
            | Q(scope__isnull=True, task__isnull=True, workplace__work_type=OuterRef("work_type"))
        )
        .order_by()
        .values("workplace")
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    teams = (
        WorkplaceTeam.objects.filter(workplace=OuterRef("workplace"))
        .order_by()
        .values("workplace")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return queryset.annotate(
        done_total=Coalesce(
            Subquery(done, output_field=DecimalField(max_digits=12, decimal_places=2)),
            Decimal("0.00"),
        ),
        teams_placed_total=Coalesce(Subquery(teams, output_field=IntegerField()), 0),
    )


DEFAULT_WORK_CATEGORIES = ("General", "Site", "Structure", "Envelope", "Finishes", "MEP")


def create_default_work_categories(company):
    return [
        WorkTypeCategory.objects.get_or_create(
            company=company,
            name=name,
            defaults={"position": position},
        )[0]
        for position, name in enumerate(DEFAULT_WORK_CATEGORIES)
    ]


def default_work_category(company):
    create_default_work_categories(company)
    return WorkTypeCategory.objects.get(company=company, name="General")


def reorder_work_categories(company, ids):
    categories = {category.pk: category for category in WorkTypeCategory.objects.filter(company=company)}
    ordered = [categories[category_id] for category_id in ids if category_id in categories]
    seen = {category.pk for category in ordered}
    ordered.extend(
        category for category in WorkTypeCategory.objects.filter(company=company) if category.pk not in seen
    )
    with transaction.atomic():
        for index, category in enumerate(ordered):
            if category.position != index:
                category.position = index
                category.save(update_fields=["position"])
    return WorkTypeCategory.objects.filter(company=company)


def reorder_kinds(company, ids):
    kinds = {kind.pk: kind for kind in WorkKind.objects.filter(company=company)}
    ordered = [kinds[kind_id] for kind_id in ids if kind_id in kinds]
    seen = {kind.pk for kind in ordered}
    ordered.extend(kind for kind in WorkKind.objects.filter(company=company) if kind.pk not in seen)
    with transaction.atomic():
        for index, kind in enumerate(ordered):
            if kind.position != index:
                kind.position = index
                kind.save(update_fields=["position"])
    return WorkKind.objects.filter(company=company)


def measure_symbol_for(task=None, workplace=None, scope=None):
    work_type = getattr(scope, "work_type", None) if scope is not None else None
    if work_type is None:
        work_type = getattr(task, "work_type", None) if task is not None else None
    if work_type is None and workplace is not None:
        work_type = workplace.work_type
    if work_type is None and task is not None:
        work_type = getattr(getattr(task, "project", None), "work_type", None)
    measure = getattr(work_type, "measure", None)
    return getattr(measure, "symbol", None)


def create_headline_scope(workplace):
    if workplace.work_type_id is None or workplace.planned_quantity is None:
        return None
    if workplace.scopes.filter(work_type=workplace.work_type).exists():
        return workplace.scopes.filter(work_type=workplace.work_type).first()
    return ProjectScope.objects.create(
        workplace=workplace,
        work_type=workplace.work_type,
        planned_quantity=workplace.planned_quantity,
        length_count=workplace.length_count,
        length_unit=workplace.length_unit,
        position=workplace.scopes.count(),
    )


def create_workplace(company, **fields):
    with transaction.atomic():
        workplace = Workplace.objects.create(company=company, **fields)
        Location.objects.create(
            company=company,
            name=workplace.name,
            kind=Location.Kind.SITE,
            workplace=workplace,
        )
        create_headline_scope(workplace)
    return workplace


def placements_between(queryset, start, end):
    """Placements that cover any day from start to end (either may be None for an open side)."""
    if start is not None:
        queryset = queryset.filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
    if end is not None:
        queryset = queryset.filter(start_date__lte=end)
    return queryset


def placement_warnings(placement):
    others = placements_between(
        WorkplaceTeam.objects.filter(team_id=placement.team_id).exclude(pk=placement.pk),
        placement.start_date,
        placement.end_date,
    ).select_related("workplace", "team")
    return [
        f"{row.team.name} is also on {row.workplace.name} from {row.start_date} to {row.end_date or 'no end date'}."
        for row in others
    ]


def sync_workplace_location(workplace):
    Location.objects.filter(workplace=workplace).update(name=workplace.name)


def prepare_site_report(attrs, instance=None):
    workplace = attrs.get("workplace") or instance.workplace
    work_date = attrs.get("work_date", getattr(instance, "work_date", None))
    team = attrs["team"] if "team" in attrs else getattr(instance, "team", None)
    quantity = attrs["quantity"] if "quantity" in attrs else getattr(instance, "quantity", None)
    days = attrs.get("days", getattr(instance, "days", None))

    ensure_day_open(workplace, work_date)
    if instance is not None and (instance.workplace_id != workplace.id or instance.work_date != work_date):
        ensure_day_open(instance.workplace, instance.work_date)
    if quantity is None or quantity <= 0:
        raise ValidationError({"quantity": "Enter how much was done."})
    if days is None or days <= 0:
        raise ValidationError({"days": "Enter how many days were worked."})
    if not workplace.workplace_teams.exists():
        raise ValidationError({"team": "Place a team on this project before filling a report."})
    if team is None:
        raise ValidationError({"team": "Choose the team that did this work."})
    placements = workplace.workplace_teams.filter(team=team)
    if not placements.exists():
        raise ValidationError({"team": "That team is not on this project."})
    if work_date is not None and not placements.filter(active_on(work_date)).exists():
        raise ValidationError({"work_date": "That team is not on this project on that date."})
    scope = attrs["scope"] if "scope" in attrs else getattr(instance, "scope", None)
    if scope is not None and scope.workplace_id != workplace.id:
        raise ValidationError({"scope": "Scope must belong to this project."})
    task = attrs["task"] if "task" in attrs else getattr(instance, "task", None)
    if task is not None:
        if task.project_id != workplace.id:
            raise ValidationError({"task": "Task must belong to this project."})
        if task.team_id and team is not None and task.team_id != team.id:
            raise ValidationError({"task": "That task is assigned to another team."})
    if scope is None and task is not None:
        match = workplace.scopes.filter(work_type=task.work_type).first() if task.work_type_id else None
        if match is not None:
            attrs["scope"] = match

    existing = SiteReport.objects.filter(workplace=workplace, team=team, work_date=work_date)
    if scope is None:
        existing = existing.filter(scope__isnull=True)
    else:
        existing = existing.filter(scope=scope)
    if instance is not None:
        existing = existing.exclude(pk=instance.pk)
    if existing.exists():
        raise ValidationError("That team already has a report for that work type on this date.")
    return attrs


def find_sheet_report(workplace, team, work_date, scope):
    reports = SiteReport.objects.filter(workplace=workplace, team=team, work_date=work_date)
    if scope is None:
        return reports.filter(scope__isnull=True).first()
    return reports.filter(scope=scope).first()


def upsert_sheet_cell(*, workplace, team, work_date, scope, quantity, note=""):
    ensure_day_open(workplace, work_date)
    existing = find_sheet_report(workplace, team, work_date, scope)
    if quantity is None or quantity == "" or Decimal(str(quantity)) <= 0:
        if existing is not None:
            existing.delete()
        return None
    attrs = prepare_site_report(
        {
            "workplace": workplace,
            "team": team,
            "work_date": work_date,
            "scope": scope,
            "quantity": Decimal(str(quantity)),
            "days": existing.days if existing is not None else Decimal("1.00"),
            "note": note if note != "" else getattr(existing, "note", "") or "",
        },
        instance=existing,
    )
    if existing is None:
        try:
            return SiteReport.objects.create(
                workplace=attrs["workplace"],
                team=attrs["team"],
                work_date=attrs["work_date"],
                scope=attrs.get("scope"),
                quantity=attrs["quantity"],
                days=attrs["days"],
                note=attrs.get("note") or "",
            )
        except IntegrityError as exc:
            raise ValidationError("That team already has a report for that work type on this date.") from exc
    existing.quantity = attrs["quantity"]
    existing.days = attrs["days"]
    existing.scope = attrs.get("scope")
    existing.note = attrs.get("note") or existing.note
    existing.save(update_fields=["quantity", "days", "scope", "note"])
    return existing


def prepare_sheet_column(attrs, workplace, instance=None):
    kind = attrs.get("kind", getattr(instance, "kind", None))
    scope = attrs["scope"] if "scope" in attrs else getattr(instance, "scope", None)
    team = attrs["team"] if "team" in attrs else getattr(instance, "team", None)
    name = (attrs["name"] if "name" in attrs else getattr(instance, "name", "") or "").strip()

    if kind == SheetColumn.Kind.WORK_TYPE:
        if scope is None:
            raise ValidationError({"scope": "Choose the work type for this column."})
        if scope.workplace_id != workplace.id:
            raise ValidationError({"scope": "Work type must belong to this project."})
        attrs["scope"] = scope
        attrs["team"] = None
        attrs["name"] = name
        return attrs
    if kind == SheetColumn.Kind.TEAM:
        if team is None:
            raise ValidationError({"team": "Choose the team for this column."})
        if not workplace.workplace_teams.filter(team=team).exists():
            raise ValidationError({"team": "That team is not on this project."})
        attrs["scope"] = None
        attrs["team"] = team
        attrs["name"] = name
        return attrs
    if kind == SheetColumn.Kind.TEXT:
        if not name:
            raise ValidationError({"name": "Name this text column."})
        attrs["scope"] = None
        attrs["team"] = None
        attrs["name"] = name
        return attrs
    raise ValidationError({"kind": "Choose work type, team, or text."})


def reorder_sheet_columns(workplace, ids):
    columns = {column.pk: column for column in workplace.sheet_columns.all()}
    ordered = [columns[column_id] for column_id in ids if column_id in columns]
    seen = {column.pk for column in ordered}
    ordered.extend(column for column in workplace.sheet_columns.all() if column.pk not in seen)
    with transaction.atomic():
        for index, column in enumerate(ordered):
            if column.position != index:
                column.position = index
                column.save(update_fields=["position"])
    return workplace.sheet_columns.select_related("scope__work_type__measure", "team")


def resolve_sheet_column(column, workplace, *, team=None, scope=None):
    if column.workplace_id != workplace.id:
        raise ValidationError({"column": "Column must belong to this project."})
    if column.kind == SheetColumn.Kind.WORK_TYPE:
        if column.scope_id is None:
            raise ValidationError({"column": "This column has no work type."})
        if team is None:
            raise ValidationError({"team": "Choose the team filling this column."})
        return team, column.scope
    if column.kind == SheetColumn.Kind.TEAM:
        if column.team_id is None:
            raise ValidationError({"column": "This column has no team."})
        if scope is None:
            raise ValidationError({"scope": "Choose the work type for this column."})
        return column.team, scope
    raise ValidationError({"column": "This column stores text, not a quantity."})


def upsert_sheet_text(*, column, work_date, text):
    ensure_day_open(column.workplace, work_date)
    text = (text or "").strip()
    existing = SheetTextCell.objects.filter(column=column, work_date=work_date).first()
    if not text:
        if existing is not None:
            existing.delete()
        return None
    if existing is None:
        return SheetTextCell.objects.create(column=column, work_date=work_date, text=text)
    existing.text = text
    existing.save(update_fields=["text"])
    return existing
