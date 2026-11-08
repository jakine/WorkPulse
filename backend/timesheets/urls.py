from rest_framework.routers import DefaultRouter

from timesheets.views import (
    HolidayViewSet,
    LeaveTypeViewSet,
    LeaveViewSet,
    OtherWorkViewSet,
    PayGroupViewSet,
    ScheduleAssignmentViewSet,
    TimesheetPeriodViewSet,
    TimesheetViewSet,
    WorkScheduleViewSet,
)

router = DefaultRouter()
router.register("schedules", WorkScheduleViewSet, basename="schedule")
router.register("schedule-assignments", ScheduleAssignmentViewSet, basename="schedule-assignment")
router.register("holidays", HolidayViewSet, basename="holiday")
router.register("leave-types", LeaveTypeViewSet, basename="leave-type")
router.register("days-off", LeaveViewSet, basename="day-off")
router.register("timesheets", TimesheetViewSet, basename="timesheet")
router.register("other-work", OtherWorkViewSet, basename="other-work")
router.register("pay-groups", PayGroupViewSet, basename="pay-group")
router.register("timesheet-periods", TimesheetPeriodViewSet, basename="timesheet-period")

urlpatterns = router.urls
