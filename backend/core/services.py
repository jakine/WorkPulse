from pathlib import PurePosixPath

from django.apps import apps
from django.utils.module_loading import import_string
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.models import ActivityEvent, Attachment


def target_label(target):
    return target._meta.label_lower


def record_event(request, verb, target, project=None, data=None):
    return ActivityEvent.objects.create(
        company=request.company,
        actor=request.user if request.user.is_authenticated else None,
        project=project,
        verb=verb,
        target_type=target_label(target),
        target_id=target.pk,
        data=data or {},
    )


def events_for(target, company=None):
    queryset = ActivityEvent.objects.filter(
        target_type=target_label(target),
        target_id=target.pk,
    ).select_related("actor")
    if company is not None:
        queryset = queryset.filter(company=company)
    return queryset


# Records that can carry files. "company" and "project" are lookups from the record;
# "lead" is the lookup that must reach the team lead for a lead to add files (None: leads cannot);
# "locked" names a function that returns a message while the record must not change.
ATTACHMENT_TARGETS = {
    "work.task": {"company": "company", "project": "project", "lead": "team__lead_user"},
    "sitelog.dailylog": {
        "company": "workplace__company",
        "project": "workplace",
        "lead": "workplace__workplace_teams__team__lead_user",
        "locked": "sitelog.services.locked_message",
    },
}

ALLOWED_UPLOADS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def _follow(obj, lookup):
    for part in lookup.split("__"):
        obj = getattr(obj, part)
    return obj


def _content_matches(content_type, head):
    if content_type == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if content_type == "application/pdf":
        return head.startswith(b"%PDF-")
    return False


def resolve_attachment_target(request, target_type, target_id):
    from companies.permissions import is_team_lead

    config = ATTACHMENT_TARGETS.get(target_type)
    if config is None:
        raise ValidationError({"target_type": "Files cannot be attached to that record."})
    model = apps.get_model(target_type)
    target = model.objects.filter(pk=target_id, **{config["company"]: request.company}).first()
    if target is None:
        raise ValidationError({"target_id": "Choose a record in this company."})
    if is_team_lead(request):
        lead_lookup = config["lead"]
        if lead_lookup is None or not model.objects.filter(pk=target.pk, **{lead_lookup: request.user}).exists():
            raise PermissionDenied("You can only add files to work assigned to a team you lead.")
    message = attachment_lock(target)
    if message:
        raise ValidationError({"target_id": message})
    project = _follow(target, config["project"]) if config["project"] else None
    return target, project


def attachment_lock(target):
    check = ATTACHMENT_TARGETS.get(target_label(target), {}).get("locked")
    return import_string(check)(target) if check else None


def attachment_target(attachment):
    model = apps.get_model(attachment.target_type)
    return model.objects.filter(pk=attachment.target_id).first()


def create_attachment(*, company, user, target, project, upload, caption=""):
    suffix = PurePosixPath(upload.name).suffix.lower()
    content_type = ALLOWED_UPLOADS.get(suffix)
    if content_type is None:
        raise ValidationError({"file": "Upload a JPG, PNG, WebP or PDF file."})
    if not upload.size:
        raise ValidationError({"file": "The file is empty."})
    if upload.size > settings.ATTACHMENT_MAX_BYTES:
        limit = settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)
        raise ValidationError({"file": f"Files can be at most {limit} MB."})
    head = upload.read(16)
    upload.seek(0)
    if not _content_matches(content_type, head):
        raise ValidationError({"file": "The file content does not match its type."})
    return Attachment.objects.create(
        company=company,
        project=project,
        target_type=target_label(target),
        target_id=target.pk,
        file=upload,
        original_name=PurePosixPath(upload.name).name[:255],
        content_type=content_type,
        size=upload.size,
        caption=(caption or "").strip(),
        uploaded_by=user,
    )


def _delete_attachment_file(sender, instance, **kwargs):
    storage, name = instance.file.storage, instance.file.name
    if name:
        transaction.on_commit(lambda: storage.delete(name))


def _delete_target_attachments(sender, instance, **kwargs):
    Attachment.objects.filter(target_type=target_label(instance), target_id=instance.pk).delete()


def connect_attachment_cleanup():
    post_delete.connect(_delete_attachment_file, sender=Attachment, dispatch_uid="attachment-file")
    for label in ATTACHMENT_TARGETS:
        post_delete.connect(_delete_target_attachments, sender=label, dispatch_uid=f"attachments-{label}")
