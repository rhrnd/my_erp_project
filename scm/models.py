from django.db import models
from django.db.models import Avg
from simple_history.models import HistoricalRecords


# ──────────────────────────────────────────────────────────────────────────────
# 1. 제품 모델 마스터
# ──────────────────────────────────────────────────────────────────────────────

class ProductModel(models.Model):
    """
    T/A 제품 모델 마스터 — 840, 870, 810, 920 등
    LOT 등록 시 이 테이블을 FK로 참조하여 모델 정보를 정규화한다.
    """

    class ProductGroup(models.TextChoices):
        TA_810 = '810', 'T/A 810'
        TA_840 = '840', 'T/A 840'
        TA_870 = '870', 'T/A 870'
        TA_920 = '920', 'T/A 920'

    model_id = models.BigAutoField(primary_key=True, verbose_name="모델 PK")
    model_code = models.CharField(max_length=50, unique=True, verbose_name="모델 코드",
                                  help_text="예: TP214N-AD-840UM, F84PC")
    model_name = models.CharField(max_length=100, verbose_name="모델명")
    product_group = models.CharField(
        max_length=10, choices=ProductGroup.choices, verbose_name="제품 그룹",
        help_text="T/A 종류 구분 (810 / 840 / 870 / 920)"
    )
    material = models.CharField(max_length=50, blank=True, null=True, verbose_name="소재",
                                help_text="예: PEEK, PC")
    spec_description = models.TextField(blank=True, null=True, verbose_name="규격 설명")
    in_use = models.BooleanField(default=True, verbose_name="사용여부")

    history = HistoricalRecords()

    class Meta:
        db_table = 'scm_product_model'
        verbose_name = '제품 모델'
        verbose_name_plural = '제품 모델 마스터'
        ordering = ['product_group', 'model_code']

    def __str__(self):
        return f"[{self.product_group}] {self.model_code}"


# ──────────────────────────────────────────────────────────────────────────────
# 2. LOT
# ──────────────────────────────────────────────────────────────────────────────

