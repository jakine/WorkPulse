from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from companies.permissions import HasCompanyRole, is_team_lead, lead_projects, project_for
from companies.viewsets import CompanyScopedViewSet
from core.services import record_event
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
from inventory.serializers import (
    FulfilSerializer,
    LocationSerializer,
    MaterialRequestSerializer,
    RejectSerializer,
    StockLevelSerializer,
    WorkTypeMaterialSerializer,
    StockItemSerializer,
    StockLotCreateSerializer,
    StockLotSerializer,
    StockMovementSerializer,
    StockTypeSerializer,
)
from inventory.services import (
    apply_movement,
    create_material_request,
    fulfil_request,
    low_stock,
    receive_stock,
    reject_request,
)


class StockTypeViewSet(CompanyScopedViewSet):
    serializer_class = StockTypeSerializer
    queryset = StockType.objects.all()


class LocationViewSet(CompanyScopedViewSet):
    serializer_class = LocationSerializer
    queryset = Location.objects.all()
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(
            company=self.request.company,
            kind=Location.Kind.DEPOT,
            workplace=None,
        )


class StockItemViewSet(CompanyScopedViewSet):
    serializer_class = StockItemSerializer
    queryset = StockItem.objects.select_related("stock_type")


class StockLotViewSet(CompanyScopedViewSet):
    queryset = StockLot.objects.select_related("item__stock_type", "location")
    company_lookup = "item__company"
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return StockLotCreateSerializer
        return StockLotSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        expires_before = self.request.query_params.get("expires_before")
        if expires_before:
            queryset = queryset.filter(expires_on__isnull=False, expires_on__lte=expires_before)
        location_id = self.request.query_params.get("location")
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lot, _movement = receive_stock(
            company=request.company,
            item=data["item"],
            location=data["location"],
            quantity=data["quantity"],
            expires_on=data.get("expires_on"),
            received_on=data.get("received_on"),
            note=data.get("note", "") if "note" in data else "",
            user=request.user,
        )
        record_event(
            request,
            "stock.received",
            lot,
            project=lot.location.workplace,
            data={"item": lot.item.name, "quantity": str(data["quantity"]), "location": lot.location.name},
        )
        output = StockLotSerializer(lot, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class StockMovementViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, HasCompanyRole]
    serializer_class = StockMovementSerializer
    queryset = StockMovement.objects.select_related(
        "lot__item",
        "from_location",
        "to_location",
        "workplace",
        "scope__work_type",
        "recorded_by",
    )
    lead_actions = ("create",)

    def get_queryset(self):
        queryset = super().get_queryset().filter(company=self.request.company)
        params = self.request.query_params
        for param, lookup in (
            ("lot", "lot_id"),
            ("workplace", "workplace_id"),
            ("scope", "scope_id"),
            ("kind", "kind"),
            ("happened_on", "happened_on"),
        ):
            if params.get(param):
                queryset = queryset.filter(**{lookup: params[param]})
        return queryset

    def _check_lead_use(self, request, data):
        """Team leads may only record material used on the site of a project their team works on."""
        workplace = data.get("workplace")
        if data["kind"] != StockMovement.Kind.CONSUME or workplace is None:
            raise PermissionDenied("Team leads can only record material used on site.")
        if not lead_projects(request).filter(pk=workplace.pk).exists():
            raise PermissionDenied("You can only record use on projects your team works on.")
        if data["lot"].location.workplace_id != workplace.pk:
            raise PermissionDenied("Use stock that is on this project's site.")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lot = data["lot"]
        if lot.item.company_id != request.company.id:
            return Response({"lot": ["Lot must belong to this company."]}, status=status.HTTP_400_BAD_REQUEST)
        if is_team_lead(request):
            self._check_lead_use(request, data)
        movement = apply_movement(
            company=request.company,
            lot=lot,
            kind=data["kind"],
            quantity=data["quantity"],
            to_location=data.get("to_location"),
            workplace=data.get("workplace"),
            happened_on=data.get("happened_on"),
            note=data.get("note", ""),
            user=request.user,
            scope=data.get("scope"),
        )
        to_location = movement.to_location
        record_event(
            request,
            f"stock.{movement.kind}",
            movement,
            project=movement.workplace or (to_location.workplace if to_location else None),
            data={"item": lot.item.name, "quantity": str(movement.quantity)},
        )
        return Response(self.get_serializer(movement).data, status=status.HTTP_201_CREATED)


