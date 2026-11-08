from django.urls import path
from rest_framework.routers import DefaultRouter

from payroll.views import (
    OwedView,
    PayAdjustmentViewSet,
    PayLineViewSet,
    PaymentViewSet,
    PayRateViewSet,
    PayRunViewSet,
    PaySettingsView,
)

router = DefaultRouter()
router.register("pay-rates", PayRateViewSet, basename="pay-rate")
router.register("pay-adjustments", PayAdjustmentViewSet, basename="pay-adjustment")
router.register("payments", PaymentViewSet, basename="payment")
router.register("pay-runs", PayRunViewSet, basename="pay-run")
router.register("pay-lines", PayLineViewSet, basename="pay-line")

urlpatterns = [
    path("pay/settings/", PaySettingsView.as_view(), name="pay-settings"),
    path("pay/owed/", OwedView.as_view(), name="pay-owed"),
    *router.urls,
]
