from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from inventory.models import Location, MaterialRequest, MaterialRequestLine, StockLevel, StockLot, StockMovement
from sitelog.services import ensure_day_open


def _lock_lot(lot_id):
    return (
        StockLot.objects.select_for_update()
        .select_related("item__stock_type", "location")
        .get(pk=lot_id)
    )


def _destination_lot(source, location, happened_on):
    existing = (
        StockLot.objects.select_for_update()
        .filter(item=source.item, location=location, expires_on=source.expires_on)
        .first()
    )
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return StockLot.objects.create(
                item=source.item,
                location=location,
                quantity=Decimal("0.00"),
                expires_on=source.expires_on,
                received_on=happened_on,
            )
    except IntegrityError:
        return (
            StockLot.objects.select_for_update()
            .get(item=source.item, location=location, expires_on=source.expires_on)
        )


def receive_stock(*, company, item, location, quantity, expires_on, received_on, note, user):
    if item.company_id != company.id or location.company_id != company.id:
        raise ValidationError("Stock must stay inside the active company.")
    if location.kind != Location.Kind.DEPOT:
        raise ValidationError({"location": "Stock is received into a depot."})
    if item.stock_type.company_id != company.id:
        raise ValidationError({"stock_type": "Stock type must belong to this company."})
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if item.stock_type.requires_expiration and expires_on is None:
        raise ValidationError({"expires_on": "This stock type requires an expiration date."})
    received_on = received_on or company.today()

    with transaction.atomic():
        lot = (
            StockLot.objects.select_for_update()
            .filter(item=item, location=location, expires_on=expires_on)
            .first()
        )
        if lot is None:
            try:
                with transaction.atomic():
                    lot = StockLot.objects.create(
                        item=item,
                        location=location,
                        quantity=Decimal("0.00"),
                        expires_on=expires_on,
                        received_on=received_on,
                    )
            except IntegrityError:
                lot = (
                    StockLot.objects.select_for_update()
                    .get(item=item, location=location, expires_on=expires_on)
                )
        lot.quantity += quantity
        lot.save(update_fields=["quantity"])
        movement = StockMovement.objects.create(
            company=company,
            lot=lot,
            kind=StockMovement.Kind.RECEIVE,
            quantity=quantity,
            to_location=location,
            happened_on=received_on,
            note=note or "",
            recorded_by=user,
        )
    return lot, movement


def apply_movement(
    *,
    company,
    lot,
    kind,
    quantity,
    to_location,
    workplace,
    happened_on,
    note,
    user,
    scope=None,
    material_request=None,
):
    if quantity == 0:
        raise ValidationError({"quantity": "Quantity cannot be zero."})
    if kind != StockMovement.Kind.ADJUST and quantity < 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if kind == StockMovement.Kind.ADJUST and not (note or "").strip():
        raise ValidationError({"note": "A note is required for an adjustment."})
    happened_on = happened_on or company.today()

    with transaction.atomic():
        lot = _lock_lot(lot.pk)
        if lot.item.company_id != company.id:
            raise ValidationError({"lot": "Lot must belong to this company."})
        if to_location is not None and to_location.company_id != company.id:
            raise ValidationError({"to_location": "Location must belong to this company."})
        if workplace is not None and workplace.company_id != company.id:
            raise ValidationError({"workplace": "Workplace must belong to this company."})
        if scope is not None:
            if kind != StockMovement.Kind.CONSUME:
                raise ValidationError({"scope": "Only material used on site is linked to a work type."})
            if workplace is None or scope.workplace_id != workplace.id:
                raise ValidationError({"scope": "Work type must belong to this project."})
        if kind == StockMovement.Kind.CONSUME and workplace is not None:
            ensure_day_open(workplace, happened_on)

        destination_lot = None
        from_location = None
        stored_to_location = None

        if kind == StockMovement.Kind.RECEIVE:
            if quantity <= 0:
                raise ValidationError({"quantity": "Quantity must be greater than zero."})
            lot.quantity += quantity
            stored_to_location = lot.location
        elif kind == StockMovement.Kind.CONSUME:
            if lot.quantity < quantity:
                raise ValidationError({"quantity": "Not enough stock in this lot."})
            if workplace is None:
                raise ValidationError({"workplace": "Choose the workplace that used this stock."})
            lot.quantity -= quantity
            from_location = lot.location
        elif kind == StockMovement.Kind.TRANSFER:
            if to_location is None:
                raise ValidationError({"to_location": "Choose a destination location."})
            if to_location.id == lot.location_id:
                raise ValidationError({"to_location": "Choose a different location."})
            if lot.quantity < quantity:
                raise ValidationError({"quantity": "Not enough stock in this lot."})
            lot.quantity -= quantity
            destination_lot = _destination_lot(lot, to_location, happened_on)
            destination_lot.quantity += quantity
            destination_lot.save(update_fields=["quantity"])
            from_location = lot.location
            stored_to_location = to_location
            if workplace is None and to_location.workplace_id:
                workplace = to_location.workplace
        elif kind == StockMovement.Kind.ADJUST:
            updated = lot.quantity + quantity
            if updated < 0:
                raise ValidationError({"quantity": "Adjustment would make the quantity negative."})
            lot.quantity = updated
            from_location = lot.location
        else:
            raise ValidationError({"kind": "Unknown movement."})

        lot.save(update_fields=["quantity"])
        movement = StockMovement.objects.create(
            company=company,
            lot=lot,
            destination_lot=destination_lot,
            kind=kind,
            quantity=quantity,
            from_location=from_location,
            to_location=stored_to_location,
            workplace=workplace,
            scope=scope,
            material_request=material_request,
            happened_on=happened_on,
            note=note or "",
            recorded_by=user,
        )
    return movement