class WorkTypeMaterialViewSet(CompanyScopedViewSet):
    serializer_class = WorkTypeMaterialSerializer
    queryset = WorkTypeMaterial.objects.select_related("item", "work_type__measure")
    company_lookup = "work_type__company"
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        work_type_id = self.request.query_params.get("work_type")
        if work_type_id:
            queryset = queryset.filter(work_type_id=work_type_id)
        return queryset


class StockLevelViewSet(CompanyScopedViewSet):
    serializer_class = StockLevelSerializer
    queryset = StockLevel.objects.select_related("item", "location")
    company_lookup = "item__company"
    pagination_class = None

    @action(detail=False, methods=["get"])
    def low(self, request):
        return Response(
            [
                {**StockLevelSerializer(level, context={"request": request}).data, "on_hand": str(on_hand)}
                for level, on_hand in low_stock(request.company)
            ]
        )


class MaterialRequestViewSet(CompanyScopedViewSet):
    serializer_class = MaterialRequestSerializer
    queryset = MaterialRequest.objects.select_related("workplace", "requested_by").prefetch_related(
        Prefetch("lines", queryset=MaterialRequestLine.objects.select_related("item"))
    )
    http_method_names = ["get", "post", "head", "options"]
    lead_actions = ("create",)

    def scope_for_lead(self, queryset):
        return queryset.filter(workplace__in=lead_projects(self.request).values("pk"))

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("workplace"):
            queryset = queryset.filter(workplace_id=params["workplace"])
        if params.get("status"):
            queryset = queryset.filter(status__in=params["status"].split(","))
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workplace = project_for(request, data["workplace"].pk)
        material_request = create_material_request(
            company=request.company,
            workplace=workplace,
            user=request.user,
            lines=data["lines"],
            needed_by=data.get("needed_by"),
            note=data.get("note", ""),
        )
        record_event(request, "materials.requested", material_request, project=workplace, data={"lines": len(data["lines"])})
        return Response(self.get_serializer(self.get_queryset().get(pk=material_request.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def fulfil(self, request, pk=None):
        material_request = self.get_object()
        serializer = FulfilSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lines = {line.pk: line for line in material_request.lines.select_related("item")}
        lots = {
            lot.pk: lot
            for lot in StockLot.objects.filter(
                item__company=request.company,
                pk__in=[pick["lot"] for pick in serializer.validated_data["picks"]],
            ).select_related("item", "location")
        }
        picks = []
        for pick in serializer.validated_data["picks"]:
            if pick["line"] not in lines or pick["lot"] not in lots:
                return Response({"picks": ["Choose lines of this request and lots of this company."]}, status=400)
            picks.append((lines[pick["line"]], lots[pick["lot"]], pick["quantity"]))
        fulfil_request(
            company=request.company,
            request=material_request,
            user=request.user,
            picks=picks,
            happened_on=serializer.validated_data.get("happened_on"),
        )
        record_event(request, "materials.sent", material_request, project=material_request.workplace)
        return Response(self.get_serializer(self.get_queryset().get(pk=material_request.pk)).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        material_request = self.get_object()
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reject_request(material_request, serializer.validated_data["note"])
        record_event(request, "materials.rejected", material_request, project=material_request.workplace)
        return Response(self.get_serializer(self.get_queryset().get(pk=material_request.pk)).data)
