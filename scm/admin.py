from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    ProductModel,
    Lot,
    IncomingInspection,
    NonConformance,
    NCStatusHistory,
    LotDefectSummary,
    LotMeasurement,
    MeasurementItem,
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. 제품 모델 마스터
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(ProductModel)
class ProductModelAdmin(SimpleHistoryAdmin):
    list_display = ('model_code', 'model_name', 'product_group', 'material', 'in_use')
    list_filter = ('product_group', 'in_use')
    search_fields = ('model_code', 'model_name')
    ordering = ('product_group', 'model_code')


# ──────────────────────────────────────────────────────────────────────────────
# 2. LOT
# ──────────────────────────────────────────────────────────────────────────────

class LotDefectSummaryInline(admin.StackedInline):
    model = LotDefectSummary
    extra = 0
    fields = (
        'incoming_defect_qty', 'process_defect_qty',
        'rework_qty', 'pending_qty', 'return_complete_qty',
        'defect_lot_sub_nos', 'remarks',
    )


class IncomingInspectionInline(admin.StackedInline):
    model = IncomingInspection
    extra = 0
    fields = ('inspection_date', 'result', 'report_no', 'defect_type', 'action_taken', 'remarks')


class NonConformanceInline(admin.TabularInline):
    model = NonConformance
    extra = 0
    fields = ('nc_type', 'detection_stage', 'defect_description', 'status', 'remarks')
    show_change_link = True


@admin.register(Lot)
class LotAdmin(SimpleHistoryAdmin):
    list_display = ('lot_no', 'lot_sub_no', 'product_model', 'received_date',
                    'received_qty', 'source_type')
    list_filter = ('source_type', 'product_model__product_group', 'received_date')
    search_fields = ('lot_no', 'lot_sub_no', 'product_model__model_code')
    ordering = ('-received_date', 'lot_no')
    inlines = [IncomingInspectionInline, NonConformanceInline, LotDefectSummaryInline]


# ──────────────────────────────────────────────────────────────────────────────
# 3. 수입검사
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(IncomingInspection)
class IncomingInspectionAdmin(SimpleHistoryAdmin):
    list_display = ('lot', 'inspection_date', 'result', 'report_no', 'defect_type')
    list_filter = ('result', 'inspection_date')
    search_fields = ('lot__lot_no', 'report_no', 'defect_type')
    ordering = ('-inspection_date',)


# ──────────────────────────────────────────────────────────────────────────────
# 4. 부적합품
# ──────────────────────────────────────────────────────────────────────────────

class NCStatusHistoryInline(admin.TabularInline):
    model = NCStatusHistory
    extra = 0
    fields = ('previous_status', 'new_status', 'change_reason', 'changed_by', 'changed_at')
    readonly_fields = ('changed_at',)
    ordering = ('-changed_at',)


@admin.register(NonConformance)
class NonConformanceAdmin(SimpleHistoryAdmin):
    list_display = ('lot', 'nc_type', 'detection_stage', 'status',
                    'return_date', 'rework_complete_date', 'created_at')
    list_filter = ('nc_type', 'status', 'created_at')
    search_fields = ('lot__lot_no', 'defect_description', 'remarks')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [NCStatusHistoryInline]

    fieldsets = (
        ('기본 정보', {
            'fields': ('lot', 'nc_type', 'detection_stage')
        }),
        ('부적합 내용 및 조치', {
            'fields': ('defect_description', 'corrective_action', 'status')
        }),
        ('처리 일자', {
            'fields': ('return_date', 'rework_complete_date')
        }),
        ('기타', {
            'fields': ('remarks', 'created_at', 'updated_at')
        }),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 5. 부적합 상태 이력 (단독 조회용)
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(NCStatusHistory)
class NCStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('nc', 'previous_status', 'new_status', 'changed_by', 'changed_at')
    list_filter = ('new_status', 'changed_at')
    search_fields = ('nc__lot__lot_no', 'change_reason', 'changed_by')
    ordering = ('-changed_at',)
    readonly_fields = ('changed_at',)


# ──────────────────────────────────────────────────────────────────────────────
# 6. LOT 불량 집계
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(LotDefectSummary)
class LotDefectSummaryAdmin(admin.ModelAdmin):
    list_display = ('lot', 'incoming_defect_qty', 'process_defect_qty',
                    'rework_qty', 'pending_qty', 'return_complete_qty', 'updated_at')
    search_fields = ('lot__lot_no', 'defect_lot_sub_nos')
    ordering = ('-updated_at',)
    readonly_fields = ('updated_at',)


# ──────────────────────────────────────────────────────────────────────────────
# 7. LOT 측정 (헤더 + 항목 인라인)
# ──────────────────────────────────────────────────────────────────────────────

class MeasurementItemInline(admin.TabularInline):
    model = MeasurementItem
    extra = 0
    fields = ('sequence_no', 'lot_sub_no', 'meas_1', 'meas_2', 'meas_3', 'meas_4', 'average')
    ordering = ('sequence_no',)


@admin.register(LotMeasurement)
class LotMeasurementAdmin(admin.ModelAdmin):
    list_display = ('lot', 'measurement_type', 'shipping_date', 'quantity')
    list_filter = ('measurement_type', 'shipping_date')
    search_fields = ('lot__lot_no',)
    ordering = ('-shipping_date',)
    inlines = [MeasurementItemInline]


@admin.register(MeasurementItem)
class MeasurementItemAdmin(admin.ModelAdmin):
    list_display = ('measurement', 'sequence_no', 'lot_sub_no',
                    'meas_1', 'meas_2', 'meas_3', 'meas_4', 'average')
    search_fields = ('measurement__lot__lot_no', 'lot_sub_no')
    ordering = ('measurement', 'sequence_no')
