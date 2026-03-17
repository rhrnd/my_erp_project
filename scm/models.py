from django.db import models
from simple_history.models import HistoricalRecords


class Material(models.Model):
    mat_id = models.BigAutoField(primary_key=True, verbose_name="자재 식별 PK")
    mat_code = models.CharField(max_length=50, unique=True, blank=True, verbose_name="제품 코드", help_text="사용자 지정 제품 코드")
    mat_nm = models.CharField(max_length=100, verbose_name="자재명", help_text="제품명")
    mat_maker = models.CharField(max_length=50, null=True, blank=True, verbose_name="제조사")
    mat_spec = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="규격"
    )
    mat_unit = models.CharField(max_length=10, verbose_name="단위")
    mat_current_stock = models.FloatField(default=0, verbose_name="현재재고")
    in_use = models.BooleanField(default=True, verbose_name="사용여부", help_text="자재 단종 시 FALSE")

    history = HistoricalRecords()

    class Meta:
        db_table = 'material'
        verbose_name = '자재 마스터'
        verbose_name_plural = '자재 마스터'
        # 제품명 + 제조사 + 규격 조합이 중복되지 않도록 설정 (UK 대응)
        unique_together = ('mat_nm', 'mat_maker', 'mat_spec')

    def __str__(self):
        return f"{self.mat_nm} ({self.mat_spec if self.mat_spec else '규격없음'})"


class Inbound(models.Model):
    in_id = models.BigAutoField(primary_key=True, verbose_name="입고 기록 PK")
    mat = models.ForeignKey(
        'Material',
        on_delete=models.PROTECT,
        db_column='mat_id',
        related_name='inbounds',
        verbose_name="입고된 자재 연결"
    )
    emp = models.ForeignKey(
        'hr.Employee',
        on_delete=models.PROTECT,
        db_column='emp_id',
        related_name='inbounds',
        verbose_name="사원 코드 연결"
    )
    in_purchase_dt = models.DateField(verbose_name="영수증 상 실제 구매일")
    in_purchase_price = models.FloatField(verbose_name="구매 당시 개당 단가")
    in_qty = models.FloatField(verbose_name="입고된 수량")
    in_dtm = models.DateTimeField(auto_now_add=True, verbose_name="시스템 등록 시각")

    class Meta:
        db_table = 'inbound'
        verbose_name = '입고 정보'
        verbose_name_plural = '입고 정보'

    def __str__(self):
        return f"{self.in_purchase_dt} 입고: {self.mat.mat_nm if hasattr(self.mat, 'mat_nm') else self.mat_id}"


class Outbound(models.Model):
    out_id = models.BigAutoField(primary_key=True, verbose_name="출고기록 PK")
    mat = models.ForeignKey(
        'Material',
        on_delete=models.PROTECT,
        db_column='mat_id',
        related_name='outbounds',
        verbose_name="자재 코드 연결"
    )
    emp = models.ForeignKey(
        'hr.Employee',
        on_delete=models.PROTECT,
        db_column='emp_id',
        related_name='outbounds',
        verbose_name="사원코드",
        help_text="출고를 기록한 사원의 정보. 실사용자는 비고에 기록"
    )
    out_date = models.DateField(verbose_name="출고 일자")
    out_qty = models.FloatField(verbose_name="사용/불출 수량")

    out_dtm = models.DateTimeField(auto_now_add=True, verbose_name="시스템 등록 시각")

    out_remark = models.TextField(null=True, blank=True, verbose_name="비고")

    class Meta:
        db_table = 'outbound'
        verbose_name = '출고 정보'
        verbose_name_plural = '출고 정보'

    def __str__(self):
        return f"{self.out_date} - {self.mat.mat_nm if hasattr(self.mat, 'mat_nm') else self.mat_id} ({self.out_qty})"
