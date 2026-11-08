from django.contrib import admin

from timesheets.models import Holiday, Leave, LeaveType, ScheduleAssignment, WorkSchedule, WorkScheduleVersion


class WorkScheduleVersionInline(admin.TabularInline):
    model = WorkScheduleVersion
    extra = 0


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ["name", "company"]
    list_filter = ["company"]
    inlines = [WorkScheduleVersionInline]


@admin.register(ScheduleAssignment)
class ScheduleAssignmentAdmin(admin.ModelAdmin):
    list_display = ["schedule", "worker", "start_date", "end_date"]
    list_filter = ["company"]


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["date", "name", "company"]
    list_filter = ["company"]


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "paid", "uses_allowance", "archived", "company"]
    list_filter = ["company"]


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ["worker", "leave_type", "start_date", "end_date", "half_day", "status"]
    list_filter = ["status", "company"]
