import json

from django.db.models import Q
from django.http import FileResponse
from rest_framework import mixins, renderers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from companies.permissions import HasCompanyRole, is_team_lead, lead_projects
from core.models import ActivityEvent, Attachment
from core.serializers import ActivityEventSerializer, AttachmentSerializer, AttachmentUploadSerializer
from core.services import (
    attachment_lock,
    attachment_target,
    create_attachment,
    record_event,
    resolve_attachment_target,
)


class ActivityEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCompanyRole]
    serializer_class = ActivityEventSerializer

    def get_queryset(self):
        queryset = ActivityEvent.objects.filter(company=self.request.company).select_related("actor", "project")
        if is_team_lead(self.request):
            queryset = queryset.filter(project__in=lead_projects(self.request).values("pk"))
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset


class FileRenderer(renderers.BaseRenderer):
    """Lets image and PDF requests through content negotiation; errors still come back as JSON."""

    media_type = "*/*"
    format = "file"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, bytes):
            return data
        return json.dumps(data).encode("utf-8")


class AttachmentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, HasCompanyRole]
    serializer_class = AttachmentSerializer
    parser_classes = [MultiPartParser, FormParser]
    lead_actions = ("create", "destroy")

    def get_queryset(self):
        queryset = Attachment.objects.filter(company=self.request.company).select_related("uploaded_by")
        if is_team_lead(self.request):
            queryset = queryset.filter(
                Q(project__isnull=True) | Q(project__in=lead_projects(self.request).values("pk"))
            )
        params = self.request.query_params
        if params.get("target_type"):
            queryset = queryset.filter(target_type=params["target_type"])
        if params.get("target_id"):
            queryset = queryset.filter(target_id=params["target_id"])
        if params.get("project"):
            queryset = queryset.filter(project_id=params["project"])
        return queryset

    def create(self, request, *args, **kwargs):
        upload = AttachmentUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        data = upload.validated_data
        target, project = resolve_attachment_target(request, data["target_type"], data["target_id"])
        attachment = create_attachment(
            company=request.company,
            user=request.user,
            target=target,
            project=project,
            upload=data["file"],
            caption=data.get("caption", ""),
        )
        record_event(request, "attachment.added", target, project=project, data={"name": attachment.original_name})
        return Response(self.get_serializer(attachment).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if is_team_lead(self.request) and instance.uploaded_by_id != self.request.user.id:
            raise PermissionDenied("You can only remove files you added.")
        target = attachment_target(instance)
        message = attachment_lock(target) if target is not None else None
        if message:
            raise ValidationError({"detail": message})
        if target is not None:
            record_event(
                self.request,
                "attachment.removed",
                target,
                project=instance.project,
                data={"name": instance.original_name},
            )
        instance.delete()

    @action(detail=True, methods=["get"], renderer_classes=[renderers.JSONRenderer, FileRenderer])
    def file(self, request, pk=None):
        attachment = self.get_object()
        response = FileResponse(
            attachment.file.open("rb"),
            content_type=attachment.content_type,
            as_attachment=request.query_params.get("download") == "1",
            filename=attachment.original_name,
        )
        response["Cache-Control"] = "private, max-age=3600"
        return response