class Lot(models.Model):
    """
    LOT 단위 입고 기록 — 모든 검사/부적합/측정의 기준 단위.

    LOT No. 형식: K40822-01 (lot_no)
    LOT 기번 형식: -001, -003 (lot_sub_no) — 성적서 측정 시 구분자
    source_type: 수입검사(INCOMING) 또는 공정(PROCESS) 발생 구분
    """

    class SourceType(models.TextChoices):
        INCOMING = 'INCOMING', '수입검사'
        PROCESS = 'PROCESS',  '공정'

    lot_id = models.BigAutoField(primary_key=True, verbose_name="LOT PK")
    product_model = models.ForeignKey(
        ProductModel,
        on_delete=models.PROTECT,
        db_column='model_id',
        related_name='lots',
        verbose_name="제품 모델"
    )
    lot_no = models.CharField(max_length=30, verbose_name="LOT No.",
                              help_text="예: K40822-01")
    lot_sub_no = models.CharField(max_length=10, blank=True, null=True,
                                  verbose_name="LOT 기번",
                                  help_text="예: -001, -003")
    received_date = models.DateField(verbose_name="입고일")
    received_qty = models.PositiveIntegerField(default=0, verbose_name="입고수량")
    source_type = models.CharField(
        max_length=10, choices=SourceType.choices,
        default=SourceType.INCOMING, verbose_name="발생 구분"
    )
    # PD 공칭값 (mm) — 성적서 측정 기준
    pd_nominal_mm = models.DecimalField(
        max_digits=6, decimal_places=3,
        blank=True, null=True,
        verbose_name="PD 공칭값 (mm)"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일시")

    history = HistoricalRecords()

    class Meta:
        db_table = 'scm_lot'
        verbose_name = 'LOT'
        verbose_name_plural = 'LOT 목록'
        # 동일 LOT No. + 기번의 중복 방지
        unique_together = [('lot_no', 'lot_sub_no')]
        ordering = ['-received_date', 'lot_no']
        indexes = [
            models.Index(fields=['lot_no'],         name='idx_lot_lot_no'),
            models.Index(fields=['received_date'],   name='idx_lot_recv_dt'),
            models.Index(fields=['product_model'],   name='idx_lot_model'),
        ]

    def __str__(self):
        sub = self.lot_sub_no or ''
        return f"{self.lot_no}{sub} ({self.received_date})"


# ──────────────────────────────────────────────────────────────────────────────
# 3. 수입검사 결과
# ──────────────────────────────────────────────────────────────────────────────

class IncomingInspection(models.Model):
    """
    LOT 수입검사 결과 — LOT 1건당 1건의 검사 결과를 저장한다.
    수입검사 불합격 시 NonConformance 레코드가 함께 생성된다.
    """

    class InspectionResult(models.TextChoices):
        PASS = 'PASS',    '합격'
        FAIL = 'FAIL',    '불합격'
        PENDING = 'PENDING', '보류'

    inspection_id = models.BigAutoField(primary_key=True, verbose_name="검사 PK")
    lot = models.OneToOneField(
        Lot,
        on_delete=models.CASCADE,
        db_column='lot_id',
        related_name='incoming_inspection',
        verbose_name="LOT"
    )
    inspection_date = models.DateField(verbose_name="검사일")
    result = models.CharField(
        max_length=10, choices=InspectionResult.choices,
        default=InspectionResult.PENDING,
        verbose_name="검사 결과"
    )
    report_no = models.CharField(max_length=50, blank=True, null=True, verbose_name="보고서 번호")
    defect_type = models.CharField(max_length=200, blank=True, null=True, verbose_name="부적합 내용",
                                   help_text="예: 수입검사 커팅 불량, Back PAD 코팅액 묻음")
    action_taken = models.TextField(blank=True, null=True, verbose_name="조치 내용",
                                    help_text="예: 재작업 후 입고 (2025-02-07) / EG개선품")
    remarks = models.TextField(blank=True, null=True, verbose_name="비고")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일시")

    history = HistoricalRecords()

    class Meta:
        db_table = 'scm_incoming_inspection'
        verbose_name = '수입검사'
        verbose_name_plural = '수입검사 목록'
        ordering = ['-inspection_date']

    def __str__(self):
        return f"{self.lot} — {self.get_result_display()}"


# ──────────────────────────────────────────────────────────────────────────────
# 4. 부적합품 (NonConformance)
# ──────────────────────────────────────────────────────────────────────────────

class NonConformance(models.Model):
    """
    부적합품 이력 — 수입검사 불합격 또는 공정 중 발견된 부적합품을 기록한다.

    nc_type: 수입검사(INCOMING) / 공정(PROCESS) / IC 공정(IC_PROCESS)
    status : 현재 처리 상태 (ENUM). 상태 변경 이력은 NCStatusHistory에 쌓인다.
    """

    class NCType(models.TextChoices):
        INCOMING = 'INCOMING',   '수입검사 부적합'
        PROCESS = 'PROCESS',    '공정 부적합'
        IC_PROCESS = 'IC_PROCESS', 'IC 공정 부적합'

    class NCStatus(models.TextChoices):
        DETECTED = 'DETECTED',         '발생'
        WAITING_RETURN = 'WAITING_RETURN',   '반송 대기'
        RETURN_COMPLETED = 'RETURN_COMPLETED', '반송 완료'
        REWORK_IN_PROGRESS = 'REWORK_IN_PROGRESS', '재작업 중'
        REWORK_COMPLETED = 'REWORK_COMPLETED',   '재작업 완료'
        IN_HOUSE_STORAGE = 'IN_HOUSE_STORAGE', '사내 보관'
        USED_UP = 'USED_UP',          '사용 완료'
        DISCARDED = 'DISCARDED',        '폐기'
        TEST_IN_PROGRESS = 'TEST_IN_PROGRESS', '테스트 중'

    nc_id = models.BigAutoField(primary_key=True, verbose_name="부적합 PK")
    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        db_column='lot_id',
        related_name='nonconformances',
        verbose_name="LOT"
    )
    nc_type = models.CharField(
        max_length=15, choices=NCType.choices,
        verbose_name="부적합 유형"
    )
    # 발견 단계 (상세 텍스트) — 예: "수입검사", "공정", "현장발견"
    detection_stage = models.CharField(max_length=50, blank=True, null=True,
                                       verbose_name="발견 단계")
    defect_description = models.TextField(verbose_name="부적합 내용",
                                          help_text="예: 이형지 손상, Back PAD 코팅액 묻음")
    corrective_action = models.TextField(blank=True, null=True, verbose_name="시정 조치")
    status = models.CharField(
        max_length=20, choices=NCStatus.choices,
        default=NCStatus.DETECTED,
        verbose_name="처리 상태",
        db_index=True
    )
    return_date = models.DateField(blank=True, null=True, verbose_name="반송 완료일")
    rework_complete_date = models.DateField(blank=True, null=True, verbose_name="재작업 완료일")
    remarks = models.TextField(blank=True, null=True, verbose_name="비고")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일시")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="수정일시")

    history = HistoricalRecords()

    class Meta:
        db_table = 'scm_nonconformance'
        verbose_name = '부적합품'
        verbose_name_plural = '부적합품 목록'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'],   name='idx_nc_status'),
            models.Index(fields=['nc_type'],  name='idx_nc_type'),
        ]

    def __str__(self):
        return f"{self.lot} — {self.get_nc_type_display()} / {self.get_status_display()}"


