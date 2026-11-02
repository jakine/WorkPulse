from rest_framework import serializers

from core.models import ActivityEvent, Attachment


class ActivityEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True, allow_null=True)

    class Meta:
        model = ActivityEvent
        fields = [
            "id",
            "actor",
            "actor_email",
            "project",
            "project_name",
            "verb",
            "target_type",
            "target_id",
            "data",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor_id else ""


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            "id",
            "target_type",
            "target_id",
            "project",
            "original_name",
            "content_type",
            "is_image",
            "size",
            "caption",
            "uploaded_by",
            "uploaded_by_email",
            "created_at",
            "url",
        ]
        read_only_fields = fields

    def get_uploaded_by_email(self, obj):
        return obj.uploaded_by.email if obj.uploaded_by_id else ""

    def get_url(self, obj):
        return f"/api/attachments/{obj.pk}/file/"


class AttachmentUploadSerializer(serializers.Serializer):
    target_type = serializers.CharField(max_length=60)
    target_id = serializers.IntegerField(min_value=1)
    file = serializers.FileField()
    caption = serializers.CharField(max_length=300, required=False, allow_blank=True)
