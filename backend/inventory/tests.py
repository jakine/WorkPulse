from datetime import date
from decimal import Decimal

from django.test import TestCase

from companies.models import Membership
from companies.testing import auth_client, make_membership, make_user
from inventory.models import Location, StockItem, StockLot, StockMovement, StockType
from inventory.services import receive_stock
from operations.models import ProjectScope, SiteReport, WorkMeasure, Workplace, WorkplaceTeam, WorkType
from operations.services import create_default_measures, create_workplace, default_work_category
from workforce.models import Team


class InventoryApiTests(TestCase):
    def setUp(self):
        self.user = make_user("stock@example.com")
        self.membership = make_membership(self.user, "Yard")
        self.client = auth_client(self.user, self.membership.company)
        self.stock_type = StockType.objects.create(
            company=self.membership.company,
            name="Cement",
            requires_expiration=False,
        )
        self.item = StockItem.objects.create(
            company=self.membership.company,
            stock_type=self.stock_type,
            name="Portland",
            unit="bag",
        )
        self.warehouse = Location.objects.create(
            company=self.membership.company,
            name="Main yard",
            kind=Location.Kind.DEPOT,
        )

    def test_receive_transfer_and_consume_keep_quantities(self):
        received = self.client.post(
            "/api/stock-lots/",
            {
                "item": self.item.id,
                "location": self.warehouse.id,
                "quantity": "10.00",
                "received_on": "2026-06-01",
            },
            format="json",
        )
        self.assertEqual(received.status_code, 201)
        lot_id = received.data["id"]

        workplace = Workplace.objects.create(company=self.membership.company, name="Block A")
        site = Location.objects.create(
            company=self.membership.company,
            name="Block A",
            kind=Location.Kind.SITE,
            workplace=workplace,
        )
        transfer = self.client.post(
            "/api/stock-movements/",
            {
                "lot": lot_id,
                "kind": "transfer",
                "quantity": "4.00",
                "to_location": site.id,
                "happened_on": "2026-06-02",
            },
            format="json",
        )
        self.assertEqual(transfer.status_code, 201)
        self.assertEqual(transfer.data["workplace"], workplace.id)

        source = StockLot.objects.get(pk=lot_id)
        self.assertEqual(source.quantity, Decimal("6.00"))
        destination = StockLot.objects.get(location=site, item=self.item)
        self.assertEqual(destination.quantity, Decimal("4.00"))

        consume = self.client.post(
            "/api/stock-movements/",
            {
                "lot": destination.id,
                "kind": "consume",
                "quantity": "1.50",
                "workplace": workplace.id,
                "happened_on": "2026-06-03",
            },
            format="json",
        )
        self.assertEqual(consume.status_code, 201)
        destination.refresh_from_db()
        self.assertEqual(destination.quantity, Decimal("2.50"))

        too_much = self.client.post(
            "/api/stock-movements/",
            {
                "lot": destination.id,
                "kind": "consume",
                "quantity": "9.00",
                "workplace": workplace.id,
                "happened_on": "2026-06-03",
            },
            format="json",
        )
        self.assertEqual(too_much.status_code, 400)

    def test_expiration_is_required_only_when_the_type_asks_for_it(self):
        paint = StockType.objects.create(
            company=self.membership.company,
            name="Paint",
            requires_expiration=True,
        )
        item = StockItem.objects.create(
            company=self.membership.company,
            stock_type=paint,
            name="White",
            unit="can",
        )
        missing = self.client.post(
            "/api/stock-lots/",
            {
                "item": item.id,
                "location": self.warehouse.id,
                "quantity": "2.00",
                "received_on": "2026-06-01",
            },
            format="json",
        )
        self.assertEqual(missing.status_code, 400)

        dated = self.client.post(
            "/api/stock-lots/",
            {
                "item": item.id,
                "location": self.warehouse.id,
                "quantity": "2.00",
                "expires_on": "2026-07-01",
                "received_on": "2026-06-01",
            },
            format="json",
        )
        self.assertEqual(dated.status_code, 201)

        upcoming = self.client.get("/api/stock-lots/?expires_before=2026-08-01")
        self.assertEqual(upcoming.status_code, 200)
        self.assertEqual(len(upcoming.data["results"]), 1)
        self.assertEqual(upcoming.data["results"][0]["expires_on"], "2026-07-01")

    def test_adjust_cannot_go_negative(self):
        lot = StockLot.objects.create(
            item=self.item,
            location=self.warehouse,
            quantity=Decimal("3.00"),
            received_on=date(2026, 6, 1),
        )
        response = self.client.post(
            "/api/stock-movements/",
            {
                "lot": lot.id,
                "kind": "adjust",
                "quantity": "-5.00",
                "happened_on": "2026-06-04",
                "note": "Count was wrong",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        lot.refresh_from_db()
        self.assertEqual(lot.quantity, Decimal("3.00"))


class SiteMaterialTests(TestCase):
    """Facade plaster uses 1.4 kg adhesive per m². 500 kg arrive at the depot; 60 kg go to the Bridge site."""

    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.company = make_membership(self.owner, "River Co").company
        self.client = auth_client(self.owner, self.company)
        self.lead = make_user("mira@example.com")
        Membership.objects.create(user=self.lead, company=self.company, role=Membership.Role.TEAM_LEAD)
        self.lead_client = auth_client(self.lead, self.company)

        create_default_measures(self.company)
        measure = WorkMeasure.objects.get(company=self.company, symbol="m²")
        self.plaster = WorkType.objects.create(
            company=self.company, category=default_work_category(self.company), measure=measure, name="Facade plaster"
        )
        self.bridge = create_workplace(self.company, name="Bridge", status="active")
        self.yard = create_workplace(self.company, name="Yard", status="active")
        self.scope = ProjectScope.objects.create(workplace=self.bridge, work_type=self.plaster, planned_quantity=Decimal("100.00"))
        self.team = Team.objects.create(company=self.company, number=1, name="Mira's team", lead_user=self.lead)
        WorkplaceTeam.objects.create(workplace=self.bridge, team=self.team, start_date=date(2026, 6, 1))
        SiteReport.objects.create(
            workplace=self.bridge, team=self.team, scope=self.scope, work_date=date(2026, 6, 2), days=Decimal("1"), quantity=Decimal("50.00")
        )

        stock_type = StockType.objects.create(company=self.company, name="Bonding")
        self.adhesive = StockItem.objects.create(company=self.company, stock_type=stock_type, name="Adhesive", unit="kg")
        self.depot = Location.objects.create(company=self.company, name="Main depot", kind=Location.Kind.DEPOT)
        self.site = Location.objects.get(workplace=self.bridge)
        self.depot_lot, _ = receive_stock(
            company=self.company,
            item=self.adhesive,
            location=self.depot,
            quantity=Decimal("500.00"),
            expires_on=None,
            received_on=date(2026, 6, 1),
            note="",
            user=self.owner,
        )
        sent = self.move(self.client, self.depot_lot, "transfer", "60.00", to_location=self.site.pk)
        self.assertEqual(sent.status_code, 201)
        self.site_lot = StockLot.objects.get(item=self.adhesive, location=self.site)

    def move(self, client, lot, kind, quantity, **fields):
        return client.post(
            "/api/stock-movements/",
            {"lot": lot.pk, "kind": kind, "quantity": quantity, "happened_on": "2026-06-02", **fields},
            format="json",
        )

    def test_norms_compare_expected_with_actual_use_and_show_shortages(self):
        norm = self.client.post(
            "/api/work-type-materials/",
            {"work_type": self.plaster.pk, "item": self.adhesive.pk, "quantity_per_unit": "1.4"},
            format="json",
        )
        self.assertEqual(norm.status_code, 201)
        used = self.move(self.lead_client, self.site_lot, "consume", "55.00", workplace=self.bridge.pk, scope=self.scope.pk)
        self.assertEqual(used.status_code, 201)
        self.assertEqual(used.data["scope_name"], "Facade plaster")

        usage = self.client.get(f"/api/projects/{self.bridge.pk}/materials/")
        self.assertEqual(usage.status_code, 200)
        adhesive = usage.data["scopes"][0]["materials"][0]
        self.assertEqual(
            (adhesive["per_unit"], adhesive["expected"], adhesive["actual"], adhesive["variance"], adhesive["still_needed"]),
            ("1.4", "70.00", "55.00", "-15.00", "70.00"),
        )
        self.assertEqual(
            [(row["item_name"], row["on_site"], row["shortage"]) for row in usage.data["items"]], [("Adhesive", "5.00", "65.00")]
        )

    def test_leads_record_use_only_on_their_own_site_and_not_on_approved_days(self):
        self.assertEqual(self.move(self.lead_client, self.depot_lot, "consume", "5.00", workplace=self.bridge.pk).status_code, 403)
        self.assertEqual(self.move(self.lead_client, self.site_lot, "consume", "5.00", workplace=self.yard.pk).status_code, 403)
        self.assertEqual(
            self.move(self.lead_client, self.site_lot, "transfer", "5.00", to_location=self.depot.pk).status_code, 403
        )
        self.client.post("/api/daily-logs/approve/", {"workplace": self.bridge.pk, "date": "2026-06-02"}, format="json")
        locked = self.move(self.lead_client, self.site_lot, "consume", "5.00", workplace=self.bridge.pk)
        self.assertEqual(locked.status_code, 400)
        self.assertIn("approved", str(locked.data))

    def test_a_site_request_is_sent_from_the_depot_in_parts(self):
        created = self.lead_client.post(
            "/api/material-requests/",
            {"workplace": self.bridge.pk, "needed_by": "2026-06-05", "lines": [{"item": self.adhesive.pk, "quantity": "100.00"}]},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["status"], "open")
        request_id, line_id = created.data["id"], created.data["lines"][0]["id"]

        def send(client, quantity):
            return client.post(
                f"/api/material-requests/{request_id}/fulfil/",
                {"picks": [{"line": line_id, "lot": self.depot_lot.pk, "quantity": quantity}], "happened_on": "2026-06-03"},
                format="json",
            )

        self.assertEqual(send(self.lead_client, "60.00").status_code, 403)
        first = send(self.client, "60.00")
        self.assertEqual(first.status_code, 200)
        self.assertEqual((first.data["status"], first.data["lines"][0]["fulfilled_quantity"]), ("partly_fulfilled", "60.00"))
        self.site_lot.refresh_from_db()
        self.assertEqual(self.site_lot.quantity, Decimal("120.00"))
        self.assertEqual(send(self.client, "40.00").data["status"], "fulfilled")
        self.assertEqual(StockMovement.objects.filter(material_request_id=request_id).count(), 2)
        rejected = self.client.post(f"/api/material-requests/{request_id}/reject/", {"note": "Too late"}, format="json")
        self.assertEqual(rejected.status_code, 400)

    def test_low_stock_lists_items_below_their_level(self):
        level = self.client.post(
            "/api/stock-levels/",
            {"item": self.adhesive.pk, "location": self.depot.pk, "min_quantity": "450.00"},
            format="json",
        )
        self.assertEqual(level.status_code, 201)
        low = self.client.get("/api/stock-levels/low/")
        self.assertEqual([(row["item_name"], row["location_name"], row["on_hand"]) for row in low.data], [("Adhesive", "Main depot", "440.00")])

    def test_requests_stay_inside_their_company(self):
        self.client.post(
            "/api/material-requests/",
            {"workplace": self.bridge.pk, "lines": [{"item": self.adhesive.pk, "quantity": "10.00"}]},
            format="json",
        )
        other_user = make_user("other@example.com")
        other_client = auth_client(other_user, make_membership(other_user, "South").company)
        self.assertEqual(other_client.get("/api/material-requests/").data["results"], [])
        foreign = other_client.post(
            "/api/material-requests/",
            {"workplace": self.bridge.pk, "lines": [{"item": self.adhesive.pk, "quantity": "10.00"}]},
            format="json",
        )
        self.assertEqual(foreign.status_code, 404)
