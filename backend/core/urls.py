from rest_framework.routers import DefaultRouter

from core.views import ActivityEventViewSet, AttachmentViewSet

router = DefaultRouter()
router.register("activity", ActivityEventViewSet, basename="activity")
router.register("attachments", AttachmentViewSet, basename="attachment")

urlpatterns = router.urls
