from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from companies.models import Membership
from companies.testing import auth_client, make_membership, make_user
from core.models import ActivityEvent
from operations.models import WorkplaceTeam
from operations.services import create_workplace
from payroll.models import PayAdjustment, PayRate, Payment, PaySettings
from payroll.services import live_lines
from sitelog.models import CrewAttendance
from timesheets.leave import create_default_leave_types
from timesheets.models import Holiday, Leave, PayGroup
from timesheets.periods import approve_period, default_pay_group, move_to_pay_group
from timesheets.services import create_default_schedule
from workforce.models import Team, TeamMembership, Worker

JUNE = (date(2026, 6, 1), date(2026, 6, 30))  # 22 weekdays


class PayTestCase(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        create_default_schedule(self.company)
        self.types = {leave_type.code: leave_type for leave_type in create_default_leave_types(self.company)}
        self.monthly = default_pay_group(self.company)
        self.team = Team.objects.create(company=self.company, number=1, name="Facade crew")
        self.project = create_workplace(company=self.company, name="Bridge")
        WorkplaceTeam.objects.create(workplace=self.project, team=self.team, start_date=date(2026, 5, 1))
        self.settings = PaySettings.objects.create(company=self.company, extra_hours_multiplier=Decimal("1.5"))

    def worker(self, name, **fields):
        worker = Worker.objects.create(company=self.company, name=name, team=self.team, **fields)
        TeamMembership.objects.create(worker=worker, team=self.team)
        return worker

    def rate(self, worker, pay_type, amount, start=date(2026, 1, 1)):
        return PayRate.objects.create(company=self.company, worker=worker, start_date=start, pay_type=pay_type, amount=Decimal(amount))

    def work(self, worker, day, hours="8"):
        CrewAttendance.objects.create(workplace=self.project, team=self.team, worker=worker, work_date=day, hours=Decimal(hours))

    def work_weekdays(self, worker, start, end, hours="8"):
        day = start
        while day <= end:
            if day.weekday() < 5:
                self.work(worker, day, hours)
            day += timedelta(days=1)

    def day_off(self, worker, code, start, end=None, half_day=False):
        return Leave.objects.create(
            company=self.company,
            worker=worker,
            leave_type=self.types[code],
            start_date=start,
            end_date=end or start,
            half_day=half_day,
            status=Leave.Status.APPROVED,
        )

    def line(self, worker, group=None, period=JUNE):
        lines = {line_worker.pk: line for line_worker, line, _ in live_lines(group or self.monthly, *period)}
        return lines[worker.pk]


class DayRateTests(PayTestCase):
    def test_days_half_days_days_off_holidays_and_extra_hours(self):
        arben = self.worker("Arben")
        self.rate(arben, PayRate.PayType.DAILY, "60")
        Holiday.objects.create(company=self.company, date=date(2026, 6, 12), name="Bank holiday")
        self.work(arben, date(2026, 6, 8), "10")  # a day, 2 extra hours
        self.work(arben, date(2026, 6, 9), "3")  # half a day
        self.day_off(arben, "V", date(2026, 6, 10), half_day=True)
        self.work(arben, date(2026, 6, 10), "4")  # half a day worked + half a day of paid vacation
        self.day_off(arben, "U", date(2026, 6, 11))  # unpaid: nothing
        self.work(arben, date(2026, 6, 13), "5")  # Saturday, unscheduled: a day, no extra under 8 h
        line = self.line(arben, period=(date(2026, 6, 8), date(2026, 6, 14)))
        self.assertEqual(line.days, Decimal("3"))
        self.assertEqual(line.base, Decimal("180.00"))
        self.assertEqual(line.off_pay, Decimal("30.00"))
        self.assertEqual(line.holiday_pay, Decimal("60.00"))
        self.assertEqual(line.extra_hours, Decimal("2"))
        self.assertEqual(line.extra_pay, Decimal("22.50"))  # 2 h × 60 ÷ 8 × 1.5
        self.assertEqual(line.net, Decimal("292.50"))

    def test_holidays_are_unpaid_when_the_company_says_so_or_inside_unpaid_leave(self):
        arben = self.worker("Arben")
        self.rate(arben, PayRate.PayType.DAILY, "60")
        Holiday.objects.create(company=self.company, date=date(2026, 6, 10), name="Bank holiday")
        Holiday.objects.create(company=self.company, date=date(2026, 6, 17), name="Other holiday")
        self.day_off(arben, "U", date(2026, 6, 9), date(2026, 6, 11))
        line = self.line(arben)
        self.assertEqual(line.holiday_pay, Decimal("60.00"))  # only the 17th
        self.settings.pay_holidays_for_day_rate = False
        self.settings.save()
        self.assertEqual(self.line(arben).holiday_pay, Decimal("0.00"))

    def test_a_rate_change_mid_period_pays_each_day_at_its_own_rate(self):
        arben = self.worker("Arben")
        self.rate(arben, PayRate.PayType.DAILY, "60")
        self.rate(arben, PayRate.PayType.DAILY, "70", start=date(2026, 6, 15))
        self.work_weekdays(arben, *JUNE)
        self.assertEqual(self.line(arben).base, Decimal("10") * 60 + Decimal("12") * 70)

    def test_no_extra_pay_without_a_multiplier_and_two_projects_count_once(self):
        arben = self.worker("Arben")
        self.rate(arben, PayRate.PayType.DAILY, "60")
        school = create_workplace(company=self.company, name="School")
        self.work(arben, date(2026, 6, 8), "6")
        CrewAttendance.objects.create(workplace=school, team=self.team, worker=arben, work_date=date(2026, 6, 8), hours=Decimal("5"))
        self.settings.extra_hours_multiplier = None
        self.settings.save()
        line = self.line(arben)
        self.assertEqual((line.days, line.extra_hours, line.extra_pay), (Decimal("1"), Decimal("3"), Decimal("0.00")))


class FixedPayTests(PayTestCase):
    def test_a_full_month_is_exactly_the_monthly_amount_whatever_was_recorded(self):
        drita = self.worker("Drita")
        self.rate(drita, PayRate.PayType.MONTHLY, "1300")
        self.work_weekdays(drita, date(2026, 6, 1), date(2026, 6, 19))
        line = self.line(drita)
        self.assertEqual(line.base, Decimal("1300.00"))
        self.assertEqual(line.unrecorded, 7)  # paid anyway, shown in the breakdown

    def test_someone_hired_on_the_fifteenth_earns_about_half(self):
        drita = self.worker("Drita", hired_on=date(2026, 6, 15))
        self.rate(drita, PayRate.PayType.MONTHLY, "1200")
        self.assertEqual(self.line(drita).base, Decimal("654.55"))  # 1200 × 12 ÷ 22

    def test_unpaid_days_off_come_off_including_a_holiday_inside_them(self):
        drita = self.worker("Drita")
        self.rate(drita, PayRate.PayType.MONTHLY, "1100")
        Holiday.objects.create(company=self.company, date=date(2026, 6, 10), name="Bank holiday")
        Holiday.objects.create(company=self.company, date=date(2026, 6, 24), name="Paid holiday")
        self.day_off(drita, "U", date(2026, 6, 8), date(2026, 6, 12))
        self.day_off(drita, "V", date(2026, 6, 15))
        line = self.line(drita)
        self.assertEqual(line.base, Decimal("850.00"))  # 1100 × 17 ÷ 22
        self.assertEqual(line.unpaid_off_days, Decimal("4"))

    def test_a_weekly_amount_inside_a_monthly_period_splits_edge_weeks_by_day(self):
        lira = self.worker("Lira")
        self.rate(lira, PayRate.PayType.WEEKLY, "300")
        line = self.line(lira)
        self.assertEqual(line.base, Decimal("1320.00"))  # four full weeks and 2 of 5 days of the last

    def test_extra_hours_on_fixed_pay_include_every_hour_on_a_saturday(self):
        drita = self.worker("Drita")
        self.rate(drita, PayRate.PayType.MONTHLY, "1760")
        self.work(drita, date(2026, 6, 8), "9")
        self.work(drita, date(2026, 6, 13), "4")
        line = self.line(drita)
        self.assertEqual(line.extra_hours, Decimal("5"))
        self.assertEqual(line.extra_pay, Decimal("75.00"))  # 5 h × 1760 ÷ 176 h × 1.5


class PayRunTests(PayTestCase):
    def setUp(self):
        super().setUp()
        self.weekly = PayGroup.objects.create(company=self.company, name="Weekly crew", cycle=PayGroup.Cycle.WEEKLY)
        self.arben = self.worker("Arben")
        move_to_pay_group(self.arben, self.weekly, date(2026, 6, 1))
        self.rate(self.arben, PayRate.PayType.DAILY, "60")
        self.week = {"pay_group": self.weekly.pk, "start_date": "2026-06-08", "end_date": "2026-06-14"}

    def approve_pay(self, week=None):
        return self.client.post("/api/pay-runs/approve/", week or self.week, format="json")

    def view(self, day="2026-06-10"):
        return self.client.get(f"/api/pay-runs/view/?pay_group={self.weekly.pk}&date={day}").data

    def test_pay_needs_approved_hours_and_a_rate_for_everyone(self):
        self.work_weekdays(self.arben, date(2026, 6, 8), date(2026, 6, 12))
        self.assertEqual(self.approve_pay().status_code, 400)
        drita = self.worker("Drita")
        move_to_pay_group(drita, self.weekly, date(2026, 6, 1))
        self.work(drita, date(2026, 6, 8))
        approve_period(self.weekly, date(2026, 6, 8), date(2026, 6, 14), self.owner)
        missing = self.approve_pay()
        self.assertEqual(missing.status_code, 400)
        self.assertIn("Drita", str(missing.data))
        self.rate(drita, PayRate.PayType.NOT_PAID_HERE, "0")
        self.assertEqual(self.approve_pay().status_code, 200)
        self.assertEqual([line["worker_name"] for line in self.view()["lines"]], ["Arben"])

    def test_an_advance_lowers_what_is_paid_and_a_late_bonus_lands_in_the_next_run(self):
        self.work_weekdays(self.arben, date(2026, 6, 8), date(2026, 6, 12))
        Payment.objects.create(company=self.company, worker=self.arben, paid_on=date(2026, 6, 10), amount=Decimal("100"), kind="advance")
        approve_period(self.weekly, date(2026, 6, 8), date(2026, 6, 14), self.owner)
        draft = self.view()["lines"][0]
        self.assertEqual((draft["net"], draft["to_pay"]), ("300.00", "200.00"))
        self.assertEqual(self.approve_pay().status_code, 200)
        line = self.view()["lines"][0]
        self.assertEqual(line["to_pay"], "200.00")

        late = PayAdjustment.objects.create(company=self.company, worker=self.arben, date=date(2026, 6, 12), kind="bonus", amount=Decimal("50"))
        self.client.post("/api/payments/", {"worker": self.arben.pk, "paid_on": "2026-06-15", "amount": "200", "kind": "wages"}, format="json")
        self.assertEqual(self.client.get("/api/pay/owed/").data, [])
        self.work(self.arben, date(2026, 6, 15))
        approve_period(self.weekly, date(2026, 6, 15), date(2026, 6, 21), self.owner)
        self.assertEqual(self.approve_pay({**self.week, "start_date": "2026-06-15", "end_date": "2026-06-21"}).status_code, 200)
        next_line = self.view("2026-06-17")["lines"][0]
        self.assertEqual((next_line["bonuses"], next_line["net"]), ("50.00", "110.00"))
        late.refresh_from_db()
        self.assertIsNotNone(late.pay_line_id)
        self.assertEqual(self.client.patch(f"/api/pay-adjustments/{late.pk}/", {"amount": "60"}, format="json").status_code, 400)

    def test_advances_bigger_than_pay_carry_over(self):
        self.work(self.arben, date(2026, 6, 8))
        Payment.objects.create(company=self.company, worker=self.arben, paid_on=date(2026, 6, 9), amount=Decimal("100"), kind="advance")
        approve_period(self.weekly, date(2026, 6, 8), date(2026, 6, 14), self.owner)
        self.approve_pay()
        self.assertEqual(self.client.get("/api/pay/owed/").data, [{"worker": self.arben.pk, "name": "Arben", "owed": "-40.00"}])
        self.work(self.arben, date(2026, 6, 15))
        approve_period(self.weekly, date(2026, 6, 15), date(2026, 6, 21), self.owner)
        self.approve_pay({**self.week, "start_date": "2026-06-15", "end_date": "2026-06-21"})
        self.assertEqual(self.view("2026-06-17")["lines"][0]["to_pay"], "20.00")

    def test_approved_pay_locks_the_hours_rates_and_only_the_latest_run_reopens(self):
        self.work_weekdays(self.arben, date(2026, 6, 8), date(2026, 6, 12))
        period = approve_period(self.weekly, date(2026, 6, 8), date(2026, 6, 14), self.owner)
        self.approve_pay()
        manager = make_user("office@example.com")
        Membership.objects.create(user=manager, company=self.company, role=Membership.Role.MANAGER)
        reopen_hours = auth_client(manager, self.company).post(f"/api/timesheet-periods/{period.pk}/reopen/")
        self.assertEqual(reopen_hours.status_code, 400)
        self.assertIn("owner must reopen pay", str(reopen_hours.data))
        rate = self.client.post(
            "/api/pay-rates/", {"worker": self.arben.pk, "start_date": "2026-06-10", "pay_type": "daily", "amount": "65"}, format="json"
        )
        self.assertEqual(rate.status_code, 400)

        self.work(self.arben, date(2026, 6, 15))
        approve_period(self.weekly, date(2026, 6, 15), date(2026, 6, 21), self.owner)
        self.approve_pay({**self.week, "start_date": "2026-06-15", "end_date": "2026-06-21"})
        first_run = self.view()["run"]["id"]
        self.assertEqual(self.client.post(f"/api/pay-runs/{first_run}/reopen/").status_code, 400)
        latest = self.view("2026-06-17")["run"]["id"]
        self.assertEqual(self.client.post(f"/api/pay-runs/{latest}/reopen/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/pay-runs/{first_run}/reopen/").status_code, 200)
        self.assertEqual(auth_client(manager, self.company).post(f"/api/timesheet-periods/{period.pk}/reopen/").status_code, 200)

    def test_the_export_opens_cleanly_in_a_spreadsheet(self):
        self.arben.name = "=Arbën"
        self.arben.save()
        self.work_weekdays(self.arben, date(2026, 6, 8), date(2026, 6, 12))
        approve_period(self.weekly, date(2026, 6, 8), date(2026, 6, 14), self.owner)
        self.approve_pay()
        response = self.client.get(f"/api/pay-runs/{self.view()['run']['id']}/export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿Worker,Pay type,Rate"))
        self.assertIn("'=Arbën,Per day,60.00,5,40", text)


