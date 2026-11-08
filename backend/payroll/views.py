"""Pay endpoints. Every one is the owner's alone (CanSeePay), and none writes to the shared activity feed."""

from datetime import timedelta

from django.db.models import Sum
from django.http import HttpResponse
from django.utils.text import slugify
from rest_framework import mixins, renderers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from companies.permissions import CanSeePay
from companies.viewsets import CompanyScopedViewSet
from core.views import FileRenderer
from payroll.models import PayAdjustment, PayLine, PayRate, PayRun, Payment
from payroll.serializers import (
    PayAdjustmentSerializer,
    PayLineSerializer,
    PaymentSerializer,
    PayPeriodSerializer,
    PayQuerySerializer,
    PayRateSerializer,
    PaySettingsSerializer,
)
from payroll.services import (
    approve_pay,
    ensure_rate_open,
    export_csv,
    line_values,
    live_lines,
    owed,
    pay_settings,
    reopen_pay,
)
from timesheets.models import PayGroup, TimesheetPeriod, period_label
from timesheets.periods import period_bounds
from workforce.models import Worker


class PayViewSet(CompanyScopedViewSet):
    permission_classes = [IsAuthenticated, CanSeePay]
    pagination_class = None

    def filter_worker(self, queryset):
        worker = self.request.query_params.get("worker")
        return queryset.filter(worker_id=worker) if worker else queryset

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, created_by=self.request.user)


