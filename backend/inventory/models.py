from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class StockType(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="stock_types",
    )
    name = models.CharField(max_length=200)
    requires_expiration = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_stock_type_name"),
        ]

    def __str__(self):
        return self.name


class Location(models.Model):
    class Kind(models.TextChoices):
        DEPOT = "depot", "Depot"
        SITE = "site", "Site"

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="locations",
    )
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    workplace = models.OneToOneField(
        "operations.Workplace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stock_location",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind="depot", workplace__isnull=True)
                    | models.Q(kind="site", workplace__isnull=False)
                ),
                name="location_kind_matches_workplace",
            ),
        ]

    def __str__(self):
        return self.name


class StockItem(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="stock_items",
    )
    stock_type = models.ForeignKey(
        StockType,
        on_delete=models.PROTECT,
        related_name="items",
    )
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=40)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockLot(models.Model):
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name="lots")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="lots")
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    expires_on = models.DateField(null=True, blank=True)
    received_on = models.DateField()

    class Meta:
        ordering = ["expires_on", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "location", "expires_on"],
                name="unique_lot_item_location_expiry",
                nulls_distinct=False,
            ),
        ]

    def __str__(self):
        return f"{self.item} @ {self.location}"


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        RECEIVE = "receive", "Receive"
        TRANSFER = "transfer", "Transfer"
        CONSUME = "consume", "Consume"
        ADJUST = "adjust", "Adjust"

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name="movements")
    destination_lot = models.ForeignKey(
        StockLot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incoming_movements",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    from_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="movements_out",
    )
    to_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="movements_in",
    )
    workplace = models.ForeignKey(
        "operations.Workplace",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    scope = models.ForeignKey(
        "operations.ProjectScope",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    material_request = models.ForeignKey(
        "MaterialRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )
    happened_on = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-happened_on", "-id"]

    def __str__(self):
        return f"{self.kind} {self.quantity}"


class WorkTypeMaterial(models.Model):
    """How much of an item one unit of a work type uses, e.g. 1.4 kg adhesive per m² of facade."""

    work_type = models.ForeignKey("operations.WorkType", on_delete=models.CASCADE, related_name="materials")
    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="norms")
    quantity_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )

    class Meta:
        ordering = ["item__name"]
        constraints = [
            models.UniqueConstraint(fields=["work_type", "item"], name="unique_material_per_work_type"),
        ]

    def __str__(self):
        return f"{self.item} per {self.work_type}"


class StockLevel(models.Model):
    """Warn when an item at a location drops below min_quantity."""

    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="levels")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="levels")
    min_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["location__name", "item__name"]
        constraints = [
            models.UniqueConstraint(fields=["item", "location"], name="unique_stock_level"),
        ]

    def __str__(self):
        return f"{self.item} @ {self.location} >= {self.min_quantity}"


class MaterialRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTLY_FULFILLED = "partly_fulfilled", "Partly sent"
        FULFILLED = "fulfilled", "Sent"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="material_requests",
    )
    workplace = models.ForeignKey(
        "operations.Workplace",
        on_delete=models.CASCADE,
        related_name="material_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="material_requests",
    )
    needed_by = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    note = models.CharField(max_length=300, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Request #{self.pk} for {self.workplace}"


class MaterialRequestLine(models.Model):
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name="request_lines")
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fulfilled_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["request", "item"], name="unique_item_per_material_request"),
        ]

    def __str__(self):
        return f"{self.quantity} {self.item}"
