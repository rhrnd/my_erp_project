from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Material, Inbound, Outbound
from .models import IncomingInspection, TAManagement


@admin.register(Material)
class MaterialAdmin(SimpleHistoryAdmin):
    list_display = ('mat_id', 'mat_nm', 'mat_unit', 'mat_current_stock', 'in_use')
    search_fields = ('mat_nm', 'mat_spec')
    list_filter = ('in_use',)


@admin.register(Inbound)
class InboundAdmin(admin.ModelAdmin):
    list_display = ('in_id', 'mat', 'emp', 'in_qty', 'in_purchase_dt', 'in_dtm')
    list_filter = ('in_purchase_dt',)


@admin.register(Outbound)
class OutboundAdmin(admin.ModelAdmin):
    list_display = ('out_id', 'mat', 'emp', 'out_qty', 'out_date', 'out_dtm')
    list_filter = ('out_date',)


class TAManagementInline(admin.TabularInline):
    model = TAManagement
    extra = 1
    fields = [
        "lot_number", "quantity",
        "incoming_defect", "defect", "rework", "pending",
        "process_defect", "note"
    ]


@admin.register(IncomingInspection)
class IncomingInspectionAdmin(admin.ModelAdmin):
    list_display = ["incoming_date", "total_quantity", "lot_count"]
    inlines = [TAManagementInline]

    def lot_count(self, obj):
        return obj.lots.count()
    lot_count.short_description = "LOT 수"


@admin.register(TAManagement)
class TAManagementAdmin(admin.ModelAdmin):
    list_display = ["lot_number", "inspection", "quantity", "defect", "rework"]
    search_fields = ["lot_number"]
    list_filter = ["inspection__incoming_date"]
