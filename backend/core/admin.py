from django.contrib import admin

from core.models import ActivityEvent, Attachment


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "company", "actor", "verb", "target_type", "target_id", "project"]
    list_filter = ["company", "verb"]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["created_at", "company", "original_name", "content_type", "size", "target_type", "target_id"]
    list_filter = ["company", "content_type"]
