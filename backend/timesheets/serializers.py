from decimal import Decimal

from rest_framework import serializers

from companies.permissions import is_team_lead
from companies.serializers import CompanyWorkerMixin, unique_name
from timesheets.leave import leave_days, request_leave, update_leave
from timesheets.models import (
    WEEKDAYS,
    Holiday,
    Leave,
    LeaveType,
    OtherWork,
    PayGroup,
    ScheduleAssignment,
    TimesheetPeriod,
    WorkSchedule,
    WorkScheduleVersion,
    period_label,
)
from timesheets.schedule import WorkCalendar
from timesheets.services import create_schedule, save_other_work


def hours_input(default=Decimal("0"), minimum=Decimal("0"), **kwargs):
    return serializers.DecimalField(
        max_digits=4, decimal_places=2, min_value=minimum, max_value=Decimal("24"), default=default, **kwargs
    )


class WorkScheduleVersionSerializer(serializers.ModelSerializer):
    week_hours = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = WorkScheduleVersion
        fields = ["id", "valid_from", *WEEKDAYS, "day_hours", "week_hours"]
        read_only_fields = fields


class ScheduleHoursSerializer(serializers.Serializer):
    valid_from = serializers.DateField(required=False, allow_null=True)
    mon = hours_input()
    tue = hours_input()
    wed = hours_input()
    thu = hours_input()
    fri = hours_input()
    sat = hours_input()
    sun = hours_input()
    day_hours = hours_input(default=Decimal("8"), minimum=Decimal("0.5"))


class WorkScheduleSerializer(serializers.ModelSerializer):
    versions = WorkScheduleVersionSerializer(many=True, read_only=True)
    is_default = serializers.SerializerMethodField()
    worker_count = serializers.SerializerMethodField()
    mon = hours_input(write_only=True)
    tue = hours_input(write_only=True)
    wed = hours_input(write_only=True)
    thu = hours_input(write_only=True)
    fri = hours_input(write_only=True)
    sat = hours_input(write_only=True)
    sun = hours_input(write_only=True)
    day_hours = hours_input(default=Decimal("8"), minimum=Decimal("0.5"), write_only=True)

    class Meta:
        model = WorkSchedule
        fields = ["id", "name", "versions", "is_default", "worker_count", *WEEKDAYS, "day_hours"]

    def get_is_default(self, schedule):
        return getattr(schedule, "is_default", False)

    def get_worker_count(self, schedule):
        return getattr(schedule, "worker_count", 0)

    def validate_name(self, name):
        return unique_name(WorkSchedule, self.context["request"].company, name, self.instance, "schedule")

    def create(self, validated_data):
        hours = {name: validated_data.pop(name) for name in WEEKDAYS}
        return create_schedule(validated_data["company"], validated_data["name"], hours, validated_data["day_hours"])

    def update(self, instance, validated_data):
        instance.name = validated_data.get("name", instance.name)
        instance.save(update_fields=["name"])
        return instance


class ApplyScheduleSerializer(serializers.Serializer):
    everyone = serializers.BooleanField(default=False)
    team = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    worker_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    start_date = serializers.DateField()

    def validate(self, attrs):
        chosen = [bool(attrs.get("everyone")), bool(attrs.get("team")), bool(attrs.get("worker_ids"))]
        if sum(chosen) != 1:
            raise serializers.ValidationError("Choose everyone, a team, or some workers.")
        return attrs


class ScheduleAssignmentSerializer(serializers.ModelSerializer):
    schedule_name = serializers.CharField(source="schedule.name", read_only=True)
    worker_name = serializers.CharField(source="worker.name", read_only=True, default="")

    class Meta:
        model = ScheduleAssignment
        fields = ["id", "schedule", "schedule_name", "worker", "worker_name", "start_date", "end_date"]
        read_only_fields = fields


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]

    def validate_date(self, day):
        clash = Holiday.objects.filter(company=self.context["request"].company, date=day)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("There is already a holiday on that day.")
        return day


class CopyHolidaysSerializer(serializers.Serializer):
    from_year = serializers.IntegerField(min_value=2000, max_value=2100)
    to_year = serializers.IntegerField(min_value=2000, max_value=2100)


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "name", "code", "paid", "uses_allowance", "position", "archived"]

    def validate_name(self, name):
        return unique_name(LeaveType, self.context["request"].company, name, self.instance, "type")

    def validate_code(self, code):
        code = code.upper()
        clash = LeaveType.objects.filter(company=self.context["request"].company, code=code)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another type uses this code.")
        return code

    def validate(self, attrs):
        if self.instance is not None and self.instance.days_off.exists():
            for field in ("paid", "uses_allowance"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {field: "This type is already used. Archive it and add a new one instead."}
                    )
        return attrs


