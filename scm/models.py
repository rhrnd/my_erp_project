from django.db import models
from django.db.models import Sum


class IncomingInspection(models.Model):
    """입고 이벤트 — 입고수량은 LOT 합산으로 자동 계산"""

    incoming_date = models.DateField(verbose_name="입고일", unique=True)

    class Meta:
        verbose_name = "입고검사"
        verbose_name_plural = "입고검사 목록"
        ordering = ["-incoming_date"]

    def __str__(self):
        return f"{self.incoming_date} / {self.total_quantity}개"

    @property
    def total_quantity(self):
        result = self.lots.aggregate(total=Sum("quantity"))
        return result["total"] or 0


class TAManagement(models.Model):
    """LOT 단위 검사 기록"""

    inspection = models.ForeignKey(
        IncomingInspection,
        on_delete=models.CASCADE,
        related_name="lots",
        verbose_name="입고검사"
    )
    lot_number = models.CharField(max_length=20, verbose_name="LOT NO.", db_index=True)
    quantity = models.PositiveIntegerField(default=0, verbose_name="수량")

    incoming_defect = models.PositiveIntegerField(default=0, verbose_name="수입불량")
    defect = models.PositiveIntegerField(default=0, verbose_name="불량")
    rework = models.PositiveIntegerField(default=0, verbose_name="재작업")
    pending = models.PositiveIntegerField(default=0, verbose_name="대기")

    incoming_inspection_defect = models.TextField(blank=True, default="", verbose_name="수입검사불량")
    process_defect = models.TextField(blank=True, default="", verbose_name="공정불량")
    pending_detail = models.TextField(blank=True, default="", verbose_name="대기 상세")
    note = models.TextField(blank=True, default="", verbose_name="비고")

    class Meta:
        db_table = 'scm_ta_management'
        verbose_name = "TA 관리"
        verbose_name_plural = "TA 관리 목록"
        ordering = ["lot_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["inspection", "lot_number"],
                name="unique_lot_per_inspection"
            )
        ]

    def __str__(self):
        return f"{self.lot_number} ({self.inspection.incoming_date})"
