from rest_framework import serializers

from sitelog.models import DailyLog, DailyLogIssue


class DayQuerySerializer(serializers.Serializer):
    workplace = serializers.IntegerField(min_value=1)
    date = serializers.DateField()


class DayUpdateSerializer(DayQuerySerializer):
    weather = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ReopenSerializer(DayQuerySerializer):
    reason = serializers.CharField(max_length=300)


class AttendanceSerializer(DayQuerySerializer):
    team = serializers.IntegerField(min_value=1)
    worker_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True)


class MissingQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class DailyLogSerializer(serializers.ModelSerializer):
    workplace_name = serializers.CharField(source="workplace.name", read_only=True)
    approved_by_email = serializers.SerializerMethodField()

    class Meta:
        model = DailyLog
        fields = [
            "id",
            "workplace",
            "workplace_name",
            "work_date",
            "status",
            "weather",
            "notes",
            "approved_by",
            "approved_by_email",
            "approved_at",
        ]
        read_only_fields = fields

    def get_approved_by_email(self, obj):
        return obj.approved_by.email if obj.approved_by_id else ""


class DailyLogIssueSerializer(serializers.ModelSerializer):
    workplace = serializers.IntegerField(write_only=True, required=False, min_value=1)
    work_date = serializers.DateField(write_only=True, required=False)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = DailyLogIssue
        fields = [
            "id",
            "log",
            "workplace",
            "work_date",
            "kind",
            "kind_label",
            "description",
            "hours_lost",
            "resolved",
            "created_by",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = ["log", "created_by", "created_at"]

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by_id else ""

    def validate(self, attrs):
        if self.instance is None and ("workplace" not in attrs or "work_date" not in attrs):
            raise serializers.ValidationError("Choose the project and day for this issue.")
        if self.instance is not None:
            attrs.pop("workplace", None)
            attrs.pop("work_date", None)
        return attrs
