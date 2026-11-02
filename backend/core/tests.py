import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from companies.models import Membership
from companies.testing import auth_client, make_membership, make_user
from core.models import ActivityEvent, Attachment
from operations.models import WorkplaceTeam
from operations.services import create_workplace
from work.models import TaskStatus
from work.services import create_default_phases, create_default_statuses, create_task
from workforce.models import Team

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4\n%test\n"
MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AttachmentApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "Build Co").company
        self.client = auth_client(self.owner, self.company)
        create_default_statuses(self.company)
        create_default_phases(self.company)
        self.todo = TaskStatus.objects.get(company=self.company, name="To do")
        self.team = Team.objects.create(company=self.company, number=1, name="Team 1")
        self.project = create_workplace(self.company, name="Bridge", status="active")
        self.task = create_task(self.company, self.project, self.owner, title="Pour slab", status=self.todo, team=self.team)

    def upload(self, client, content=PNG, name="slab.png", target=None):
        target = target or self.task
        return client.post(
            "/api/attachments/",
            {
                "target_type": "work.task",
                "target_id": target.pk,
                "file": SimpleUploadedFile(name, content),
                "caption": "North edge",
            },
            format="multipart",
        )

    def test_manager_adds_a_photo_to_a_task_and_opens_it(self):
        created = self.upload(self.client)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["content_type"], "image/png")
        self.assertTrue(created.data["is_image"])
        self.assertEqual(created.data["project"], self.project.pk)
        self.assertEqual(created.data["caption"], "North edge")

        listed = self.client.get(f"/api/attachments/?target_type=work.task&target_id={self.task.pk}")
        self.assertEqual([row["original_name"] for row in listed.data["results"]], ["slab.png"])

        opened = self.client.get(created.data["url"], HTTP_ACCEPT="image/webp,image/*")
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened["Content-Type"], "image/png")
        self.assertEqual(b"".join(opened.streaming_content), PNG)
        self.assertTrue(
            ActivityEvent.objects.filter(verb="attachment.added", target_type="work.task", target_id=self.task.pk).exists()
        )

    def test_only_images_and_pdfs_with_matching_content_are_accepted(self):
        self.assertEqual(self.upload(self.client, b"MZ\x90\x00", "tool.exe").status_code, 400)
        self.assertEqual(self.upload(self.client, PDF, "photo.png").status_code, 400)
        self.assertEqual(self.upload(self.client, b"", "empty.png").status_code, 400)
        self.assertEqual(self.upload(self.client, PDF, "plan.pdf").status_code, 201)

    def test_files_stay_inside_their_company(self):
        created = self.upload(self.client)
        other_user = make_user("other@example.com")
        other_client = auth_client(other_user, make_membership(other_user, "South").company)

        self.assertEqual(other_client.get("/api/attachments/").data["results"], [])
        self.assertEqual(other_client.get(created.data["url"]).status_code, 404)
        self.assertEqual(self.upload(other_client).status_code, 400)

    def test_lead_adds_files_to_their_team_tasks_and_removes_only_their_own(self):
        lead = make_user("lead@example.com")
        Membership.objects.create(user=lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        self.team.lead_user = lead
        self.team.save(update_fields=["lead_user"])
        WorkplaceTeam.objects.create(workplace=self.project, team=self.team, start_date="2026-06-01")
        lead_client = auth_client(lead, self.company)
        unassigned = create_task(self.company, self.project, self.owner, title="Fence", status=self.todo)

        self.assertEqual(self.upload(lead_client, target=unassigned).status_code, 403)
        own = self.upload(lead_client)
        self.assertEqual(own.status_code, 201)
        manager_file = self.upload(self.client)
        self.assertEqual(len(lead_client.get("/api/attachments/").data["results"]), 2)
        self.assertEqual(lead_client.delete(f"/api/attachments/{manager_file.data['id']}/").status_code, 403)
        self.assertEqual(lead_client.delete(f"/api/attachments/{own.data['id']}/").status_code, 204)

    def test_deleting_a_task_removes_its_files(self):
        self.upload(self.client)
        self.assertEqual(self.client.delete(f"/api/tasks/{self.task.pk}/").status_code, 204)
        self.assertFalse(Attachment.objects.exists())
