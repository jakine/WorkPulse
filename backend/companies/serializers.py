from zoneinfo import available_timezones

from rest_framework import serializers

from companies.models import Company, Membership


def unique_name(model, company, name, instance=None, label="record"):
    name = name.strip()
    existing = model.objects.filter(company=company, name__iexact=name)
    if instance is not None:
        existing = existing.exclude(pk=instance.pk)
    if existing.exists():
        raise serializers.ValidationError(f"A {label} with that name already exists.")
    return name


class CompanyWorkerMixin:
    def validate_worker(self, worker):
        if worker.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Worker must belong to this company.")
        return worker


class CompanyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "timezone", "leave_days_per_year"]

    def validate_name(self, name):
        name = name.strip()
        if not name:
            raise serializers.ValidationError("Enter a company name.")
        return name

    def validate_timezone(self, value):
        if value not in available_timezones():
            raise serializers.ValidationError("Choose a time zone from the list.")
        return value


class MembershipSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source="user_id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "email", "role"]


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=[Membership.Role.MANAGER, Membership.Role.TEAM_LEAD],
        default=Membership.Role.MANAGER,
    )
    team = serializers.IntegerField(required=False, allow_null=True)


class SwitchSerializer(serializers.Serializer):
    company_id = serializers.IntegerField()
