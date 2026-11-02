"""Material use per work type: expected from norms × measured progress, actual from consumption."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from inventory.models import Location, StockLot, StockMovement, WorkTypeMaterial
from operations.progress import amount
from operations.services import scopes_with_progress

ZERO = Decimal("0.00")


def material_usage(workplace):
    scopes = list(scopes_with_progress(workplace.scopes.select_related("work_type__measure")))
    norms = defaultdict(list)
    for norm in WorkTypeMaterial.objects.filter(work_type__in=[scope.work_type_id for scope in scopes]).select_related("item"):
        norms[norm.work_type_id].append(norm)
    site = Location.objects.filter(workplace=workplace).first()
    on_site = {}
    if site is not None:
        on_site = dict(
            StockLot.objects.filter(location=site).values("item_id").annotate(total=Sum("quantity")).values_list("item_id", "total")
        )
    used = defaultdict(Decimal)
    unassigned = defaultdict(Decimal)
    items = {}
    consumed = StockMovement.objects.filter(workplace=workplace, kind=StockMovement.Kind.CONSUME).select_related("lot__item")
    for movement in consumed:
        items[movement.lot.item_id] = movement.lot.item
        if movement.scope_id:
            used[(movement.scope_id, movement.lot.item_id)] += movement.quantity
        else:
            unassigned[movement.lot.item_id] += movement.quantity

    need = defaultdict(Decimal)
    scope_rows = []
    for scope in scopes:
        done = scope.done_total
        remaining = max(scope.planned_quantity - done, ZERO)
        materials = []
        for norm in norms[scope.work_type_id]:
            items[norm.item_id] = norm.item
            expected = done * norm.quantity_per_unit
            actual = used[(scope.pk, norm.item_id)]
            still_needed = remaining * norm.quantity_per_unit
            need[norm.item_id] += still_needed
            materials.append(
                {
                    "item": norm.item_id,
                    "item_name": norm.item.name,
                    "unit": norm.item.unit,
                    "per_unit": str(norm.quantity_per_unit.normalize()),
                    "expected": amount(expected),
                    "actual": amount(actual),
                    "variance": amount(actual - expected),
                    "variance_percent": amount((actual - expected) / expected * 100) if expected else None,
                    "still_needed": amount(still_needed),
                }
            )
        scope_rows.append(
            {
                "scope": scope.pk,
                "work_type_name": scope.work_type.name,
                "measure_symbol": scope.work_type.measure.symbol,
                "done": amount(done),
                "remaining": amount(remaining),
                "materials": materials,
            }
        )

    item_ids = set(need) | set(on_site) | set(unassigned)
    missing = [item_id for item_id in item_ids if item_id not in items]
    for lot in StockLot.objects.filter(item_id__in=missing).select_related("item"):
        items[lot.item_id] = lot.item
    return {
        "site_location": site.pk if site else None,
        "scopes": scope_rows,
        "items": [
            {
                "item": item_id,
                "item_name": items[item_id].name,
                "unit": items[item_id].unit,
                "on_site": amount(on_site.get(item_id, ZERO)),
                "still_needed": amount(need[item_id]) if item_id in need else None,
                "shortage": amount(max(need[item_id] - on_site.get(item_id, ZERO), ZERO)) if item_id in need else None,
            }
            for item_id in sorted(item_ids, key=lambda key: items[key].name)
        ],
        "unassigned_use": [
            {"item": item_id, "item_name": items[item_id].name, "unit": items[item_id].unit, "quantity": amount(total)}
            for item_id, total in unassigned.items()
        ],
    }
