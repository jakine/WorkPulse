from django.contrib import admin

from payroll.models import PayAdjustment, PayLine, PayRate, PayRun, PaySettings, Payment

admin.site.register(PaySettings)


@admin.register(PayRate)
class PayRateAdmin(admin.ModelAdmin):
    list_display = ["worker", "start_date", "pay_type", "amount"]
    list_filter = ["company", "pay_type"]


class PayLineInline(admin.TabularInline):
    model = PayLine
    extra = 0
    fields = ["worker", "pay_type", "rate", "days", "net", "to_pay"]
    readonly_fields = fields


@admin.register(PayRun)
class PayRunAdmin(admin.ModelAdmin):
    list_display = ["period", "status", "approved_by", "approved_at"]
    list_filter = ["company", "status"]
    inlines = [PayLineInline]


@admin.register(PayAdjustment)
class PayAdjustmentAdmin(admin.ModelAdmin):
    list_display = ["worker", "date", "kind", "amount", "pay_line"]
    list_filter = ["company", "kind"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["worker", "paid_on", "amount", "kind", "method"]
    list_filter = ["company", "kind"]