# ──────────────────────────────────────────────────────────────────────────────
# 5. 부적합품 상태 변경 이력
# ──────────────────────────────────────────────────────────────────────────────

class NCStatusHistory(models.Model):
    """
    부적합품 상태 변경 이력 — NonConformance.status 변경 시마다 한 줄씩 기록.
    엑셀의 비고란에 날짜가 뒤섞여 있던 문제를 구조화하여 해결한다.
    """

    nc = models.ForeignKey(
        NonConformance,
        on_delete=models.CASCADE,
        db_column='nc_id',
        related_name='status_histories',
        verbose_name="부적합품"
    )
    previous_status = models.CharField(
        max_length=20,
        choices=NonConformance.NCStatus.choices,
        blank=True, null=True,
        verbose_name="이전 상태"
    )
    new_status = models.CharField(
        max_length=20,
        choices=NonConformance.NCStatus.choices,
        verbose_name="변경 후 상태"
    )
    change_reason = models.TextField(blank=True, null=True, verbose_name="변경 사유",
                                     help_text="예: Fujibo 社 반송 완료 (2024-12-26)")
    changed_by = models.CharField(max_length=50, blank=True, null=True,
                                  verbose_name="변경자")
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="변경일시")

    class Meta:
        db_table = 'scm_nc_status_history'
        verbose_name = '부적합 상태 이력'
        verbose_name_plural = '부적합 상태 이력'
        ordering = ['-changed_at']

    def __str__(self):
        return (f"{self.nc} | "
                f"{self.previous_status or '-'} → {self.new_status} "
                f"({self.changed_at:%Y-%m-%d})")


# ──────────────────────────────────────────────────────────────────────────────
# 6. LOT 불량 집계 (이력관리 파일 대응)
# ──────────────────────────────────────────────────────────────────────────────

class LotDefectSummary(models.Model):
    """
    LOT 단위 불량 집계 — '이력관리' 파일의 입고수량 대비 불량/재작업/대기 수량.

    엑셀에서 한 행에 들어가 있던 LOT 집계를 정형화한다.
    defect_lot_sub_nos: 불량이 발생한 기번 목록 (예: "065, 076, 191")
    """

    summary_id = models.BigAutoField(primary_key=True, verbose_name="집계 PK")
    lot = models.OneToOneField(
        Lot,
        on_delete=models.CASCADE,
        db_column='lot_id',
        related_name='defect_summary',
        verbose_name="LOT"
    )
    incoming_defect_qty = models.PositiveIntegerField(default=0, verbose_name="수입불량 수량")
    process_defect_qty = models.PositiveIntegerField(default=0, verbose_name="공정불량 수량")
    rework_qty = models.PositiveIntegerField(default=0, verbose_name="재작업 수량")
    pending_qty = models.PositiveIntegerField(default=0, verbose_name="대기 수량")
    return_complete_qty = models.PositiveIntegerField(default=0, verbose_name="반송 완료 수량")
    # 불량 기번 목록 — 조회/필터용 텍스트
    defect_lot_sub_nos = models.TextField(
        blank=True, null=True,
        verbose_name="불량 기번 목록",
        help_text="예: 065, 076, 191, 407"
    )
    remarks = models.TextField(blank=True, null=True, verbose_name="비고")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="최종 수정일시")

    class Meta:
        db_table = 'scm_lot_defect_summary'
        verbose_name = 'LOT 불량 집계'
        verbose_name_plural = 'LOT 불량 집계'

    def __str__(self):
        return f"{self.lot} — 불량 {self.process_defect_qty} / 재작업 {self.rework_qty}"


