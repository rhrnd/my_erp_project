from django.contrib import admin
from .models import IncomingInspection, TAManagement


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
