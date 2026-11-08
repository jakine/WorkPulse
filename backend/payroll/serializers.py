from rest_framework import serializers

from companies.serializers import CompanyWorkerMixin
from payroll.models import PayAdjustment, PayLine, PayRate, PaySettings, Payment


class PaySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaySettings
        fields = ["currency", "extra_hours_multiplier", "pay_holidays_for_day_rate"]

    def validate_currency(self, currency):
        currency = currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise serializers.ValidationError("Use a three-letter currency code, such as EUR.")
        return currency


class PayRateSerializer(CompanyWorkerMixin, serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)

    class Meta:
        model = PayRate
        fields = ["id", "worker", "worker_name", "start_date", "pay_type", "amount", "note"]

    def validate(self, attrs):
        worker = attrs.get("worker", getattr(self.instance, "worker", None))
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        clash = PayRate.objects.filter(worker=worker, start_date=start_date)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"start_date": "This worker already has a rate starting that day."})
        return attrs


class PayAdjustmentSerializer(CompanyWorkerMixin, serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)
    settled = serializers.SerializerMethodField()

    class Meta:
        model = PayAdjustment
        fields = ["id", "worker", "worker_name", "date", "kind", "amount", "note", "settled"]

    def get_settled(self, adjustment):
        return adjustment.pay_line_id is not None


class PaymentSerializer(CompanyWorkerMixin, serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "worker", "worker_name", "paid_on", "amount", "kind", "method", "note"]


class PayLineSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)

    class Meta:
        model = PayLine
        fields = [
            "id",
            "worker",
            "worker_name",
            "pay_type",
            "rate",
            "days",
            "hours",
            "extra_hours",
            "paid_off_days",
            "unpaid_off_days",
            "holidays",
            "base",
            "extra_pay",
            "off_pay",
            "holiday_pay",
            "bonuses",
            "deductions",
            "gross",
            "net",
            "balance_before",
            "to_pay",
            "breakdown",
        ]
        read_only_fields = fields


class PayPeriodSerializer(serializers.Serializer):
    pay_group = serializers.IntegerField(min_value=1)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class PayQuerySerializer(serializers.Serializer):
    pay_group = serializers.IntegerField(min_value=1)
    date = serializers.DateField(required=False)
