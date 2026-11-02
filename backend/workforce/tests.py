from datetime import timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from companies.models import Membership
from companies.testing import auth_client, make_membership, make_user
from core.models import ActivityEvent
from operations.models import WorkplaceTeam
from operations.services import create_workplace
from workforce.models import Team, TeamMembership, Worker


class WorkforceApiTests(TestCase):
    def setUp(self):
        self.user = make_user("lead@example.com")
        self.membership = make_membership(self.user, "North")
        self.client = auth_client(self.user, self.membership.company)
        self.other_user = make_user("other@example.com")
        self.other = make_membership(self.other_user, "South")

    def test_workers_are_scoped_to_the_active_company(self):
        Worker.objects.create(company=self.membership.company, name="Ada")
        Worker.objects.create(company=self.other.company, name="Hidden")

        response = self.client.get("/api/workers/")

        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data["results"]]
        self.assertEqual(names, ["Ada"])

    def test_a_worker_belongs_to_a_team(self):
        created = self.client.post(
            "/api/teams/",
            {"number": 1, "name": "Team 1", "worker_count": 4, "lead_note": "Mira"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        worker = self.client.post(
            "/api/workers/",
            {"name": "Ada", "team": created.data["id"]},
            format="json",
        )
        self.assertEqual(worker.status_code, 201)
        self.assertEqual(worker.data["team_name"], "Team 1")
        self.assertEqual(worker.data["team_number"], 1)

    def test_requests_without_a_company_are_rejected(self):
        client = APIClient()
        client.force_login(self.user)
        response = client.get("/api/workers/")
        self.assertEqual(response.status_code, 403)


class TeamHistoryTests(TestCase):
    def setUp(self):
        self.user = make_user("owner@example.com")
        self.company = make_membership(self.user, "North").company
        self.client = auth_client(self.user, self.company)
        self.structure = Team.objects.create(company=self.company, number=1, name="Structure crew")
        self.finishes = Team.objects.create(company=self.company, number=2, name="Finishes crew")
        self.today = self.company.today()
        self.worker = Worker.objects.create(company=self.company, name="Valon", team=self.structure)
        TeamMembership.objects.create(
            worker=self.worker, team=self.structure, start_date=self.today - timedelta(days=60)
        )

    def move(self, team, on_date, client=None):
        return (client or self.client).post(
            f"/api/workers/{self.worker.pk}/move/",
            {"team": team.pk if team else None, "on_date": str(on_date)},
            format="json",
        )

    def test_moving_a_worker_keeps_their_team_history(self):
        moved_on = self.today - timedelta(days=10)
        response = self.move(self.finishes, moved_on)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["team_name"], "Finishes crew")
        stretches = [(row["team_name"], row["start_date"], row["end_date"]) for row in response.data["memberships"]]
        self.assertEqual(
            stretches,
            [
                ("Finishes crew", str(moved_on), None),
                ("Structure crew", str(self.today - timedelta(days=60)), str(moved_on - timedelta(days=1))),
            ],
        )
        counts = {row["name"]: row["member_count"] for row in self.client.get("/api/teams/").data["results"]}
        self.assertEqual(counts, {"Structure crew": 0, "Finishes crew": 1})
        self.assertTrue(ActivityEvent.objects.filter(verb="worker.moved", target_id=self.worker.pk).exists())

    def test_moves_cannot_go_before_the_current_team_or_into_the_future(self):
        self.assertEqual(self.move(self.finishes, self.today - timedelta(days=61)).status_code, 400)
        self.assertEqual(self.move(self.finishes, self.today + timedelta(days=1)).status_code, 400)

    def test_a_same_day_move_corrects_the_team_without_an_empty_stretch(self):
        self.move(self.finishes, self.today)
        response = self.move(self.structure, self.today)
        self.assertEqual(response.status_code, 200)
        stretches = [(row["team_name"], row["end_date"]) for row in response.data["memberships"]]
        self.assertEqual(stretches, [("Structure crew", None), ("Structure crew", str(self.today - timedelta(days=1)))])

    def test_leaving_a_team_and_editing_the_team_on_the_worker(self):
        left = self.move(None, self.today - timedelta(days=5))
        self.assertIsNone(left.data["team"])
        edited = self.client.patch(f"/api/workers/{self.worker.pk}/", {"team": self.finishes.pk}, format="json")
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(TeamMembership.objects.get(worker=self.worker, end_date__isnull=True).team, self.finishes)

    def test_new_worker_with_a_team_starts_a_stretch_today(self):
        created = self.client.post("/api/workers/", {"name": "Ana", "team": self.finishes.pk}, format="json")
        self.assertEqual(created.status_code, 201)
        stretch = TeamMembership.objects.get(worker_id=created.data["id"])
        self.assertEqual((stretch.team, stretch.start_date, stretch.end_date), (self.finishes, self.today, None))

    def test_team_leads_cannot_move_workers(self):
        lead = make_user("lead@example.com")
        Membership.objects.create(user=lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        response = self.move(self.finishes, self.today, client=auth_client(lead, self.company))
        self.assertEqual(response.status_code, 403)

    def test_team_page_lists_members_past_members_and_placements(self):
        self.move(self.finishes, self.today - timedelta(days=10))
        project = create_workplace(self.company, name="Bridge", status="active")
        WorkplaceTeam.objects.create(workplace=project, team=self.structure, start_date=self.today - timedelta(days=30))
        Worker.objects.create(company=self.company, name="Genti")
        response = self.client.get(f"/api/teams/{self.structure.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["members"], [])
        self.assertEqual([row["worker_name"] for row in response.data["past_members"]], ["Valon"])
        self.assertEqual([row["workplace_name"] for row in response.data["placements"]], ["Bridge"])
