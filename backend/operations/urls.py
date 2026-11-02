from django.urls import path
from rest_framework.routers import DefaultRouter

from operations.views import (
    DurationUnitViewSet,
    ProgressOverviewView,
    ProjectScopeViewSet,
    SheetColumnViewSet,
    SiteReportViewSet,
    WorkKindViewSet,
    WorkMeasureViewSet,
    WorkplaceTeamViewSet,
    WorkplaceViewSet,
    WorkTypeCategoryViewSet,
    WorkTypeViewSet,
)

router = DefaultRouter()
router.register("projects", WorkplaceViewSet, basename="project")
router.register("workplaces", WorkplaceViewSet, basename="workplace")
router.register("workplace-teams", WorkplaceTeamViewSet, basename="workplace-team")
router.register("project-scopes", ProjectScopeViewSet, basename="project-scope")
router.register("sheet-columns", SheetColumnViewSet, basename="sheet-column")
router.register("duration-units", DurationUnitViewSet, basename="duration-unit")
router.register("work-kinds", WorkKindViewSet, basename="work-kind")
router.register("work-measures", WorkMeasureViewSet, basename="work-measure")
router.register("work-type-categories", WorkTypeCategoryViewSet, basename="work-type-category")
router.register("work-types", WorkTypeViewSet, basename="work-type")
router.register("site-reports", SiteReportViewSet, basename="site-report")

urlpatterns = [path("progress/", ProgressOverviewView.as_view(), name="progress-overview"), *router.urls]