class LeaveSerializer(CompanyWorkerMixin, serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)
    type_name = serializers.CharField(source="leave_type.name", read_only=True)
    type_code = serializers.CharField(source="leave_type.code", read_only=True)
    paid = serializers.BooleanField(source="leave_type.paid", read_only=True)
    uses_allowance = serializers.BooleanField(source="leave_type.uses_allowance", read_only=True)
    requested_by_email = serializers.EmailField(source="requested_by.email", read_only=True, default="")
    decided_by_email = serializers.EmailField(source="decided_by.email", read_only=True, default="")
    days = serializers.SerializerMethodField()

    class Meta:
        model = Leave
        fields = [
            "id",
            "worker",
            "worker_name",
            "leave_type",
            "type_name",
            "type_code",
            "paid",
            "uses_allowance",
            "start_date",
            "end_date",
            "half_day",
            "status",
            "note",
            "requested_by",
            "requested_by_email",
            "decided_by_email",
            "decided_at",
            "created_at",
            "days",
        ]
        read_only_fields = ["status", "requested_by", "decided_at", "created_at"]

    def validate_leave_type(self, leave_type):
        if leave_type.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Type must belong to this company.")
        return leave_type

    def get_days(self, leave):
        calendar = self.context.get("calendar") or WorkCalendar(
            leave.company, [leave.worker], leave.start_date, leave.end_date
        )
        return str(leave_days(calendar, leave))

    def to_representation(self, leave):
        data = super().to_representation(leave)
        request = self.context.get("request")
        if request is not None and is_team_lead(request) and leave.requested_by_id != request.user.id:
            data["note"] = ""
        return data

    def create(self, validated_data):
        request = self.context["request"]
        return request_leave(
            company=validated_data["company"],
            worker=validated_data["worker"],
            leave_type=validated_data["leave_type"],
            start_date=validated_data["start_date"],
            end_date=validated_data["end_date"],
            half_day=validated_data.get("half_day", False),
            note=validated_data.get("note", ""),
            user=request.user,
            approve=not is_team_lead(request),
        )

    def update(self, instance, validated_data):
        validated_data.pop("worker", None)
        return update_leave(instance, validated_data)


class LeavePreviewSerializer(serializers.Serializer):
    worker = serializers.IntegerField(min_value=1)
    leave_type = serializers.IntegerField(min_value=1, required=False)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    half_day = serializers.BooleanField(default=False)


class YearSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100, required=False)
    team = serializers.IntegerField(min_value=1, required=False)


class OtherWorkSerializer(CompanyWorkerMixin, serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)

    class Meta:
        model = OtherWork
        fields = ["id", "worker", "worker_name", "work_date", "hours", "kind", "note"]

    def create(self, validated_data):
        return save_other_work(OtherWork(**validated_data), user=self.context["request"].user)

    def update(self, instance, validated_data):
        validated_data.pop("worker", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return save_other_work(instance)


class PayGroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = PayGroup
        fields = ["id", "name", "cycle", "anchor_date", "is_default", "member_count"]
        read_only_fields = ["is_default"]

    def get_member_count(self, group):
        return getattr(group, "member_count", 0)

    def validate_name(self, name):
        return unique_name(PayGroup, self.context["request"].company, name, self.instance, "pay group")

    def validate(self, attrs):
        cycle = attrs.get("cycle", getattr(self.instance, "cycle", PayGroup.Cycle.MONTHLY))
        anchor = attrs.get("anchor_date", getattr(self.instance, "anchor_date", None))
        if cycle == PayGroup.Cycle.TWO_WEEKS and anchor is not None and anchor.weekday() != 0:
            raise serializers.ValidationError({"anchor_date": "A two-week cycle starts on a Monday."})
        return attrs


class TimesheetPeriodSerializer(serializers.ModelSerializer):
    pay_group_name = serializers.CharField(source="pay_group.name", read_only=True)
    approved_by_email = serializers.EmailField(source="approved_by.email", read_only=True, default="")
    label = serializers.SerializerMethodField()

    class Meta:
        model = TimesheetPeriod
        fields = ["id", "pay_group", "pay_group_name", "start_date", "end_date", "status", "approved_by_email", "approved_at", "label"]
        read_only_fields = fields

    def get_label(self, period):
        return period_label(period.start_date, period.end_date)


class PeriodApproveSerializer(serializers.Serializer):
    pay_group = serializers.IntegerField(min_value=1)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class TimesheetQuerySerializer(serializers.Serializer):
    """Reads ?from=&to= (``from`` cannot be a class attribute name)."""

    def get_fields(self):
        return {
            "from": serializers.DateField(required=False),
            "to": serializers.DateField(required=False),
            "date": serializers.DateField(required=False),
            "pay_group": serializers.IntegerField(min_value=1, required=False),
            "team": serializers.IntegerField(min_value=1, required=False),
            "worker": serializers.IntegerField(min_value=1, required=False),
        }


class CellSerializer(serializers.Serializer):
    worker = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    hours = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("24"))
    workplace = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class WorkerDaySerializer(serializers.Serializer):
    worker = serializers.IntegerField(min_value=1)
    date = serializers.DateField()


class FillSerializer(serializers.Serializer):
    def get_fields(self):
        return {
            "worker": serializers.IntegerField(min_value=1),
            "from": serializers.DateField(),
            "to": serializers.DateField(),
        }
