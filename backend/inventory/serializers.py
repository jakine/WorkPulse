from decimal import Decimal

from rest_framework import serializers

from inventory.models import (
    Location,
    MaterialRequest,
    MaterialRequestLine,
    StockItem,
    StockLevel,
    StockLot,
    StockMovement,
    StockType,
    WorkTypeMaterial,
)


class StockTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockType
        fields = ["id", "name", "requires_expiration"]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "kind", "workplace"]
        read_only_fields = ["kind", "workplace"]


class StockItemSerializer(serializers.ModelSerializer):
    stock_type_name = serializers.CharField(source="stock_type.name", read_only=True)
    requires_expiration = serializers.BooleanField(source="stock_type.requires_expiration", read_only=True)

    class Meta:
        model = StockItem
        fields = ["id", "stock_type", "stock_type_name", "requires_expiration", "name", "unit"]

    def validate_stock_type(self, stock_type):
        if stock_type.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Stock type must belong to this company.")
        return stock_type


class StockLotSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    requires_expiration = serializers.BooleanField(
        source="item.stock_type.requires_expiration",
        read_only=True,
    )

    class Meta:
        model = StockLot
        fields = [
            "id",
            "item",
            "item_name",
            "unit",
            "location",
            "location_name",
            "quantity",
            "expires_on",
            "received_on",
            "requires_expiration",
        ]
        read_only_fields = ["quantity"]

    def validate(self, attrs):
        item = attrs.get("item")
        location = attrs.get("location")
        company = self.context["request"].company
        if item is not None and item.company_id != company.id:
            raise serializers.ValidationError({"item": "Item must belong to this company."})
        if location is not None and location.company_id != company.id:
            raise serializers.ValidationError({"location": "Location must belong to this company."})
        if item is not None and item.stock_type.requires_expiration and not attrs.get("expires_on"):
            raise serializers.ValidationError({"expires_on": "This stock type requires an expiration date."})
        return attrs


class StockLotCreateSerializer(StockLotSerializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta(StockLotSerializer.Meta):
        read_only_fields = []


class StockMovementSerializer(serializers.ModelSerializer):
    lot_item_name = serializers.CharField(source="lot.item.name", read_only=True)
    from_location_name = serializers.CharField(source="from_location.name", read_only=True)
    to_location_name = serializers.CharField(source="to_location.name", read_only=True)
    workplace_name = serializers.CharField(source="workplace.name", read_only=True)
    scope_name = serializers.CharField(source="scope.work_type.name", read_only=True, allow_null=True)
    unit = serializers.CharField(source="lot.item.unit", read_only=True)
    recorded_by_email = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "lot",
            "lot_item_name",
            "destination_lot",
            "kind",
            "quantity",
            "from_location",
            "from_location_name",
            "to_location",
            "to_location_name",
            "workplace",
            "workplace_name",
            "scope",
            "scope_name",
            "unit",
            "material_request",
            "happened_on",
            "note",
            "recorded_by_email",
            "created_at",
        ]
        read_only_fields = ["destination_lot", "from_location", "material_request", "created_at"]

    def get_recorded_by_email(self, obj):
        return obj.recorded_by.email if obj.recorded_by_id else ""

    def validate_scope(self, scope):
        if scope is not None and scope.workplace.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Work type must belong to this company.")
        return scope

    happened_on = serializers.DateField(required=False)


class WorkTypeMaterialSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    measure_symbol = serializers.CharField(source="work_type.measure.symbol", read_only=True)

    class Meta:
        model = WorkTypeMaterial
        fields = ["id", "work_type", "work_type_name", "measure_symbol", "item", "item_name", "unit", "quantity_per_unit"]

    def validate(self, attrs):
        company = self.context["request"].company
        work_type = attrs.get("work_type") or self.instance.work_type
        item = attrs.get("item") or self.instance.item
        if work_type.company_id != company.id or item.company_id != company.id:
            raise serializers.ValidationError("Work type and item must belong to this company.")
        existing = WorkTypeMaterial.objects.filter(work_type=work_type, item=item)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError({"item": "That item is already listed for this work type."})
        return attrs


class StockLevelSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = StockLevel
        fields = ["id", "item", "item_name", "unit", "location", "location_name", "min_quantity"]

    def validate(self, attrs):
        company = self.context["request"].company
        item = attrs.get("item") or self.instance.item
        location = attrs.get("location") or self.instance.location
        if item.company_id != company.id or location.company_id != company.id:
            raise serializers.ValidationError("Item and location must belong to this company.")
        existing = StockLevel.objects.filter(item=item, location=location)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError({"item": "A level is already set for this item here."})
        return attrs


class MaterialRequestLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)

    class Meta:
        model = MaterialRequestLine
        fields = ["id", "item", "item_name", "unit", "quantity", "fulfilled_quantity"]
        read_only_fields = ["fulfilled_quantity"]


class MaterialRequestSerializer(serializers.ModelSerializer):
    lines = MaterialRequestLineSerializer(many=True)
    workplace_name = serializers.CharField(source="workplace.name", read_only=True)
    requested_by_email = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = MaterialRequest
        fields = [
            "id",
            "workplace",
            "workplace_name",
            "requested_by",
            "requested_by_email",
            "needed_by",
            "status",
            "status_label",
            "note",
            "decision_note",
            "lines",
            "created_at",
        ]
        read_only_fields = ["requested_by", "status", "decision_note", "created_at"]

    def get_requested_by_email(self, obj):
        return obj.requested_by.email if obj.requested_by_id else ""


class FulfilPickSerializer(serializers.Serializer):
    line = serializers.IntegerField(min_value=1)
    lot = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class FulfilSerializer(serializers.Serializer):
    picks = FulfilPickSerializer(many=True)
    happened_on = serializers.DateField(required=False)


class RejectSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=300)
