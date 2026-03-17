from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Material, Inbound, Outbound

# Register your models here.


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
