import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from companies.models import Membership
from companies.testing import auth_client, make_membership, make_user
from core.models import ActivityEvent
from operations.models import ProjectScope, SheetColumn, WorkMeasure, WorkplaceTeam, WorkType
from operations.services import create_default_measures, create_workplace, default_work_category
from sitelog.models import CrewAttendance, DailyLog
from workforce.models import Team, TeamMembership, Worker

DAY = "2026-06-10"
MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DailyLogTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        self.lead = make_user("mira@example.com")
        Membership.objects.create(user=self.lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        self.lead_client = auth_client(self.lead, self.company)

        create_default_measures(self.company)
        measure = WorkMeasure.objects.get(company=self.company, symbol="m²")
        plaster = WorkType.objects.create(
            company=self.company, category=default_work_category(self.company), measure=measure, name="Plaster"
        )
        self.project = create_workplace(self.company, name="Bridge", status="active")
        self.scope = ProjectScope.objects.create(workplace=self.project, work_type=plaster, planned_quantity=Decimal("500"))
        self.team = Team.objects.create(company=self.company, number=1, name="Mira's team", lead_user=self.lead)
        self.other_team = Team.objects.create(company=self.company, number=2, name="Structure crew")
        for team in (self.team, self.other_team):
            WorkplaceTeam.objects.create(workplace=self.project, team=team, start_date="2026-06-01")
        self.workers = []
        for name in ("Besnik", "Drita", "Niko"):
            worker = Worker.objects.create(company=self.company, name=name, team=self.team)
            TeamMembership.objects.create(worker=worker, team=self.team, start_date="2026-05-01")
            self.workers.append(worker)
        self.genti = Worker.objects.create(company=self.company, name="Genti", team=self.other_team)
        TeamMembership.objects.create(worker=self.genti, team=self.other_team, start_date="2026-05-01")

    def day(self, client=None):
        return (client or self.client).get(f"/api/daily-logs/day/?workplace={self.project.pk}&date={DAY}")

    def crew(self, client, team, workers):
        return client.put(
            "/api/daily-logs/attendance/",
            {"workplace": self.project.pk, "date": DAY, "team": team.pk, "worker_ids": [w.pk for w in workers]},
            format="json",
        )

    def report(self, client, quantity="20.00"):
        return client.post(
            "/api/site-reports/",
            {
                "workplace": self.project.pk,
                "team": self.team.pk,
                "scope": self.scope.pk,
                "work_date": DAY,
                "days": "1.00",
                "quantity": quantity,
            },
            format="json",
        )

    def test_day_shows_placed_teams_with_their_members(self):
        response = self.day()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "open")
        crew = {row["team_name"]: [w["name"] for w in row["crew"]] for row in response.data["teams"]}
        self.assertEqual(crew, {"Mira's team": ["Besnik", "Drita", "Niko"], "Structure crew": ["Genti"]})

    def test_lead_fills_crew_and_report_then_manager_approval_locks_the_day(self):
        crew = self.crew(self.lead_client, self.team, self.workers[:2])
        self.assertEqual(crew.status_code, 200)
        team = next(row for row in crew.data["teams"] if row["team"] == self.team.pk)
        self.assertEqual(team["present_count"], 2)
        self.assertEqual(self.report(self.lead_client).status_code, 201)

        approved = self.client.post("/api/daily-logs/approve/", {"workplace": self.project.pk, "date": DAY}, format="json")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["log"]["approved_by_email"], "owner@example.com")

        self.assertEqual(self.crew(self.lead_client, self.team, self.workers).status_code, 400)
        duplicate = self.report(self.lead_client, quantity="5.00")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("approved", str(duplicate.data))
        report_id = approved.data["reports"][0]["id"]
        changed = self.client.patch(f"/api/site-reports/{report_id}/", {"quantity": "25.00"}, format="json")
        self.assertEqual(changed.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/site-reports/{report_id}/").status_code, 400)
        column = SheetColumn.objects.create(workplace=self.project, kind=SheetColumn.Kind.TEXT, name="Weather")
        sheet = self.client.post(
            f"/api/projects/{self.project.pk}/sheet/", {"column": column.pk, "work_date": DAY, "text": "Sun"}, format="json"
        )
        self.assertEqual(sheet.status_code, 400)

        self.assertEqual(
            self.lead_client.post("/api/daily-logs/reopen/", {"workplace": self.project.pk, "date": DAY, "reason": "x"}, format="json").status_code,
            403,
        )
        reopened = self.client.post(
            "/api/daily-logs/reopen/",
            {"workplace": self.project.pk, "date": DAY, "reason": "Wrong amount"},
            format="json",
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.data["status"], "open")
        self.assertEqual(self.client.patch(f"/api/site-reports/{report_id}/", {"quantity": "25.00"}, format="json").status_code, 200)
        verbs = set(ActivityEvent.objects.filter(project=self.project).values_list("verb", flat=True))
        self.assertTrue({"day.approved", "day.reopened"} <= verbs)

    def test_leads_record_only_their_own_team_and_cannot_approve(self):
        self.assertEqual(self.crew(self.lead_client, self.other_team, [self.genti]).status_code, 403)
        approve = self.lead_client.post("/api/daily-logs/approve/", {"workplace": self.project.pk, "date": DAY}, format="json")
        self.assertEqual(approve.status_code, 403)

    def test_a_worker_is_on_one_crew_per_project_day(self):
        self.assertEqual(self.crew(self.client, self.other_team, [self.genti]).status_code, 200)
        moved = self.crew(self.client, self.team, [self.workers[0], self.genti])
        self.assertEqual(moved.status_code, 400)
        self.assertIn("Genti", str(moved.data))
        self.assertEqual(CrewAttendance.objects.filter(work_date=DAY).count(), 1)

    def test_missing_reports_lists_placed_teams_that_have_not_reported(self):
        self.report(self.client)
        missing = self.client.get(f"/api/daily-logs/missing/?date={DAY}")
        self.assertEqual(missing.status_code, 200)
        self.assertEqual([row["team_name"] for row in missing.data["results"]], ["Structure crew"])
        lead_view = self.lead_client.get(f"/api/daily-logs/missing/?date={DAY}")
        self.assertEqual(lead_view.data["results"], [])

    def test_notes_and_issues_belong_to_the_day(self):
        updated = self.lead_client.patch(
            "/api/daily-logs/day/",
            {"workplace": self.project.pk, "date": DAY, "weather": "Rain after 14:00", "notes": "Scaffold moved"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["log"]["weather"], "Rain after 14:00")
        issue = self.lead_client.post(
            "/api/daily-log-issues/",
            {"workplace": self.project.pk, "work_date": DAY, "kind": "material", "description": "No adhesive", "hours_lost": "2.50"},
            format="json",
        )
        self.assertEqual(issue.status_code, 201)
        self.assertEqual([row["description"] for row in self.day().data["issues"]], ["No adhesive"])
        self.assertEqual(DailyLog.objects.get(workplace=self.project).issues.count(), 1)

    def test_days_stay_inside_their_company(self):
        other_user = make_user("other@example.com")
        other_client = auth_client(other_user, make_membership(other_user, "South").company)
        self.assertEqual(self.day(other_client).status_code, 404)
        self.assertEqual(self.crew(other_client, self.team, self.workers).status_code, 404)

    def test_photos_on_an_approved_day_are_locked(self):
        self.client.patch("/api/daily-logs/day/", {"workplace": self.project.pk, "date": DAY, "notes": "Start"}, format="json")
        log = DailyLog.objects.get(workplace=self.project)

        def upload():
            return self.lead_client.post(
                "/api/attachments/",
                {
                    "target_type": "sitelog.dailylog",
                    "target_id": log.pk,
                    "file": SimpleUploadedFile("deck.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16),
                },
                format="multipart",
            )

        added = upload()
        self.assertEqual(added.status_code, 201)
        self.client.post("/api/daily-logs/approve/", {"workplace": self.project.pk, "date": DAY}, format="json")
        self.assertEqual(upload().status_code, 400)
        self.assertEqual(self.lead_client.delete(f"/api/attachments/{added.data['id']}/").status_code, 400)
