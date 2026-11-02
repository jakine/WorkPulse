from rest_framework import serializers

from workforce.models import Team, TeamMembership, Worker, WorkerType
from workforce.services import move_worker


class WorkerTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerType
        fields = ["id", "name"]


class TeamSerializer(serializers.ModelSerializer):
    lead_user_email = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "number",
            "name",
            "worker_count",
            "member_count",
            "lead_note",
            "lead_user",
            "lead_user_email",
        ]

    def get_lead_user_email(self, obj):
        if obj.lead_user_id is None:
            return ""
        return obj.lead_user.email

    def get_member_count(self, obj):
        count = getattr(obj, "member_count", None)
        if count is None:
            count = obj.memberships.filter(end_date__isnull=True).count()
        return count

    def validate_number(self, number):
        company = self.context["request"].company
        existing = Team.objects.filter(company=company, number=number)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("This team number is already used.")
        return number

    def validate_lead_user(self, lead_user):
        if lead_user is None:
            return lead_user
        from companies.models import Membership

        company = self.context["request"].company
        if not Membership.objects.filter(company=company, user=lead_user).exists():
            raise serializers.ValidationError("Link a user who belongs to this company.")
        return lead_user


class WorkerSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_number = serializers.IntegerField(source="team.number", read_only=True, allow_null=True)
    worker_type_name = serializers.CharField(source="worker_type.name", read_only=True)

    class Meta:
        model = Worker
        fields = [
            "id",
            "name",
            "contact",
            "status",
            "worker_type",
            "worker_type_name",
            "team",
            "team_name",
            "team_number",
        ]

    def validate_team(self, team):
        if team is None:
            return team
        if team.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Team must belong to this company.")
        return team

    def create(self, validated_data):
        team = validated_data.pop("team", None)
        worker = super().create(validated_data)
        if team is not None:
            worker = move_worker(worker, team, worker.company.today())
        return worker

    def update(self, instance, validated_data):
        team = validated_data.pop("team", instance.team)
        worker = super().update(instance, validated_data)
        if getattr(team, "id", None) != worker.team_id:
            worker = move_worker(worker, team, worker.company.today())
        return worker

    def validate_worker_type(self, worker_type):
        if worker_type is None:
            return worker_type
        if worker_type.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Worker type must belong to this company.")
        return worker_type


class TeamMembershipSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)
    worker_type_name = serializers.CharField(source="worker.worker_type.name", read_only=True, allow_null=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_number = serializers.IntegerField(source="team.number", read_only=True)

    class Meta:
        model = TeamMembership
        fields = [
            "id",
            "worker",
            "worker_name",
            "worker_type_name",
            "team",
            "team_name",
            "team_number",
            "start_date",
            "end_date",
        ]
        read_only_fields = fields


class WorkerMoveSerializer(serializers.Serializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), allow_null=True)
    on_date = serializers.DateField()

    def validate_team(self, team):
        if team is not None and team.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Team must belong to this company.")
        return team
