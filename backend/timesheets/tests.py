from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from companies.models import Membership
from companies.testing import auth_client, make_membership, make_user
from timesheets.leave import create_default_leave_types
from timesheets.models import Holiday, PayGroup, ScheduleAssignment, WorkSchedule
from timesheets.schedule import WorkCalendar
from timesheets.services import assign_schedule, change_schedule_hours, create_default_schedule, create_schedule
from workforce.models import Team, TeamMembership, Worker

MONDAY = date(2026, 6, 8)
SATURDAY = date(2026, 6, 13)
SIX_DAYS = {"mon": 8, "tue": 8, "wed": 8, "thu": 8, "fri": 8, "sat": 5}


def hours(**days):
    return {name: Decimal(str(days.get(name, 0))) for name in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


class WorkCalendarTests(TestCase):
    def setUp(self):
        self.company = make_membership(make_user("owner@example.com"), "River Co").company
        self.standard = create_default_schedule(self.company)
        self.worker = Worker.objects.create(company=self.company, name="Arben")

    def calendar(self, start=MONDAY, end=SATURDAY):
        return WorkCalendar(self.company, [self.worker], start, end)

    def test_everyone_starts_on_monday_to_friday_eight_hours(self):
        calendar = self.calendar()
        self.assertEqual(calendar.expected_hours(self.worker.pk, MONDAY), Decimal("8"))
        self.assertEqual(calendar.expected_hours(self.worker.pk, SATURDAY), Decimal("0"))

    def test_holidays_and_employment_remove_expected_hours_but_not_the_schedule(self):
        Holiday.objects.create(company=self.company, date=MONDAY, name="Bank holiday")
        self.worker.hired_on = date(2026, 6, 10)
        self.worker.save()
        calendar = self.calendar()
        self.assertEqual(calendar.expected_hours(self.worker.pk, MONDAY), Decimal("0"))
        self.assertEqual(calendar.scheduled_hours(self.worker.pk, MONDAY), Decimal("8"))
        self.assertEqual(calendar.expected_hours(self.worker.pk, date(2026, 6, 9)), Decimal("0"))
        self.assertEqual(calendar.expected_hours(self.worker.pk, date(2026, 6, 10)), Decimal("8"))
        self.assertEqual(calendar.holiday(MONDAY), "Bank holiday")

    def test_a_worker_schedule_applies_from_its_start_date(self):
        six = create_schedule(self.company, "Six days", hours(**SIX_DAYS), Decimal("8"))
        assign_schedule(self.company, six, [self.worker], date(2026, 6, 13))
        calendar = self.calendar(MONDAY, date(2026, 6, 20))
        self.assertEqual(calendar.expected_hours(self.worker.pk, date(2026, 6, 6)), Decimal("0"))
        self.assertEqual(calendar.expected_hours(self.worker.pk, SATURDAY), Decimal("5"))

    def test_changing_hours_keeps_earlier_days(self):
        change_schedule_hours(self.standard, date(2026, 6, 10), hours(mon=9, tue=9, wed=9, thu=9, fri=6), Decimal("8"))
        calendar = self.calendar()
        self.assertEqual(calendar.expected_hours(self.worker.pk, date(2026, 6, 9)), Decimal("8"))
        self.assertEqual(calendar.expected_hours(self.worker.pk, date(2026, 6, 10)), Decimal("9"))
        self.assertEqual(calendar.expected_hours(self.worker.pk, date(2026, 6, 12)), Decimal("6"))

    def test_norm_is_the_schedule_or_a_full_day_when_nothing_is_scheduled(self):
        Holiday.objects.create(company=self.company, date=MONDAY, name="Bank holiday")
        change_schedule_hours(self.standard, None, hours(mon=8, tue=8, wed=8, thu=8, fri=6), Decimal("7.5"))
        calendar = self.calendar()
        self.assertEqual(calendar.norm(self.worker.pk, date(2026, 6, 12)), Decimal("6"))
        self.assertEqual(calendar.norm(self.worker.pk, SATURDAY), Decimal("7.5"))
        self.assertEqual(calendar.norm(self.worker.pk, MONDAY), Decimal("7.5"))


class ScheduleApiTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        self.standard = create_default_schedule(self.company)
        self.team = Team.objects.create(company=self.company, number=1, name="Facade crew")
        self.arben = Worker.objects.create(company=self.company, name="Arben", team=self.team)
        self.drita = Worker.objects.create(company=self.company, name="Drita", team=self.team)
        for worker in (self.arben, self.drita):
            TeamMembership.objects.create(worker=worker, team=self.team)
        self.lead = make_user("lead@example.com")
        Membership.objects.create(user=self.lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        self.lead_client = auth_client(self.lead, self.company)

    def create_six_days(self):
        response = self.client.post("/api/schedules/", {"name": "Six days", **SIX_DAYS}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_schedules_list_their_hours_and_the_default(self):
        six = self.create_six_days()
        self.assertEqual(six["versions"][0]["sat"], "5.00")
        self.assertEqual(six["versions"][0]["week_hours"], "45.00")
        rows = {row["name"]: row for row in self.client.get("/api/schedules/").data}
        self.assertTrue(rows["Standard"]["is_default"])
        self.assertFalse(rows["Six days"]["is_default"])

    def test_a_schedule_needs_some_hours_and_a_new_name(self):
        empty = self.client.post("/api/schedules/", {"name": "Nothing"}, format="json")
        self.assertEqual(empty.status_code, 400)
        clash = self.client.post("/api/schedules/", {"name": "standard", "mon": 8}, format="json")
        self.assertEqual(clash.status_code, 400)

    def test_hours_change_from_a_date(self):
        response = self.client.post(
            f"/api/schedules/{self.standard.pk}/versions/",
            {"valid_from": "2026-07-01", "mon": 9, "tue": 9, "wed": 9, "thu": 9, "fri": 9},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["valid_from"] for row in response.data["versions"]], [None, "2026-07-01"])

    def test_applying_to_a_team_moves_its_members_from_a_date(self):
        six = self.create_six_days()
        response = self.client.post(
            f"/api/schedules/{six['id']}/apply/", {"team": self.team.pk, "start_date": "2026-06-13"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["worker_count"], 2)
        detail = self.client.get(f"/api/workers/{self.arben.pk}/").data
        self.assertEqual(detail["schedule"]["name"], "Six days")
        self.assertTrue(detail["schedule"]["own"])

        reset = self.client.post("/api/schedules/reset/", {"worker_ids": [self.arben.pk], "start_date": "2026-06-20"}, format="json")
        self.assertEqual(reset.status_code, 200)
        own = ScheduleAssignment.objects.get(worker=self.arben)
        self.assertEqual(own.end_date, date(2026, 6, 19))

    def test_a_schedule_in_use_cannot_be_deleted(self):
        response = self.client.delete(f"/api/schedules/{self.standard.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(WorkSchedule.objects.filter(pk=self.standard.pk).exists())

    def test_the_company_default_row_cannot_be_deleted(self):
        row = ScheduleAssignment.objects.get(company=self.company, worker__isnull=True)
        response = self.client.delete(f"/api/schedule-assignments/{row.pk}/")
        self.assertEqual(response.status_code, 405)

    def test_holidays_by_year_and_copied_to_the_next(self):
        for day, name in (("2026-01-01", "New Year"), ("2026-12-25", "Christmas"), ("2025-12-25", "Christmas")):
            self.assertEqual(self.client.post("/api/holidays/", {"date": day, "name": name}, format="json").status_code, 201)
        twice = self.client.post("/api/holidays/", {"date": "2026-01-01", "name": "Again"}, format="json")
        self.assertEqual(twice.status_code, 400)
        self.assertEqual(len(self.client.get("/api/holidays/?year=2026").data), 2)
        copied = self.client.post("/api/holidays/copy-year/", {"from_year": 2026, "to_year": 2027}, format="json")
        self.assertEqual(copied.data["created"], 2)
        self.assertEqual([row["name"] for row in self.client.get("/api/holidays/?year=2027").data], ["New Year", "Christmas"])

    def test_leads_read_but_cannot_change_schedules_or_holidays(self):
        self.assertEqual(self.lead_client.get("/api/schedules/").status_code, 200)
        self.assertEqual(self.lead_client.post("/api/schedules/", {"name": "Mine", "mon": 8}, format="json").status_code, 403)
        apply = self.lead_client.post(
            f"/api/schedules/{self.standard.pk}/apply/", {"everyone": True, "start_date": "2026-06-01"}, format="json"
        )
        self.assertEqual(apply.status_code, 403)
        self.assertEqual(self.lead_client.post("/api/holidays/", {"date": "2026-05-01", "name": "May Day"}, format="json").status_code, 403)

    def test_another_company_sees_none_of_it(self):
        other = make_user("other@example.com")
        other_client = auth_client(other, make_membership(other, "South").company)
        Holiday.objects.create(company=self.company, date=MONDAY, name="Bank holiday")
        self.assertEqual(other_client.get("/api/schedules/").data, [])
        self.assertEqual(other_client.get("/api/holidays/").data, [])
        self.assertEqual(other_client.get(f"/api/schedules/{self.standard.pk}/").status_code, 404)
        apply = other_client.post(
            f"/api/schedules/{self.standard.pk}/apply/", {"everyone": True, "start_date": "2026-06-01"}, format="json"
        )
        self.assertEqual(apply.status_code, 404)


class EmploymentTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        self.worker = Worker.objects.create(company=self.company, name="Arben")

    def test_employment_dates_and_allowance_are_saved_in_order(self):
        response = self.client.patch(
            f"/api/workers/{self.worker.pk}/",
            {"hired_on": "2026-03-01", "left_on": "2026-10-31", "leave_allowance": "22"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["leave_allowance"], "22.0")
        backwards = self.client.patch(f"/api/workers/{self.worker.pk}/", {"left_on": "2026-02-01"}, format="json")
        self.assertEqual(backwards.status_code, 400)

    def test_company_sets_the_default_days_off_per_year(self):
        response = self.client.patch("/api/companies/current/", {"leave_days_per_year": "25"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["leave_days_per_year"], "25.0")


class DaysOffTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        create_default_schedule(self.company)
        self.types = {leave_type.code: leave_type for leave_type in create_default_leave_types(self.company)}
        self.team = Team.objects.create(company=self.company, number=1, name="Facade crew")
        self.other_team = Team.objects.create(company=self.company, number=2, name="Roof crew")
        self.arben = Worker.objects.create(company=self.company, name="Arben", team=self.team)
        self.lira = Worker.objects.create(company=self.company, name="Lira", team=self.other_team)
        TeamMembership.objects.create(worker=self.arben, team=self.team)
        TeamMembership.objects.create(worker=self.lira, team=self.other_team)
        self.lead = make_user("lead@example.com")
        Membership.objects.create(user=self.lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        self.team.lead_user = self.lead
        self.team.save()
        self.lead_client = auth_client(self.lead, self.company)

    def ask(self, worker, start, end, code="V", client=None, **extra):
        body = {"worker": worker.pk, "leave_type": self.types[code].pk, "start_date": start, "end_date": end, **extra}
        return (client or self.client).post("/api/days-off/", body, format="json")

    def test_days_skip_weekends_and_holidays_and_managers_approve_at_once(self):
        Holiday.objects.create(company=self.company, date=date(2026, 6, 10), name="Bank holiday")
        response = self.ask(self.arben, "2026-06-08", "2026-06-14")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["days"], "4")
        self.assertEqual(response.data["status"], "approved")
        half = self.ask(self.arben, "2026-06-15", "2026-06-15", half_day=True)
        self.assertEqual(half.data["days"], "0.5")

    def test_overlaps_days_outside_employment_and_empty_ranges_are_refused(self):
        self.assertEqual(self.ask(self.arben, "2026-06-08", "2026-06-12").status_code, 201)
        self.assertEqual(self.ask(self.arben, "2026-06-12", "2026-06-16", code="S").status_code, 400)
        self.assertEqual(self.ask(self.arben, "2026-06-13", "2026-06-14").status_code, 400)
        self.arben.left_on = date(2026, 6, 30)
        self.arben.save()
        self.assertEqual(self.ask(self.arben, "2026-06-29", "2026-07-02").status_code, 400)
        self.assertEqual(self.ask(self.arben, "2026-06-17", "2026-06-16").status_code, 400)

    def test_leads_ask_for_their_own_team_and_managers_decide(self):
        response = self.ask(self.arben, "2026-06-08", "2026-06-09", client=self.lead_client, note="Wedding")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "requested")
        self.assertEqual(response.data["note"], "Wedding")
        self.assertEqual(self.ask(self.lira, "2026-06-08", "2026-06-09", client=self.lead_client).status_code, 403)
        leave_id = response.data["id"]
        self.assertEqual(self.lead_client.post(f"/api/days-off/{leave_id}/approve/").status_code, 403)
        approved = self.client.post(f"/api/days-off/{leave_id}/approve/")
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(self.client.post(f"/api/days-off/{leave_id}/approve/").status_code, 400)

    def test_leads_see_only_their_team_and_only_their_own_notes(self):
        self.ask(self.arben, "2026-06-08", "2026-06-08", code="S", note="Doctor")
        self.ask(self.lira, "2026-06-08", "2026-06-08")
        rows = self.lead_client.get("/api/days-off/").data["results"]
        self.assertEqual([row["worker_name"] for row in rows], ["Arben"])
        self.assertEqual(rows[0]["note"], "")
        self.assertEqual(self.client.get("/api/days-off/?worker=%s" % self.arben.pk).data["results"][0]["note"], "Doctor")

    def test_leads_withdraw_only_their_own_waiting_requests(self):
        mine = self.ask(self.arben, "2026-06-08", "2026-06-08", client=self.lead_client).data
        theirs = self.ask(self.arben, "2026-06-15", "2026-06-15").data
        self.assertEqual(self.lead_client.post(f"/api/days-off/{theirs['id']}/cancel/").status_code, 403)
        self.assertEqual(self.lead_client.post(f"/api/days-off/{mine['id']}/cancel/").data["status"], "cancelled")
        self.assertEqual(self.ask(self.arben, "2026-06-08", "2026-06-08").status_code, 201)

    def test_balances_count_vacation_against_the_allowance(self):
        today = self.company.today()
        year = today.year
        self.arben.leave_allowance = Decimal("22")
        self.arben.save()
        self.ask(self.arben, f"{year}-01-05", f"{year}-01-09")
        self.ask(self.arben, f"{year}-02-02", f"{year}-02-02", code="S")
        self.ask(self.arben, f"{year}-12-28", f"{year + 1}-01-08")
        self.ask(self.arben, f"{year}-03-02", f"{year}-03-02", client=self.lead_client)
        rows = {row["name"]: row for row in self.client.get(f"/api/days-off/balances/?year={year}").data}
        arben = rows["Arben"]
        self.assertEqual(arben["allowance"], "22.0")
        self.assertEqual(arben["waiting"], "1")
        self.assertEqual(arben["by_type"]["S"], "1")
        self.assertEqual(Decimal(arben["used"]) + Decimal(arben["planned"]), Decimal("9"))
        self.assertEqual(arben["left"], "13.0")
        self.assertEqual(rows["Lira"]["allowance"], "20.0")

    def test_preview_counts_days_and_the_vacation_left(self):
        response = self.client.get(
            "/api/days-off/preview/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-08", "end_date": "2026-06-19"},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["days"], "10")
        self.assertIsNotNone(response.data["left_after"])

    def test_type_flags_are_fixed_once_used_and_archived_types_cannot_be_chosen(self):
        sick = self.types["S"]
        self.ask(self.arben, "2026-06-08", "2026-06-08", code="S")
        response = self.client.patch(f"/api/leave-types/{sick.pk}/", {"paid": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.patch(f"/api/leave-types/{sick.pk}/", {"archived": True}, format="json").status_code, 200)
        self.assertEqual(self.ask(self.arben, "2026-06-15", "2026-06-15", code="S").status_code, 400)

    def test_teams_count_who_is_off_each_day(self):
        self.ask(self.arben, "2026-06-08", "2026-06-09")
        counts = self.client.get("/api/days-off/by-team/?from=2026-06-08&to=2026-06-14").data
        self.assertEqual(counts, {self.team.pk: {"2026-06-08": 1, "2026-06-09": 1}})

    def test_another_company_cannot_see_or_use_these_days_off(self):
        self.ask(self.arben, "2026-06-08", "2026-06-08")
        other = make_user("other@example.com")
        other_company = make_membership(other, "South").company
        other_client = auth_client(other, other_company)
        self.assertEqual(other_client.get("/api/days-off/").data["results"], [])
        own_type = create_default_leave_types(other_company)[0]
        foreign = other_client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": own_type.pk, "start_date": "2026-06-15", "end_date": "2026-06-15"},
            format="json",
        )
        self.assertEqual(foreign.status_code, 400)


class DayLogOffTests(TestCase):
    def setUp(self):
        from operations.models import WorkplaceTeam
        from operations.services import create_workplace

        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        create_default_schedule(self.company)
        self.vacation = create_default_leave_types(self.company)[0]
        self.team = Team.objects.create(company=self.company, number=1, name="Facade crew")
        self.worker = Worker.objects.create(company=self.company, name="Arben", team=self.team)
        TeamMembership.objects.create(worker=self.worker, team=self.team)
        self.project = create_workplace(company=self.company, name="Bridge")
        WorkplaceTeam.objects.create(workplace=self.project, team=self.team, start_date=date(2026, 6, 1))
        self.client.post(
            "/api/days-off/",
            {"worker": self.worker.pk, "leave_type": self.vacation.pk, "start_date": "2026-06-08", "end_date": "2026-06-08"},
            format="json",
        )
        self.other_lead = make_user("lead@example.com")
        Membership.objects.create(user=self.other_lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        roof = Team.objects.create(company=self.company, number=2, name="Roof crew", lead_user=self.other_lead)
        WorkplaceTeam.objects.create(workplace=self.project, team=roof, start_date=date(2026, 6, 1))

    def crew(self, client):
        day = client.get(f"/api/daily-logs/day/?workplace={self.project.pk}&date=2026-06-08").data
        return next(team for team in day["teams"] if team["team"] == self.team.pk)["crew"][0]

    def test_the_crew_shows_who_is_off_and_hides_the_kind_from_other_leads(self):
        self.assertEqual(self.crew(self.client)["off"]["name"], "Vacation")
        self.assertEqual(self.crew(auth_client(self.other_lead, self.company))["off"], {"code": "", "name": "Off", "half_day": False})


class HoursTestCase(TestCase):
    """A company with one crew placed on one project from 1 June 2026."""

    def setUp(self):
        from operations.models import WorkplaceTeam
        from operations.services import create_workplace

        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        create_default_schedule(self.company)
        self.types = {leave_type.code: leave_type for leave_type in create_default_leave_types(self.company)}
        self.team = Team.objects.create(company=self.company, number=1, name="Facade crew")
        self.arben = Worker.objects.create(company=self.company, name="Arben", team=self.team)
        self.drita = Worker.objects.create(company=self.company, name="Drita", team=self.team)
        for worker in (self.arben, self.drita):
            TeamMembership.objects.create(worker=worker, team=self.team)
        self.project = create_workplace(company=self.company, name="Bridge")
        WorkplaceTeam.objects.create(workplace=self.project, team=self.team, start_date=date(2026, 6, 1))
        self.lead = make_user("lead@example.com")
        Membership.objects.create(user=self.lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        self.team.lead_user = self.lead
        self.team.save()
        self.lead_client = auth_client(self.lead, self.company)

    def crew(self, day, workers, hours=None, client=None, workplace=None):
        body = {"workplace": (workplace or self.project).pk, "date": day, "team": self.team.pk, "worker_ids": [w.pk for w in workers]}
        if hours is not None:
            body["hours"] = {str(worker.pk): value for worker, value in hours.items()}
        return (client or self.client).put("/api/daily-logs/attendance/", body, format="json")

    def cell(self, worker, day, hours, client=None, **extra):
        return (client or self.client).put(
            "/api/timesheets/cell/", {"worker": worker.pk, "date": day, "hours": hours, **extra}, format="json"
        )

    def sheet(self, client=None, **params):
        return (client or self.client).get("/api/timesheets/", params).data

    def row(self, sheet, worker):
        return next(row for row in sheet["workers"] if row["worker"] == worker.pk)


class AttendanceHoursTests(HoursTestCase):
    def test_crew_hours_default_to_the_schedule_and_keep_what_was_saved(self):
        from sitelog.models import CrewAttendance

        self.assertEqual(self.crew("2026-06-08", [self.arben], {self.arben: "10"}).status_code, 200)
        self.assertEqual(self.crew("2026-06-08", [self.arben, self.drita]).status_code, 200)
        hours = dict(CrewAttendance.objects.filter(work_date=date(2026, 6, 8)).values_list("worker__name", "hours"))
        self.assertEqual(hours, {"Arben": Decimal("10.00"), "Drita": Decimal("8.00")})
        saturday = self.crew("2026-06-13", [self.arben])
        self.assertEqual(saturday.status_code, 200)
        self.assertEqual(saturday.data["teams"][0]["crew"][0]["hours"], "8.00")

    def test_too_many_hours_future_days_and_days_outside_employment_are_refused(self):
        from operations.models import WorkplaceTeam
        from operations.services import create_workplace

        school = create_workplace(company=self.company, name="School")
        WorkplaceTeam.objects.create(workplace=school, team=self.team, start_date=date(2026, 6, 1))
        self.assertEqual(self.crew("2026-06-08", [self.arben], {self.arben: "16"}).status_code, 200)
        self.assertEqual(self.crew("2026-06-08", [self.arben], {self.arben: "9"}, workplace=school).status_code, 400)
        tomorrow = self.company.today() + timedelta(days=1)
        self.assertEqual(self.crew(str(tomorrow), [self.arben]).status_code, 400)
        self.drita.hired_on = date(2026, 6, 10)
        self.drita.save()
        self.assertEqual(self.crew("2026-06-09", [self.drita]).status_code, 400)

    def test_a_worker_who_has_left_stays_on_past_crews(self):
        self.crew("2026-06-08", [self.arben, self.drita])
        self.drita.left_on = date(2026, 6, 12)
        self.drita.status = Worker.Status.INACTIVE
        self.drita.save()
        self.assertEqual(self.crew("2026-06-08", [self.arben, self.drita], {self.arben: "9"}).status_code, 200)
        day = self.client.get(f"/api/daily-logs/day/?workplace={self.project.pk}&date=2026-06-15").data
        self.assertEqual([member["name"] for member in day["teams"][0]["crew"]], ["Arben"])

    def test_deleting_a_worker_team_or_project_with_hours_is_refused(self):
        self.crew("2026-06-08", [self.arben])
        self.assertEqual(self.client.delete(f"/api/workers/{self.arben.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/teams/{self.team.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/projects/{self.project.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/workers/{self.drita.pk}/").status_code, 204)


class TimesheetTests(HoursTestCase):
    def test_typing_hours_records_crew_on_the_teams_project(self):
        from sitelog.models import CrewAttendance

        response = self.cell(self.arben, "2026-06-08", "9.5")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["worked"], "9.5")
        self.assertEqual(response.data["extra"], "1.5")
        row = CrewAttendance.objects.get(worker=self.arben)
        self.assertEqual((row.workplace_id, row.team_id, row.hours), (self.project.pk, self.team.pk, Decimal("9.50")))
        self.assertEqual(self.cell(self.arben, "2026-06-08", "0").data["worked"], "0")
        self.assertFalse(CrewAttendance.objects.filter(worker=self.arben).exists())

    def test_a_worker_who_changed_teams_is_put_on_their_team_of_that_day(self):
        from operations.models import WorkplaceTeam
        from operations.services import create_workplace
        from sitelog.models import CrewAttendance
        from workforce.services import move_worker

        roof = Team.objects.create(company=self.company, number=2, name="Roof crew")
        school = create_workplace(company=self.company, name="School")
        WorkplaceTeam.objects.create(workplace=school, team=roof, start_date=date(2026, 6, 1))
        move_worker(self.drita, roof, date(2026, 6, 10))
        self.assertEqual(self.cell(self.drita, "2026-06-09", "8").status_code, 200)
        self.assertEqual(self.cell(self.drita, "2026-06-11", "8").status_code, 200)
        rows = dict(CrewAttendance.objects.filter(worker=self.drita).values_list("work_date", "workplace__name"))
        self.assertEqual(rows, {date(2026, 6, 9): "Bridge", date(2026, 6, 11): "School"})

    def test_two_projects_on_one_day_need_the_day_panel(self):
        from operations.models import WorkplaceTeam
        from operations.services import create_workplace

        school = create_workplace(company=self.company, name="School")
        WorkplaceTeam.objects.create(workplace=school, team=self.team, start_date=date(2026, 6, 1))
        self.assertEqual(self.cell(self.arben, "2026-06-08", "8").status_code, 400)
        self.assertEqual(self.cell(self.arben, "2026-06-08", "8", workplace=school.pk).status_code, 200)
        day = self.client.get("/api/timesheets/day/", {"worker": self.arben.pk, "date": "2026-06-08"}).data
        self.assertEqual(len(day["placements"]), 2)
        self.assertEqual(day["cell"]["entries"][0]["project_name"], "School")

    def test_totals_count_days_extra_hours_days_off_and_missing_days(self):
        self.cell(self.arben, "2026-06-08", "10")
        self.cell(self.arben, "2026-06-09", "3")
        self.client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-10", "end_date": "2026-06-10", "half_day": True},
            format="json",
        )
        self.cell(self.arben, "2026-06-10", "4")
        self.client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["S"].pk, "start_date": "2026-06-11", "end_date": "2026-06-11"},
            format="json",
        )
        self.client.post("/api/other-work/", {"worker": self.arben.pk, "work_date": "2026-06-13", "hours": "5", "kind": "yard"}, format="json")
        sheet = self.sheet(**{"from": "2026-06-08", "to": "2026-06-14"})
        totals = self.row(sheet, self.arben)["totals"]
        self.assertEqual(totals["days"], "3")  # 10 h + 3 h (half) + 4 h (half, next to a half day off) + 5 h Saturday
        self.assertEqual(totals["hours"], "22")
        self.assertEqual(totals["extra"], "7")  # 2 on Monday and all 5 on Saturday
        self.assertEqual(totals["off"], {"V": "0.5", "S": "1"})
        self.assertEqual(totals["missing"], 1)  # Friday
        self.assertEqual(totals["worked_on_leave"], 0)

    def test_working_on_a_full_day_off_is_flagged_and_never_counted_twice(self):
        self.client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-08", "end_date": "2026-06-08"},
            format="json",
        )
        self.cell(self.arben, "2026-06-08", "8")
        row = self.row(self.sheet(**{"from": "2026-06-08", "to": "2026-06-08"}), self.arben)
        self.assertIn("worked_on_leave", row["cells"]["2026-06-08"]["flags"])
        self.assertEqual(row["totals"]["days"], "1")
        self.assertEqual(row["totals"]["off"], {})

    def test_fill_from_schedule_skips_days_off_holidays_and_recorded_days(self):
        Holiday.objects.create(company=self.company, date=date(2026, 6, 9), name="Bank holiday")
        self.client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-10", "end_date": "2026-06-10"},
            format="json",
        )
        self.cell(self.arben, "2026-06-11", "10")
        result = self.client.post("/api/timesheets/fill/", {"worker": self.arben.pk, "from": "2026-06-08", "to": "2026-06-14"}, format="json")
        self.assertEqual(result.data, {"filled": 2, "skipped": []})
        totals = self.row(self.sheet(**{"from": "2026-06-08", "to": "2026-06-14"}), self.arben)["totals"]
        self.assertEqual(totals["hours"], "26")

    def test_leads_read_their_team_but_change_hours_only_in_the_daily_log(self):
        outsider = Worker.objects.create(company=self.company, name="Lira")
        sheet = self.sheet(client=self.lead_client, **{"from": "2026-06-08", "to": "2026-06-14"})
        self.assertEqual({row["name"] for row in sheet["workers"]}, {"Arben", "Drita"})
        self.assertNotIn(outsider.pk, [row["worker"] for row in sheet["workers"]])
        self.assertEqual(self.cell(self.arben, "2026-06-08", "8", client=self.lead_client).status_code, 403)
        self.assertEqual(self.crew("2026-06-08", [self.arben], {self.arben: "9"}, client=self.lead_client).status_code, 200)

    def test_another_company_sees_no_rows_and_cannot_write(self):
        other = make_user("other@example.com")
        other_client = auth_client(other, make_membership(other, "South").company)
        self.assertEqual(other_client.get("/api/timesheets/", {"from": "2026-06-08", "to": "2026-06-14"}).data["workers"], [])
        self.assertEqual(self.cell(self.arben, "2026-06-08", "8", client=other_client).status_code, 404)


