from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from companies.models import Company, Membership
from companies.services import create_company
from inventory.models import (
    Location,
    MaterialRequest,
    StockItem,
    StockLevel,
    StockLot,
    StockMovement,
    StockType,
    WorkTypeMaterial,
)
from inventory.services import apply_movement, create_material_request, receive_stock
from operations.models import (
    DurationUnit,
    ProjectScope,
    SheetColumn,
    SiteReport,
    WorkMeasure,
    Workplace,
    WorkplaceTeam,
    WorkType,
    WorkTypeCategory,
)
from operations.services import (
    create_default_duration_units,
    create_default_measures,
    create_default_work_categories,
    create_headline_scope,
    create_workplace,
    default_duration_unit,
    default_work_category,
)
from work.models import Task, TaskPhase, TaskStatus
from work.services import create_default_phases, create_default_statuses, create_task
from sitelog.models import CrewAttendance, DailyLog, DailyLogIssue
from workforce.models import Team, TeamMembership, Worker, WorkerType
from workforce.services import move_worker

User = get_user_model()

DEMO_PASSWORD = "Manager-pass-123"


def user(email, password=DEMO_PASSWORD):
    found = User.objects.filter(username__iexact=email).first()
    if found:
        return found
    return User.objects.create_user(username=email, email=email, password=password)


def member(company, person, role):
    return Membership.objects.get_or_create(user=person, company=company, defaults={"role": role})[0]


def named(model, company, name, **defaults):
    return model.objects.get_or_create(company=company, name=name, defaults=defaults)[0]