# ──────────────────────────────────────────────────────────────────────────────
# 7. 출하 측정 헤더 (PD / CS DATA 파일 대응)
# ──────────────────────────────────────────────────────────────────────────────

class LotMeasurement(models.Model):
    """
    LOT 출하 측정 헤더 — PD_DATA / CS_DATA 파일의 Lot 단위 측정 세션.

    measurement_type: PD(두께) 또는 CS(간격) 구분
    shipping_date   : 출하일 (파일의 Shipping Date)
    """

    class MeasurementType(models.TextChoices):
        PD = 'PD', 'PD 측정 (두께)'
        CS = 'CS', 'CS 측정 (간격)'

    measurement_id = models.BigAutoField(primary_key=True, verbose_name="측정 PK")
    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        db_column='lot_id',
        related_name='measurements',
        verbose_name="LOT"
    )
    measurement_type = models.CharField(
        max_length=5, choices=MeasurementType.choices,
        verbose_name="측정 유형"
    )
    shipping_date = models.DateField(verbose_name="출하일")
    quantity = models.PositiveIntegerField(default=0, verbose_name="출하 수량 (pcs)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일시")

    class Meta:
        db_table = 'scm_lot_measurement'
        verbose_name = 'LOT 측정 헤더'
        verbose_name_plural = 'LOT 측정 헤더 목록'
        unique_together = [('lot', 'measurement_type', 'shipping_date')]
        ordering = ['-shipping_date', 'lot']

    def __str__(self):
        return f"{self.lot} — {self.get_measurement_type_display()} ({self.shipping_date})"


# ──────────────────────────────────────────────────────────────────────────────
# 8. 측정 항목 (측정 1~4 + 평균)
# ──────────────────────────────────────────────────────────────────────────────

class MeasurementItem(models.Model):
    """
    측정 항목 — LotMeasurement 1건당 N개의 측정 행 (LOT 기번별).

    엑셀에서 측정1~4 컬럼 + 평균 컬럼이 한 행에 들어가 있던 구조를 정형화.
    average 는 DB 저장 시 자동 계산(save override)하거나 엑셀 값을 그대로 저장 가능.
    """

    item_id = models.BigAutoField(primary_key=True, verbose_name="측정 항목 PK")
    measurement = models.ForeignKey(
        LotMeasurement,
        on_delete=models.CASCADE,
        db_column='measurement_id',
        related_name='items',
        verbose_name="측정 헤더"
    )
    sequence_no = models.PositiveSmallIntegerField(verbose_name="순번",
                                                   help_text="엑셀 No 열 값")
    lot_sub_no = models.CharField(max_length=10, blank=True, null=True,
                                  verbose_name="LOT 기번",
                                  help_text="예: -001, -003")
    meas_1 = models.DecimalField(max_digits=8, decimal_places=4,
                                 blank=True, null=True, verbose_name="측정1")
    meas_2 = models.DecimalField(max_digits=8, decimal_places=4,
                                 blank=True, null=True, verbose_name="측정2")
    meas_3 = models.DecimalField(max_digits=8, decimal_places=4,
                                 blank=True, null=True, verbose_name="측정3")
    meas_4 = models.DecimalField(max_digits=8, decimal_places=4,
                                 blank=True, null=True, verbose_name="측정4")
    average = models.DecimalField(max_digits=8, decimal_places=4,
                                  blank=True, null=True, verbose_name="평균")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일시")

    class Meta:
        db_table = 'scm_measurement_item'
        verbose_name = '측정 항목'
        verbose_name_plural = '측정 항목 목록'
        unique_together = [('measurement', 'sequence_no')]
        ordering = ['measurement', 'sequence_no']

    def save(self, *args, **kwargs):
        # 평균값이 없으면 측정값 중 입력된 것들만 평균 계산
        if self.average is None:
            values = [v for v in [self.meas_1, self.meas_2, self.meas_3, self.meas_4]
                      if v is not None]
            if values:
                self.average = round(sum(float(v) for v in values) / len(values), 4)
        super().save(*args, **kwargs)

    def __str__(self):
        return (f"{self.measurement} / No.{self.sequence_no}"
                f"{(' ' + self.lot_sub_no) if self.lot_sub_no else ''}"
                f" — avg:{self.average}")