class PaySettingsView(APIView):
    permission_classes = [IsAuthenticated, CanSeePay]

    def get(self, request):
        return Response(PaySettingsSerializer(pay_settings(request.company)).data)

    def patch(self, request):
        serializer = PaySettingsSerializer(pay_settings(request.company), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class OwedView(APIView):
    """What each worker is owed now: approved pay minus everything handed over."""

    permission_classes = [IsAuthenticated, CanSeePay]

    def get(self, request):
        workers = list(Worker.objects.filter(company=request.company).order_by("name"))
        balances = owed(workers)
        return Response(
            [{"worker": worker.pk, "name": worker.name, "owed": str(balances[worker.pk])} for worker in workers if balances[worker.pk]]
        )


class PayRateViewSet(PayViewSet):
    serializer_class = PayRateSerializer
    queryset = PayRate.objects.select_related("worker")

    def get_queryset(self):
        return self.filter_worker(super().get_queryset())

    def perform_create(self, serializer):
        ensure_rate_open(serializer.validated_data["worker"], serializer.validated_data["start_date"])
        super().perform_create(serializer)

    def perform_update(self, serializer):
        rate = serializer.instance
        ensure_rate_open(rate.worker, rate.start_date)
        ensure_rate_open(rate.worker, serializer.validated_data.get("start_date", rate.start_date))
        serializer.save()

    def perform_destroy(self, instance):
        ensure_rate_open(instance.worker, instance.start_date)
        instance.delete()


class PayAdjustmentViewSet(PayViewSet):
    serializer_class = PayAdjustmentSerializer
    queryset = PayAdjustment.objects.select_related("worker")

    def get_queryset(self):
        queryset = self.filter_worker(super().get_queryset())
        if self.request.query_params.get("open") == "1":
            queryset = queryset.filter(pay_line__isnull=True)
        return queryset

    def _check_open(self, adjustment):
        if adjustment.pay_line_id is not None:
            raise ValidationError("This is already part of approved pay and can't change.")

    def perform_update(self, serializer):
        self._check_open(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_open(instance)
        instance.delete()


class PaymentViewSet(PayViewSet):
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("worker")

    def get_queryset(self):
        queryset = self.filter_worker(super().get_queryset())
        params = self.request.query_params
        if params.get("from"):
            queryset = queryset.filter(paid_on__gte=params["from"])
        if params.get("to"):
            queryset = queryset.filter(paid_on__lte=params["to"])
        return queryset


def money_or_none(value):
    return str(value) if value is not None else None


class PayRunViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CanSeePay]

    def get_queryset(self):
        return PayRun.objects.filter(company=self.request.company).select_related("period__pay_group", "approved_by")

    def _group(self, request, group_id):
        group = PayGroup.objects.filter(company=request.company, pk=group_id).select_related("company").first()
        if group is None:
            raise NotFound("Pay group not found.")
        return group

    @action(detail=False, methods=["get"])
    def periods(self, request):
        """The group's recent periods, newest first, with the state of their hours and pay."""
        query = PayQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        group = self._group(request, query.validated_data["pay_group"])
        today = request.company.today()
        saved = {period.start_date: period for period in group.periods.select_related("pay_run")}
        totals = {
            period_id: (net, to_pay)
            for period_id, net, to_pay in PayLine.objects.filter(
                pay_run__period__pay_group=group, pay_run__status=PayRun.Status.APPROVED
            )
            .values_list("pay_run__period_id")
            .annotate(Sum("net"), Sum("to_pay"))
        }
        start, end = period_bounds(group, today)
        rows = []
        for _ in range(8):
            period = saved.get(start)
            run = getattr(period, "pay_run", None)
            net, to_pay = totals.get(getattr(period, "pk", None), (None, None))
            rows.append(
                {
                    "start": str(start),
                    "end": str(end),
                    "label": period_label(start, end),
                    "over": end < today,
                    "hours_status": period.status if period else TimesheetPeriod.Status.OPEN,
                    "pay_status": run.status if run else None,
                    "net": money_or_none(net),
                    "to_pay": money_or_none(to_pay),
                }
            )
            start, end = period_bounds(group, start - timedelta(days=1))
        return Response(rows)

    @action(detail=False, methods=["get"])
    def view(self, request):
        """One period's pay: frozen lines once approved, otherwise calculated now from the timesheet."""
        query = PayQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        group = self._group(request, query.validated_data["pay_group"])
        start, end = period_bounds(group, query.validated_data.get("date") or request.company.today())
        saved = TimesheetPeriod.objects.filter(pay_group=group, start_date=start).first()
        run = PayRun.objects.filter(period=saved).select_related("approved_by").first() if saved else None
        if run is not None and run.status == PayRun.Status.APPROVED:
            saved_lines = list(run.lines.select_related("worker"))
            lines = [{**PayLineSerializer(line).data, "missing_rate": False} for line in saved_lines]
            workers = [line.worker for line in saved_lines]
        else:
            calculated = live_lines(group, start, end)
            workers = [worker for worker, _, _ in calculated]
            before = owed(workers)
            lines = [
                {
                    "id": None,
                    "worker": worker.pk,
                    "worker_name": worker.name,
                    **{key: value if key == "breakdown" else str(value) for key, value in line_values(line, before[worker.pk]).items()},
                    "missing_rate": line.missing_rate,
                }
                for worker, line, _ in calculated
            ]
        now = owed(workers)
        for line in lines:
            line["owed_now"] = str(now[line["worker"]])
        return Response(
            {
                "pay_group": {"id": group.pk, "name": group.name, "cycle": group.cycle},
                "currency": pay_settings(request.company).currency,
                "period": {
                    "start": str(start),
                    "end": str(end),
                    "label": period_label(start, end),
                    "over": end < request.company.today(),
                    "hours_status": saved.status if saved else TimesheetPeriod.Status.OPEN,
                },
                "run": None
                if run is None
                else {
                    "id": run.pk,
                    "status": run.status,
                    "approved_by_email": run.approved_by.email if run.approved_by else "",
                    "approved_at": run.approved_at,
                },
                "lines": lines,
            }
        )

    @action(detail=False, methods=["post"])
    def approve(self, request):
        serializer = PayPeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        run = approve_pay(self._group(request, data["pay_group"]), data["start_date"], data["end_date"], request.user)
        return Response({"id": run.pk, "status": run.status})

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        run = reopen_pay(self.get_object())
        return Response({"id": run.pk, "status": run.status})

    @action(detail=True, methods=["get"], renderer_classes=[renderers.JSONRenderer, FileRenderer])
    def export(self, request, pk=None):
        run = self.get_object()
        if run.status != PayRun.Status.APPROVED:
            raise ValidationError("Approve this pay before exporting it.")
        period = run.period
        name = f"pay-{slugify(period.pay_group.name)}-{period.start_date}-{period.end_date}.csv"
        response = HttpResponse(export_csv(run), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class PayLineViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Approved pay lines; retrieving one gives a payslip."""

    permission_classes = [IsAuthenticated, CanSeePay]
    serializer_class = PayLineSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = PayLine.objects.filter(
            pay_run__company=self.request.company, pay_run__status=PayRun.Status.APPROVED
        ).select_related("worker", "pay_run__period__pay_group", "pay_run__company")
        worker = self.request.query_params.get("worker")
        if worker:
            queryset = queryset.filter(worker_id=worker)
        return queryset.order_by("-pay_run__period__start_date")

    def list(self, request, *args, **kwargs):
        lines = self.get_queryset()
        return Response(
            [
                {
                    **self.get_serializer(line).data,
                    "period_label": period_label(line.pay_run.period.start_date, line.pay_run.period.end_date),
                    "pay_group_name": line.pay_run.period.pay_group.name,
                }
                for line in lines
            ]
        )

    def retrieve(self, request, *args, **kwargs):
        line = self.get_object()
        period = line.pay_run.period
        advances = Payment.objects.filter(
            worker=line.worker,
            kind=Payment.Kind.ADVANCE,
            paid_on__range=(period.start_date, period.end_date),
        )
        return Response(
            {
                **self.get_serializer(line).data,
                "company_name": line.pay_run.company.name,
                "currency": pay_settings(request.company).currency,
                "pay_group_name": period.pay_group.name,
                "period": {"start": str(period.start_date), "end": str(period.end_date), "label": period_label(period.start_date, period.end_date)},
                "adjustments": PayAdjustmentSerializer(line.adjustments.all(), many=True).data,
                "advances": PaymentSerializer(advances, many=True).data,
                "owed_now": str(owed([line.worker])[line.worker.pk]),
            }
        )
