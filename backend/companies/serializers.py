from zoneinfo import available_timezones

from rest_framework import serializers

from companies.models import Company, Membership


class CompanyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "timezone"]

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