class PayPrivacyTests(PayTestCase):
    def test_only_the_owner_sees_any_pay(self):
        arben = self.worker("Arben")
        rate = self.rate(arben, PayRate.PayType.DAILY, "60")
        routes = [
            ("get", "/api/pay/settings/"),
            ("get", "/api/pay/owed/"),
            ("get", "/api/pay-rates/"),
            ("post", "/api/pay-rates/"),
            ("get", f"/api/pay-rates/{rate.pk}/"),
            ("get", "/api/pay-adjustments/"),
            ("get", "/api/payments/"),
            ("post", "/api/payments/"),
            ("get", f"/api/pay-runs/periods/?pay_group={self.monthly.pk}"),
            ("get", f"/api/pay-runs/view/?pay_group={self.monthly.pk}"),
            ("post", "/api/pay-runs/approve/"),
            ("get", "/api/pay-lines/1/"),
        ]
        manager = make_user("office@example.com")
        Membership.objects.create(user=manager, company=self.company, role=Membership.Role.MANAGER)
        lead = make_user("lead@example.com")
        Membership.objects.create(user=lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        for user in (manager, lead):
            client = auth_client(user, self.company)
            for method, path in routes:
                self.assertEqual(getattr(client, method)(path, {}, format="json").status_code, 403, (user.email, path))
            worker = client.get(f"/api/workers/{arben.pk}/").data
            self.assertFalse({"rate", "pay_rates", "amount", "pay"} & set(worker))
        self.assertEqual(self.client.get("/api/pay-rates/").status_code, 200)
        self.assertFalse(ActivityEvent.objects.filter(verb__startswith="pay.").exists())

    def test_another_companys_owner_sees_none_of_it(self):
        arben = self.worker("Arben")
        self.rate(arben, PayRate.PayType.DAILY, "60")
        other = make_user("other@example.com")
        other_client = auth_client(other, make_membership(other, "South").company)
        self.assertEqual(other_client.get("/api/pay-rates/").data, [])
        foreign = other_client.post(
            "/api/payments/", {"worker": arben.pk, "paid_on": "2026-06-10", "amount": "10", "kind": "advance"}, format="json"
        )
        self.assertEqual(foreign.status_code, 400)
        self.assertEqual(other_client.get(f"/api/pay-runs/view/?pay_group={self.monthly.pk}").status_code, 404)