def stock_on_hand(company):
    rows = (
        StockLot.objects.filter(item__company=company)
        .values("item_id", "location_id")
        .annotate(total=Sum("quantity"))
    )
    return {(row["item_id"], row["location_id"]): row["total"] for row in rows}


def low_stock(company):
    on_hand = stock_on_hand(company)
    levels = StockLevel.objects.filter(item__company=company).select_related("item", "location")
    return [
        (level, on_hand.get((level.item_id, level.location_id), Decimal("0.00")))
        for level in levels
        if on_hand.get((level.item_id, level.location_id), Decimal("0.00")) < level.min_quantity
    ]


def create_material_request(*, company, workplace, user, lines, needed_by=None, note=""):
    if not lines:
        raise ValidationError({"lines": "Add at least one item."})
    items = [line["item"] for line in lines]
    if any(item.company_id != company.id for item in items):
        raise ValidationError({"lines": "Items must belong to this company."})
    if len({item.pk for item in items}) != len(items):
        raise ValidationError({"lines": "List each item once."})
    with transaction.atomic():
        request = MaterialRequest.objects.create(
            company=company,
            workplace=workplace,
            requested_by=user,
            needed_by=needed_by,
            note=(note or "").strip(),
        )
        MaterialRequestLine.objects.bulk_create(
            MaterialRequestLine(request=request, item=line["item"], quantity=line["quantity"]) for line in lines
        )
    return request


def _ensure_request_open(request):
    if request.status in (MaterialRequest.Status.FULFILLED, MaterialRequest.Status.REJECTED):
        raise ValidationError(f"This request is already {request.get_status_display().lower()}.")


def fulfil_request(*, company, request, user, picks, happened_on=None):
    """Send stock to the project's site: each pick is (line, lot, quantity) and becomes a transfer."""
    _ensure_request_open(request)
    site = Location.objects.filter(workplace=request.workplace).first()
    if site is None:
        raise ValidationError("This project has no site location.")
    if not picks:
        raise ValidationError({"picks": "Choose what to send."})
    with transaction.atomic():
        for line, lot, quantity in picks:
            if line.request_id != request.pk:
                raise ValidationError({"picks": "That line belongs to another request."})
            if lot.item_id != line.item_id:
                raise ValidationError({"picks": f"Pick a lot of {line.item.name}."})
            if lot.location_id == site.pk:
                raise ValidationError({"picks": "That stock is already on this site."})
            apply_movement(
                company=company,
                lot=lot,
                kind=StockMovement.Kind.TRANSFER,
                quantity=quantity,
                to_location=site,
                workplace=request.workplace,
                happened_on=happened_on,
                note=f"Material request #{request.pk}",
                user=user,
                material_request=request,
            )
            line.fulfilled_quantity += quantity
            line.save(update_fields=["fulfilled_quantity"])
        lines = MaterialRequestLine.objects.filter(request=request)
        complete = all(line.fulfilled_quantity >= line.quantity for line in lines)
        request.status = MaterialRequest.Status.FULFILLED if complete else MaterialRequest.Status.PARTLY_FULFILLED
        request.save(update_fields=["status", "updated_at"])
    return request


def reject_request(request, note):
    _ensure_request_open(request)
    request.status = MaterialRequest.Status.REJECTED
    request.decision_note = (note or "").strip()
    request.save(update_fields=["status", "decision_note", "updated_at"])
    return request
