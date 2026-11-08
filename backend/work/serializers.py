from decimal import Decimal

from rest_framework import serializers

from companies.models import Membership
from companies.serializers import unique_name
from operations.models import WorkplaceTeam
from operations.services import measure_symbol_for
from work.models import Task, TaskCategory, TaskComment, TaskPhase, TaskStatus


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = ["id", "name", "color", "position"]

    def validate_name(self, name):
        return unique_name(TaskCategory, self.context["request"].company, name, self.instance, "category")

    def validate_color(self, color):
        color = color.strip()
        if len(color) != 7 or not color.startswith("#"):
            raise serializers.ValidationError("Use a color like #01696f.")
        try:
            int(color[1:], 16)
        except ValueError as exc:
            raise serializers.ValidationError("Use a color like #01696f.") from exc
        return color.lower()


class TaskPhaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPhase
        fields = ["id", "name", "position"]

    def validate_name(self, name):
        return unique_name(TaskPhase, self.context["request"].company, name, self.instance, "phase")


class TaskStatusSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_color = serializers.CharField(source="category.color", read_only=True)

    class Meta:
        model = TaskStatus
        fields = ["id", "name", "category", "category_name", "category_color", "position"]

    def validate_name(self, name):
        return unique_name(TaskStatus, self.context["request"].company, name, self.instance, "status")

    def validate_category(self, category):
        if category.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Category must belong to this company.")
        return category


class StatusReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class TaskSerializer(serializers.ModelSerializer):
    key = serializers.CharField(read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    status_name = serializers.CharField(source="status.name", read_only=True)
    status_category = serializers.CharField(source="status.category.name", read_only=True)
    status_category_color = serializers.CharField(source="status.category.color", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    team_number = serializers.IntegerField(source="team.number", read_only=True, allow_null=True)
    assignee_email = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()
    work_type_name = serializers.CharField(source="work_type.name", read_only=True, allow_null=True)
    phase_name = serializers.CharField(source="phase.name", read_only=True)
    measure_symbol = serializers.SerializerMethodField()
    done_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    progress_percent = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True, allow_null=True)
    status = serializers.PrimaryKeyRelatedField(queryset=TaskStatus.objects.all(), required=False)
    phase = serializers.PrimaryKeyRelatedField(queryset=TaskPhase.objects.all(), required=False)

    class Meta:
        model = Task
        fields = [
            "id",
            "key",
            "number",
            "project",
            "project_name",
            "title",
            "description",
            "status",
            "status_name",
            "status_category",
            "status_category_color",
            "priority",
            "phase",
            "phase_name",
            "team",
            "team_name",
            "team_number",
            "work_type",
            "work_type_name",
            "assignee_user",
            "assignee_email",
            "start_date",
            "due_date",
            "planned_quantity",
            "measure_symbol",
            "done_quantity",
            "progress_percent",
            "position",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["number", "position", "created_at", "updated_at"]

    def get_assignee_email(self, obj):
        return obj.assignee_user.email if obj.assignee_user_id else ""

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by_id else ""

    def get_measure_symbol(self, obj):
        return measure_symbol_for(task=obj, workplace=obj.project)

    def validate(self, attrs):
        company = self.context["request"].company
        project = attrs.get("project") or getattr(self.instance, "project", None)
        if project is None:
            raise serializers.ValidationError({"project": "Choose a project."})
        if self.instance is not None and "project" in attrs and attrs["project"].pk != self.instance.project_id:
            raise serializers.ValidationError({"project": "A task cannot move to another project."})
        if project.company_id != company.id:
            raise serializers.ValidationError({"project": "Project must belong to this company."})
        status = attrs.get("status")
        if status is not None and status.company_id != company.id:
            raise serializers.ValidationError({"status": "Status must belong to this company."})
        phase = attrs.get("phase")
        if phase is not None and phase.company_id != company.id:
            raise serializers.ValidationError({"phase": "Phase must belong to this company."})
        team = attrs["team"] if "team" in attrs else getattr(self.instance, "team", None)
        if team is not None:
            if team.company_id != company.id:
                raise serializers.ValidationError({"team": "Team must belong to this company."})
            if not WorkplaceTeam.objects.filter(workplace=project, team=team).exists():
                raise serializers.ValidationError({"team": "Place that team on the project first."})
        assignee = attrs.get("assignee_user")
        if assignee is not None and not Membership.objects.filter(company=company, user=assignee).exists():
            raise serializers.ValidationError({"assignee_user": "Assignee must be a member of this company."})
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        due_date = attrs.get("due_date", getattr(self.instance, "due_date", None))
        work_type = attrs.get("work_type")
        if work_type is not None and work_type.company_id != company.id:
            raise serializers.ValidationError({"work_type": "Work type must belong to this company."})
        if start_date and due_date and due_date < start_date:
            raise serializers.ValidationError({"due_date": "Due date must be on or after the start date."})
        return attrs

    def to_representation(self, instance):
        done = getattr(instance, "done_quantity", None)
        if done is None:
            done = sum((report.quantity or Decimal("0")) for report in instance.reports.all())
        instance.done_quantity = done or Decimal("0.00")
        if instance.planned_quantity:
            instance.progress_percent = (
                instance.done_quantity / instance.planned_quantity * Decimal("100")
            ).quantize(Decimal("0.01"))
        else:
            instance.progress_percent = None
        return super().to_representation(instance)


class TaskMoveSerializer(serializers.Serializer):
    status = serializers.PrimaryKeyRelatedField(queryset=TaskStatus.objects.all())
    position = serializers.IntegerField(min_value=0, default=0)

    def validate_status(self, status):
        if status.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Status must belong to this company.")
        return status


class TaskCommentSerializer(serializers.ModelSerializer):
    author_email = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ["id", "task", "author_email", "body", "created_at"]
        read_only_fields = ["task", "created_at"]

    def get_author_email(self, obj):
        return obj.author.email if obj.author_id else ""

    def validate_body(self, body):
        body = body.strip()
        if not body:
            raise serializers.ValidationError("Write a comment first.")
        return body
