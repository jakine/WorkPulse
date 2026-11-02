from rest_framework.routers import DefaultRouter

from inventory.views import (
    LocationViewSet,
    MaterialRequestViewSet,
    StockItemViewSet,
    StockLevelViewSet,
    StockLotViewSet,
    StockMovementViewSet,
    StockTypeViewSet,
    WorkTypeMaterialViewSet,
)

router = DefaultRouter()
router.register("stock-types", StockTypeViewSet, basename="stock-type")
router.register("locations", LocationViewSet, basename="location")
router.register("stock-items", StockItemViewSet, basename="stock-item")
router.register("stock-lots", StockLotViewSet, basename="stock-lot")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("stock-levels", StockLevelViewSet, basename="stock-level")
router.register("work-type-materials", WorkTypeMaterialViewSet, basename="work-type-material")
router.register("material-requests", MaterialRequestViewSet, basename="material-request")

urlpatterns = router.urls
