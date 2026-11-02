from rest_framework.routers import DefaultRouter

from sitelog.views import DailyLogIssueViewSet, DailyLogViewSet

router = DefaultRouter()
router.register("daily-logs", DailyLogViewSet, basename="daily-log")
router.register("daily-log-issues", DailyLogIssueViewSet, basename="daily-log-issue")

urlpatterns = router.urls