class Command(BaseCommand):
    help = "Fill one company with people, teams, work types, projects, reports and stock for a walkthrough."

    def add_arguments(self, parser):
        parser.add_argument("--company", default="River Co", help="Company name to seed. Created if missing.")

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["company"]
        owner = User.objects.filter(email="manager@example.com").first() or user("manager@example.com")
        company = Company.objects.filter(name=name).first()
        if company is None:
            company = create_company(owner, name)
            self.stdout.write(f"Created company {company.name}")
        else:
            member(company, owner, Membership.Role.OWNER)
            create_default_measures(company)
            create_default_duration_units(company)
            create_default_work_categories(company)
            create_default_statuses(company)
            create_default_phases(company)

        office = user("office@example.com")
        mira = user("mira@example.com")
        arben = user("arben@example.com")
        lira = user("lira@example.com")
        member(company, office, Membership.Role.MANAGER)
        member(company, mira, Membership.Role.TEAM_LEAD)
        member(company, arben, Membership.Role.TEAM_LEAD)
        member(company, lira, Membership.Role.TEAM_LEAD)

        mason = named(WorkerType, company, "Mason")
        carpenter = named(WorkerType, company, "Carpenter")
        finisher = named(WorkerType, company, "Finisher")
        laborer = named(WorkerType, company, "Laborer")

        team_mira, _ = Team.objects.get_or_create(
            company=company,
            number=1,
            defaults={"name": "Mira's team", "worker_count": 4, "lead_note": "Mira", "lead_user": mira},
        )
        if team_mira.lead_user_id is None:
            team_mira.lead_user = mira
            team_mira.lead_note = team_mira.lead_note or "Mira"
            team_mira.save(update_fields=["lead_user", "lead_note"])
        team_arben, _ = Team.objects.get_or_create(
            company=company,
            number=2,
            defaults={"name": "Structure crew", "worker_count": 5, "lead_note": "Arben", "lead_user": arben},
        )
        if team_arben.lead_user_id is None:
            team_arben.lead_user = arben
            team_arben.save(update_fields=["lead_user"])
        team_lira, _ = Team.objects.get_or_create(
            company=company,
            number=3,
            defaults={"name": "Finishes crew", "worker_count": 3, "lead_note": "Lira", "lead_user": lira},
        )
        if team_lira.lead_user_id is None:
            team_lira.lead_user = lira
            team_lira.save(update_fields=["lead_user"])

        workers = (
            ("Mira", mason, team_mira),
            ("Niko", laborer, team_mira),
            ("Besnik", mason, team_mira),
            ("Drita", carpenter, team_mira),
            ("Arben", mason, team_arben),
            ("Genti", laborer, team_arben),
            ("Valon", carpenter, team_arben),
            ("Lira", finisher, team_lira),
            ("Ana", finisher, team_lira),
        )
        for worker_name, worker_type, team in workers:
            Worker.objects.get_or_create(
                company=company,
                name=worker_name,
                defaults={"worker_type": worker_type, "team": team, "status": Worker.Status.ACTIVE},
            )
        team_starts = {team_mira.id: date(2026, 3, 1), team_arben.id: date(2026, 5, 1), team_lira.id: date(2026, 9, 1)}
        for worker in Worker.objects.filter(company=company, team__isnull=False):
            if not worker.memberships.exists():
                TeamMembership.objects.create(worker=worker, team=worker.team, start_date=team_starts.get(worker.team_id))
        valon = Worker.objects.get(company=company, name="Valon")
        if valon.team_id == team_arben.id and not valon.memberships.filter(end_date__isnull=False).exists():
            move_worker(valon, team_lira, date(2026, 10, 1))
        for team in (team_mira, team_arben, team_lira):
            count = team.members.filter(status=Worker.Status.ACTIVE).count()
            if team.worker_count != count:
                team.worker_count = count
                team.save(update_fields=["worker_count"])

        categories = {row.name: row for row in WorkTypeCategory.objects.filter(company=company)}
        if "General" not in categories:
            default_work_category(company)
            categories = {row.name: row for row in WorkTypeCategory.objects.filter(company=company)}
        measures = {row.symbol: row for row in WorkMeasure.objects.filter(company=company)}
        work_types = {}
        for type_name, symbol, category_name in (
            ("Facade plaster", "m²", "Envelope"),
            ("North slab", "m³", "Structure"),
            ("Excavation", "m³", "Site"),
            ("Partition walls", "m²", "Finishes"),
            ("Rebar", "t", "Structure"),
        ):
            work_types[type_name] = named(
                WorkType,
                company,
                type_name,
                measure=measures[symbol],
                category=categories[category_name],
            )

        day = default_duration_unit(company, "day")
        week = default_duration_unit(company, "week")
        month = default_duration_unit(company, "month")
        statuses = {row.name: row for row in TaskStatus.objects.filter(company=company)}
        phases = {row.name: row for row in TaskPhase.objects.filter(company=company)}

        bridge = Workplace.objects.filter(company=company, name="Bridge site").first()
        if bridge is None:
            bridge = create_workplace(
                company,
                name="Bridge site",
                address="12 Bank",
                status=Workplace.Status.ACTIVE,
                start_date=date(2026, 3, 1),
                length_count=4,
                length_unit=month,
                work_type=work_types["Facade plaster"],
                planned_quantity=Decimal("800.00"),
            )
        else:
            bridge.address = bridge.address or "12 Bank"
            bridge.status = Workplace.Status.ACTIVE
            if bridge.length_count is None:
                bridge.length_count = 4
                bridge.length_unit = month
            if bridge.work_type_id is None:
                bridge.work_type = work_types["Facade plaster"]
                bridge.planned_quantity = Decimal("800.00")
            bridge.save()
            create_headline_scope(bridge)

        school = Workplace.objects.filter(company=company, name="School annex").first()
        if school is None:
            school = create_workplace(
                company,
                name="School annex",
                address="4 Oak Road",
                status=Workplace.Status.ACTIVE,
                start_date=date(2026, 9, 1),
                length_count=3,
                length_unit=month,
                work_type=work_types["Partition walls"],
                planned_quantity=Decimal("400.00"),
            )
        yard = Workplace.objects.filter(company=company, name="Yard wall").first()
        if yard is None:
            yard = create_workplace(
                company,
                name="Yard wall",
                address="Main yard edge",
                status=Workplace.Status.PLANNED,
                length_count=12,
                length_unit=day,
                work_type=work_types["Excavation"],
                planned_quantity=Decimal("80.00"),
            )

        self._scope(
            bridge,
            work_types["North slab"],
            Decimal("120.00"),
            length_count=6,
            length_unit=week,
            teams_needed=1,
        )
        facade_scope = bridge.scopes.filter(work_type=work_types["Facade plaster"]).first()
        if facade_scope and facade_scope.teams_needed is None:
            facade_scope.teams_needed = 2
            facade_scope.length_count = facade_scope.length_count or 4
            facade_scope.length_unit = facade_scope.length_unit or month
            facade_scope.save()
        school_scope = school.scopes.filter(work_type=work_types["Partition walls"]).first()
        if school_scope and school_scope.teams_needed is None:
            school_scope.teams_needed = 1
            school_scope.save(update_fields=["teams_needed"])

        for workplace, team, start in (
            (bridge, team_mira, date(2026, 3, 1)),
            (bridge, team_arben, date(2026, 5, 1)),
            (school, team_lira, date(2026, 9, 1)),
        ):
            WorkplaceTeam.objects.get_or_create(
                workplace=workplace,
                team=team,
                defaults={"start_date": start},
            )

        self._task(
            company,
            owner,
            bridge,
            "Pour north slab",
            status=statuses["In progress"],
            phase=phases["Execution"],
            team=team_arben,
            work_type=work_types["North slab"],
            priority=Task.Priority.HIGH,
            start_date=date(2026, 6, 1),
            due_date=date(2026, 6, 12),
            planned_quantity=Decimal("80.00"),
        )
        self._task(
            company,
            owner,
            bridge,
            "Plaster east elevation",
            status=statuses["To do"],
            phase=phases["Execution"],
            team=team_mira,
            work_type=work_types["Facade plaster"],
            priority=Task.Priority.MEDIUM,
            start_date=date(2026, 10, 6),
            due_date=date(2026, 10, 31),
            planned_quantity=Decimal("220.00"),
        )
        self._task(
            company,
            owner,
            bridge,
            "Tie deck rebar",
            status=statuses["Inspection"],
            phase=phases["Procurement"],
            team=team_arben,
            work_type=work_types["Rebar"],
            priority=Task.Priority.HIGH,
            start_date=date(2026, 9, 15),
            due_date=date(2026, 10, 10),
            planned_quantity=Decimal("8.00"),
        )
        self._task(
            company,
            owner,
            school,
            "Set first-floor partitions",
            status=statuses["In progress"],
            phase=phases["Execution"],
            team=team_lira,
            work_type=work_types["Partition walls"],
            priority=Task.Priority.MEDIUM,
            start_date=date(2026, 10, 1),
            due_date=date(2026, 11, 15),
            planned_quantity=Decimal("180.00"),
        )
        self._task(
            company,
            owner,
            school,
            "Close-out punch list",
            status=statuses["To do"],
            phase=phases["Post construction"],
            team=team_lira,
            priority=Task.Priority.LOW,
            start_date=date(2026, 11, 20),
            due_date=date(2026, 12, 5),
        )
        self._task(
            company,
            owner,
            yard,
            "Dig footing trench",
            status=statuses["To do"],
            phase=phases["Preconstruction"],
            work_type=work_types["Excavation"],
            priority=Task.Priority.MEDIUM,
            planned_quantity=Decimal("80.00"),
        )

        slab_scope = bridge.scopes.filter(work_type=work_types["North slab"]).first()
        self._sheet_column(bridge, SheetColumn.Kind.WORK_TYPE, scope=facade_scope, position=0)
        self._sheet_column(bridge, SheetColumn.Kind.WORK_TYPE, scope=slab_scope, position=1)
        self._sheet_column(bridge, SheetColumn.Kind.TEXT, name="Weather", position=2)
        self._sheet_column(school, SheetColumn.Kind.WORK_TYPE, scope=school_scope, position=0)
        self._sheet_column(school, SheetColumn.Kind.TEAM, team=team_lira, position=1)
        self._report(bridge, team_arben, date(2026, 6, 3), Decimal("1.00"), Decimal("25.00"), slab_scope, "North bay pour")
        self._report(bridge, team_arben, date(2026, 6, 4), Decimal("1.00"), Decimal("30.00"), slab_scope, "Second bay")
        self._report(bridge, team_mira, date(2026, 10, 8), Decimal("1.00"), Decimal("40.00"), facade_scope, "East scaffold")
        self._report(bridge, team_mira, date(2026, 10, 9), Decimal("1.00"), Decimal("35.00"), facade_scope, "East return")
        self._report(school, team_lira, date(2026, 10, 14), Decimal("1.00"), Decimal("60.00"), school_scope, "Grid A-C")
        self._report(school, team_lira, date(2026, 10, 15), Decimal("1.00"), Decimal("45.00"), school_scope, "Grid C-E")

        people = {worker.name: worker for worker in Worker.objects.filter(company=company)}
        for workplace, team, day, names in (
            (bridge, team_mira, date(2026, 10, 8), ("Mira", "Niko", "Besnik")),
            (bridge, team_mira, date(2026, 10, 9), ("Mira", "Niko", "Besnik", "Drita")),
            (school, team_lira, date(2026, 10, 14), ("Lira", "Ana", "Valon")),
            (school, team_lira, date(2026, 10, 15), ("Lira", "Ana")),
        ):
            for name in names:
                CrewAttendance.objects.get_or_create(
                    workplace=workplace, work_date=day, worker=people[name], defaults={"team": team}
                )
        approved, created = DailyLog.objects.get_or_create(
            workplace=bridge,
            work_date=date(2026, 10, 8),
            defaults={"weather": "Dry, 16 °C", "notes": "East scaffold up. Inspector signed off the first lift."},
        )
        if created:
            approved.status = DailyLog.Status.APPROVED
            approved.approved_by = owner
            approved.approved_at = timezone.now()
            approved.save(update_fields=["status", "approved_by", "approved_at"])
        for workplace, day, weather, kind, description, hours in (
            (bridge, date(2026, 10, 9), "Cloudy, 14 °C", DailyLogIssue.Kind.MATERIAL, "Adhesive delivery came at 11:00", "1.50"),
            (school, date(2026, 10, 15), "Rain from 15:00", DailyLogIssue.Kind.WEATHER, "Rain stopped outside work", "2.00"),
        ):
            log, _ = DailyLog.objects.get_or_create(workplace=workplace, work_date=day, defaults={"weather": weather})
            DailyLogIssue.objects.get_or_create(
                log=log,
                description=description,
                defaults={"kind": kind, "hours_lost": Decimal(hours), "created_by": owner},
            )

        depot = Location.objects.filter(company=company, kind=Location.Kind.DEPOT).first()
        if depot is None:
            depot = Location.objects.create(company=company, name="Main yard", kind=Location.Kind.DEPOT)
        material = named(StockType, company, "Material")
        named(StockType, company, "Paint", requires_expiration=True)
        cement = named(StockItem, company, "Cement bags", stock_type=material, unit="bags")
        rebar = named(StockItem, company, "Rebar 12mm", stock_type=material, unit="t")
        mesh = named(StockItem, company, "Facade mesh", stock_type=material, unit="rolls")
        self._receive(company, owner, cement, depot, Decimal("200.00"), date(2026, 5, 1), "Opening cement")
        self._receive(company, owner, rebar, depot, Decimal("15.00"), date(2026, 5, 2), "Opening rebar")
        self._receive(company, owner, mesh, depot, Decimal("40.00"), date(2026, 5, 3), "Opening mesh")
        site = Location.objects.get(workplace=bridge)
        self._transfer(company, owner, cement, depot, site, Decimal("40.00"), date(2026, 6, 1), "To bridge")
        self._transfer(company, owner, rebar, depot, site, Decimal("6.00"), date(2026, 6, 1), "To bridge")
        self._consume(company, owner, cement, site, bridge, Decimal("12.00"), date(2026, 6, 3), "Slab pour")
        StockMovement.objects.filter(
            company=company, lot__item=cement, workplace=bridge, kind=StockMovement.Kind.CONSUME, scope__isnull=True
        ).update(scope=slab_scope)

        for work_type, item, per_unit in (
            (work_types["North slab"], cement, Decimal("7")),
            (work_types["North slab"], rebar, Decimal("0.1")),
            (work_types["Facade plaster"], mesh, Decimal("0.02")),
        ):
            WorkTypeMaterial.objects.get_or_create(work_type=work_type, item=item, defaults={"quantity_per_unit": per_unit})
        for item, location, minimum in ((cement, depot, Decimal("180.00")), (mesh, site, Decimal("5.00"))):
            StockLevel.objects.get_or_create(item=item, location=location, defaults={"min_quantity": minimum})
        if not MaterialRequest.objects.filter(company=company, workplace=bridge).exists():
            create_material_request(
                company=company,
                workplace=bridge,
                user=mira,
                lines=[{"item": mesh, "quantity": Decimal("10.00")}],
                needed_by=date(2026, 11, 6),
                note="East elevation starts next week",
            )

        self.stdout.write(self.style.SUCCESS(f"Demo data is ready for {company.name}."))
        self.stdout.write("Log in as:")
        self.stdout.write(f"  owner      manager@example.com / {DEMO_PASSWORD}")
        self.stdout.write(f"  manager    office@example.com / {DEMO_PASSWORD}")
        self.stdout.write(f"  team lead  mira@example.com / {DEMO_PASSWORD}   (team 1)")
        self.stdout.write(f"  team lead  arben@example.com / {DEMO_PASSWORD}  (team 2)")
        self.stdout.write(f"  team lead  lira@example.com / {DEMO_PASSWORD}   (team 3)")
        self.stdout.write("Walk through Projects → Bridge site (overview, board, timeline, teams, reports, stock).")

    def _sheet_column(self, workplace, kind, *, name="", scope=None, team=None, position=0):
        if workplace is None:
            return None
        if kind == SheetColumn.Kind.WORK_TYPE and scope is None:
            return None
        if kind == SheetColumn.Kind.TEAM and team is None:
            return None
        if kind == SheetColumn.Kind.WORK_TYPE and scope is not None:
            found = SheetColumn.objects.filter(workplace=workplace, kind=kind, scope=scope).first()
        elif kind == SheetColumn.Kind.TEAM and team is not None:
            found = SheetColumn.objects.filter(workplace=workplace, kind=kind, team=team).first()
        else:
            found = SheetColumn.objects.filter(workplace=workplace, kind=kind, name=name).first()
        if found is not None:
            return found
        return SheetColumn.objects.create(
            workplace=workplace,
            kind=kind,
            name=name,
            scope=scope,
            team=team,
            position=position,
        )

    def _scope(self, workplace, work_type, planned, **fields):
        return ProjectScope.objects.get_or_create(
            workplace=workplace,
            work_type=work_type,
            defaults={"planned_quantity": planned, "position": workplace.scopes.count(), **fields},
        )[0]

    def _task(self, company, created_by, project, title, **fields):
        existing = Task.objects.filter(company=company, project=project, title=title).first()
        if existing is None:
            return create_task(company, project, created_by, title=title, **fields)
        changed = []
        for key in ("work_type", "team", "start_date", "due_date", "planned_quantity"):
            if fields.get(key) is not None and getattr(existing, key) is None:
                setattr(existing, key, fields[key])
                changed.append(key)
        if changed:
            existing.save(update_fields=changed)
        return existing

    def _report(self, workplace, team, work_date, days, quantity, scope, note):
        SiteReport.objects.get_or_create(
            workplace=workplace,
            team=team,
            work_date=work_date,
            defaults={"days": days, "quantity": quantity, "scope": scope, "note": note},
        )

    def _receive(self, company, person, item, location, quantity, received_on, note):
        if StockLot.objects.filter(item=item, location=location).exists():
            return
        receive_stock(
            company=company,
            item=item,
            location=location,
            quantity=quantity,
            expires_on=None,
            received_on=received_on,
            note=note,
            user=person,
        )

    def _transfer(self, company, person, item, from_location, to_location, quantity, happened_on, note):
        if StockLot.objects.filter(item=item, location=to_location).exists():
            return
        source = StockLot.objects.filter(item=item, location=from_location).first()
        if source is None:
            return
        apply_movement(
            company=company,
            lot=source,
            kind="transfer",
            quantity=quantity,
            to_location=to_location,
            workplace=to_location.workplace,
            happened_on=happened_on,
            note=note,
            user=person,
        )

    def _consume(self, company, person, item, location, workplace, quantity, happened_on, note):
        if StockMovement.objects.filter(company=company, lot__item=item, workplace=workplace, kind="consume").exists():
            return
        lot = StockLot.objects.filter(item=item, location=location).first()
        if lot is None or lot.quantity < quantity:
            return
        apply_movement(
            company=company,
            lot=lot,
            kind="consume",
            quantity=quantity,
            to_location=None,
            workplace=workplace,
            happened_on=happened_on,
            note=note,
            user=person,
        )
