from django.contrib import admin

from sitelog.models import CrewAttendance, DailyLog, DailyLogIssue


@admin.register(DailyLog)
class DailyLogAdmin(admin.ModelAdmin):
    list_display = ["work_date", "workplace", "status", "approved_by", "approved_at"]
    list_filter = ["status", "workplace__company"]


@admin.register(DailyLogIssue)
class DailyLogIssueAdmin(admin.ModelAdmin):
    list_display = ["created_at", "log", "kind", "description", "hours_lost", "resolved"]
    list_filter = ["kind", "resolved"]


@admin.register(CrewAttendance)
class CrewAttendanceAdmin(admin.ModelAdmin):
    list_display = ["work_date", "workplace", "team", "worker"]
    list_filter = ["workplace__company"]