class PeriodTests(HoursTestCase):
    def setUp(self):
        super().setUp()
        from timesheets.periods import default_pay_group

        self.monthly = default_pay_group(self.company)
        self.weekly = PayGroup.objects.create(company=self.company, name="Weekly crew", cycle=PayGroup.Cycle.WEEKLY)
        self.client.post(f"/api/pay-groups/{self.weekly.pk}/assign/", {"worker_ids": [self.arben.pk], "start_date": "2026-06-01"}, format="json")

    def approve(self, group, start, end):
        return self.client.post(
            "/api/timesheet-periods/approve/", {"pay_group": group.pk, "start_date": start, "end_date": end}, format="json"
        )

    def test_each_group_has_its_own_period(self):
        weekly = self.sheet(pay_group=self.weekly.pk, date="2026-06-10")
        self.assertEqual((weekly["start"], weekly["end"]), ("2026-06-08", "2026-06-14"))
        self.assertEqual([row["name"] for row in weekly["workers"]], ["Arben"])
        monthly = self.sheet(pay_group=self.monthly.pk, date="2026-06-10")
        self.assertEqual((monthly["start"], monthly["end"]), ("2026-06-01", "2026-06-30"))
        self.assertEqual([row["name"] for row in monthly["workers"]], ["Drita"])

    def test_approving_a_week_locks_its_hours_days_off_and_calendar(self):
        self.cell(self.arben, "2026-06-08", "8")
        self.assertEqual(self.approve(self.weekly, "2026-06-08", "2026-06-10").status_code, 400)
        approved = self.approve(self.weekly, "2026-06-08", "2026-06-14")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], "approved")

        locked = self.cell(self.arben, "2026-06-09", "8")
        self.assertEqual(locked.status_code, 400)
        self.assertIn("Weekly crew", str(locked.data))
        self.assertEqual(self.crew("2026-06-09", [self.arben, self.drita]).status_code, 400)
        self.assertEqual(self.cell(self.drita, "2026-06-09", "8").status_code, 200)
        day_off = self.client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-12", "end_date": "2026-06-15"},
            format="json",
        )
        self.assertEqual(day_off.status_code, 400)
        self.assertEqual(self.client.post("/api/holidays/", {"date": "2026-06-11", "name": "Late"}, format="json").status_code, 400)
        version = self.client.post(
            f"/api/schedules/{WorkSchedule.objects.get(company=self.company).pk}/versions/",
            {"valid_from": "2026-06-01", "mon": 9},
            format="json",
        )
        self.assertEqual(version.status_code, 400)
        self.assertEqual(self.client.patch(f"/api/workers/{self.arben.pk}/", {"hired_on": "2026-06-10"}, format="json").status_code, 400)
        cell = self.sheet(pay_group=self.weekly.pk, date="2026-06-10")["workers"][0]["cells"]["2026-06-09"]
        self.assertTrue(cell["locked"])
        self.assertFalse(cell["editable"])

        period = self.client.get(f"/api/timesheet-periods/?pay_group={self.weekly.pk}").data[0]
        self.assertEqual(self.lead_client.post(f"/api/timesheet-periods/{period['id']}/reopen/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/timesheet-periods/{period['id']}/reopen/").data["status"], "open")
        self.assertEqual(self.cell(self.arben, "2026-06-09", "8").status_code, 200)

    def test_waiting_requests_block_approval(self):
        asked = self.client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-10", "end_date": "2026-06-10"},
            format="json",
        )
        self.assertEqual(asked.status_code, 201)
        self.client.post(f"/api/days-off/{asked.data['id']}/cancel/")
        request = self.lead_client.post(
            "/api/days-off/",
            {"worker": self.arben.pk, "leave_type": self.types["V"].pk, "start_date": "2026-06-10", "end_date": "2026-06-10"},
            format="json",
        )
        self.assertEqual(request.data["status"], "requested")
        response = self.approve(self.weekly, "2026-06-08", "2026-06-14")
        self.assertEqual(response.status_code, 400)
        self.assertIn("waiting", str(response.data))
        self.client.post(f"/api/days-off/{request.data['id']}/approve/")
        self.assertEqual(self.approve(self.weekly, "2026-06-08", "2026-06-14").status_code, 200)

    def test_moving_groups_starts_after_the_last_approved_period_and_never_counts_a_day_twice(self):
        self.approve(self.weekly, "2026-06-08", "2026-06-14")
        refused = self.client.post(
            f"/api/pay-groups/{self.monthly.pk}/assign/", {"worker_ids": [self.arben.pk], "start_date": "2026-06-10"}, format="json"
        )
        self.assertEqual(refused.status_code, 400)
        moved = self.client.post(
            f"/api/pay-groups/{self.monthly.pk}/assign/", {"worker_ids": [self.arben.pk], "start_date": "2026-06-15"}, format="json"
        )
        self.assertEqual(moved.status_code, 200, moved.data)
        june = self.row(self.sheet(pay_group=self.monthly.pk, date="2026-06-20"), self.arben)
        counted = sorted(day for day, cell in june["cells"].items() if cell["counted"])
        self.assertEqual(counted[0], "2026-06-15")
