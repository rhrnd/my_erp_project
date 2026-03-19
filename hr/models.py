from django.contrib.auth.models import AbstractUser
from django.db import models
from permission.models import UserRole
from simple_history.models import HistoricalRecords


class Department(models.Model):
    dept_id = models.BigAutoField(primary_key=True, verbose_name="부서코드")
    dept_comp = models.CharField(max_length=100, verbose_name="소속회사명")
    dept_nm = models.CharField(max_length=50, verbose_name="부서명")
    parent_dept = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='parent_dept_id',
        related_name='sub_departments',
        verbose_name="상위부서코드",
        help_text="부서 안에 소속된 부서의 경우 이 컬럼을 사용합니다."
    )  # 상위부서코드 (FK): 자기 자신을 참조
    in_use = models.BooleanField(default=True, verbose_name="사용여부")

    history = HistoricalRecords()

    class Meta:
        db_table = 'department'
        verbose_name = '부서 마스터'
        verbose_name_plural = '부서 마스터'

    def __str__(self):
        return f"[{self.dept_comp}] {self.dept_nm}"


class Employee(models.Model):

    class EmpStat(models.TextChoices):
        ACTIVE = '재직', '재직'
        LEAVE = '휴직', '휴직'
        RESIGNED = '퇴직', '퇴직'
        SUSPENDED = '정직', '정직'

    class EmpType(models.TextChoices):
        REGULAR = '정규직', '정규직'
        CONTRACT = '계약직', '계약직'
        PART_TIME = '파트타임', '파트타임'

    emp_id = models.BigAutoField(primary_key=True, verbose_name="사원코드")
    dept = models.ForeignKey(
        'Department',
        on_delete=models.PROTECT,
        db_column='dept_id',
        related_name='employees',
        verbose_name="부서코드",
        help_text="소속 부서 연결"
    )  # 부서코드 (FK): 부서 테이블 참조
    # 사원번호: 고유 사원 번호 [입사년도]+[순번], 로그인 ID로 사용 가능
    emp_no = models.CharField(max_length=20, unique=True, verbose_name="사원번호")
    emp_nm = models.CharField(max_length=50, verbose_name="성명")
    emp_pos = models.CharField(max_length=30, null=True, blank=True, verbose_name="직급")
    emp_type = models.CharField(max_length=30, choices=EmpType.choices, default=EmpType.REGULAR, verbose_name="고용형태코드")
    emp_stat = models.CharField(max_length=30, choices=EmpStat.choices, default=EmpStat.ACTIVE, verbose_name="재직상태코드")
    emp_tel = models.CharField(max_length=20, null=True, blank=True, verbose_name="연락처")
    emp_add = models.CharField(max_length=255, null=True, blank=True, verbose_name="주소")
    emp_rn = models.TextField(unique=True, verbose_name="주민등록번호")  # 주민등록번호: 암호화 시 데이터 부피를 고려해 TEXT 사용
    emp_hire = models.DateField(verbose_name="입사일")
    emp_retire_dt = models.DateField(null=True, blank=True, verbose_name="퇴사일")

    # 주민등록번호(emp_rn)는 민감정보이므로 이력에서 제외
    history = HistoricalRecords(excluded_fields=['emp_rn'])

    class Meta:
        db_table = 'employee'
        verbose_name = '사원 마스터'
        verbose_name_plural = '사원 마스터'

    def __str__(self):
        return f"{self.emp_nm} ({self.emp_no})"


class EmployeeFinance(models.Model):
    """사원 금융 정보"""
    # 사원코드 (PK, FK): 사원 마스터와 1:1 연결
    emp = models.OneToOneField(
        'Employee',
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='emp_id',
        related_name='finance',
        verbose_name="사원코드",
        help_text="사원 1:1 연결"
    )
    bank_nm = models.CharField(max_length=50, null=True, blank=True, verbose_name="은행명")
    bank_acc_no = models.CharField(max_length=50, null=True, blank=True, verbose_name="계좌번호")
    bank_holder = models.CharField(max_length=50, null=True, blank=True, verbose_name="예금주")
    has_car = models.BooleanField(default=False, verbose_name="본인차량여부")

    # 계좌번호는 민감정보이므로 이력에서 제외
    history = HistoricalRecords(excluded_fields=['bank_acc_no'])

    class Meta:
        db_table = 'employee_finance'  # 실제 DB 테이블명
        verbose_name = '사원 금융 정보'
        verbose_name_plural = '사원 금융 정보'

    def __str__(self):
        return f"{self.emp.emp_nm}의 금융 정보"


class Salary(models.Model):
    salary_rec_id = models.BigAutoField(primary_key=True, verbose_name="급여 기록 ID")
    # 사원 고유번호 (FK): employee.emp_id 참조
    emp = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        db_column='emp_id',
        related_name='salaries',
        verbose_name="사원 고유번호"
    )

    salary_month = models.CharField(max_length=7, verbose_name="급여 귀속월")    # 급여 귀속월: 예 '2025-12'
    payment_dt = models.DateField(null=True, blank=True, verbose_name="급여 지급일")    # 실제 급여 지급일

    # --- 수당 항목 (통상임금 및 기타 수당) ---
    base_amt = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="기본급")
    pos_allowance = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                        blank=True, default=0, verbose_name="직책수당")
    exp_allowance = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                        blank=True, default=0, verbose_name="경력수당")
    weekly_holiday_pay = models.DecimalField(max_digits=15, decimal_places=0,
                                             null=True, blank=True, default=0, verbose_name="주휴수당")
    ot_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True,
                                   blank=True, default=0, verbose_name="잔업시간(h)")
    ot_pay = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                 blank=True, default=0, verbose_name="시간외수당")
    non_smoke_allowance = models.DecimalField(max_digits=15, decimal_places=0,
                                              null=True, blank=True, default=0, verbose_name="비흡연수당")
    func_allowance = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                         blank=True, default=0, verbose_name="업무기능수당")
    comm_allowance = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                         blank=True, default=0, verbose_name="통신보조비")
    special_allowance = models.DecimalField(max_digits=15, decimal_places=0,
                                            null=True, blank=True, default=0, verbose_name="특별수당")
    hourly_adj_amt = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                         blank=True, default=0, verbose_name="시급정산")
    meal_pay = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                   blank=True, default=0, verbose_name="식대비")
    car_allowance = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                        blank=True, default=0, verbose_name="자가운전보조금")

    # --- 공제 항목 ---
    income_tax = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                     blank=True, default=0, verbose_name="갑근세")
    local_income_tax = models.DecimalField(max_digits=15, decimal_places=0,
                                           null=True, blank=True, default=0, verbose_name="주민세")
    health_ins = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                     blank=True, default=0, verbose_name="건강보험")
    national_pension = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                           blank=True, default=0, verbose_name="국민연금")
    emp_ins = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                  blank=True, default=0, verbose_name="고용보험")
    longterm_care_ins = models.DecimalField(max_digits=15, decimal_places=0,
                                            null=True, blank=True, default=0, verbose_name="노인장기요양보험")
    other_deduction = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                          blank=True, default=0, verbose_name="기타공제")

    # --- 회사 부담금 ---
    health_ins_comp = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                          blank=True, default=0, verbose_name="건강보험(회사)")
    pension_comp = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                       blank=True, default=0, verbose_name="국민연금(회사)")
    emp_ins_comp = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                       blank=True, default=0, verbose_name="고용보험(회사)")
    ind_acc_comp = models.DecimalField(max_digits=15, decimal_places=0, null=True,
                                       blank=True, default=0, verbose_name="산재보험(회사)")

    # --- 합계 및 결과 ---
    total_gross_amt = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="급여 총계")
    total_deduction_amt = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="공제 총계")
    total_labor_cost = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="법인 인건비 총계")
    net_pay_amt = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="실수령액")
    tax_free_exclusion = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="비과세 제외액")

    # 비고
    remark = models.TextField(null=True, blank=True, verbose_name="비고")

    history = HistoricalRecords()

    class Meta:
        db_table = 'salary'
        unique_together = ('emp', 'salary_month')  # 동일 사원이 같은 달에 급여가 중복되는것을 방지
        verbose_name = '급여 정보'
        verbose_name_plural = '급여 정보'

    def __str__(self):
        return f"{self.salary_month} {self.emp.emp_nm} 급여"

    def save(self, *args, **kwargs):
        # 1. 급여 총계 계산 (모든 수당 합산)
        self.total_gross_amt = (
            (self.base_amt or 0) + (self.pos_allowance or 0) + (self.exp_allowance or 0) +
            (self.weekly_holiday_pay or 0) + (self.ot_pay or 0) + (self.non_smoke_allowance or 0) +
            (self.func_allowance or 0) + (self.comm_allowance or 0) + (self.special_allowance or 0) +
            (self.hourly_adj_amt or 0) + (self.meal_pay or 0) + (self.car_allowance or 0)
        )

        # 2. 공제 총계 계산 (모든 공제 항목 합산)
        self.total_deduction_amt = (
            (self.income_tax or 0) + (self.local_income_tax or 0) + (self.health_ins or 0) +
            (self.national_pension or 0) + (self.emp_ins or 0) + (self.longterm_care_ins or 0) +
            (self.other_deduction or 0)
        )

        # 3. 실수령액 계산
        self.net_pay_amt = self.total_gross_amt - self.total_deduction_amt

        # 4. 법인 인건비 총계 계산 (급여 총계 + 회사 부담금)
        self.total_labor_cost = self.total_gross_amt + (
            (self.health_ins_comp or 0) + (self.pension_comp or 0) +
            (self.emp_ins_comp or 0) + (self.ind_acc_comp or 0)
        )

        super().save(*args, **kwargs)


class AttendanceLog(models.Model):
    att_id = models.BigAutoField(primary_key=True, verbose_name="근태기록ID")

    # 사원 마스터 참조
    emp = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        db_column='emp_id',
        related_name='attendance_logs',
        verbose_name="사원코드"
    )

    # 근무 기준일 (날짜별로 1개의 레코드만 존재하도록 설정)
    work_dt = models.DateField(verbose_name="근무기준일")

    # --- 실시간 편집 및 계산을 위한 핵심 필드 (Decimal) ---
    # 1. 정상 근무 (기본 8시간 등)
    normal_hours = models.DecimalField(
        max_digits=4, decimal_places=1, default=0, verbose_name="정상근무"
    )

    # 2. O/T (잔업 시간)
    ot_hours = models.DecimalField(
        max_digits=4, decimal_places=1, default=0, verbose_name="잔업시간"
    )

    # 3. 토일근무 (특근 시간)
    weekend_hours = models.DecimalField(
        max_digits=4, decimal_places=1, default=0, verbose_name="토일근무"
    )

    # --- 상태 기록 필드 (문자열) ---
    # 연차, 결근, 지각, 조퇴 등 텍스트 상태를 저장
    status_text = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="상태값"
    )

    # 비고
    remark = models.TextField(null=True, blank=True, verbose_name="비고")

    history = HistoricalRecords()

    class Meta:
        db_table = 'attendance_log'
        verbose_name = '근태 기록'
        verbose_name_plural = '근태 기록'
        # 한 사원이 같은 날짜에 중복된 기록을 갖지 못하도록 제약
        unique_together = ('emp', 'work_dt')

    def __str__(self):
        return f"{self.work_dt} {self.emp.emp_nm} (정상:{self.normal_hours}/OT:{self.ot_hours})"


class LateRecord(models.Model):
    """지각 기록 — 사원별 연월별 지각 횟수 저장 (누적은 전체 합산으로 계산)"""
    emp = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        db_column='emp_id',
        related_name='late_records',
        verbose_name="사원코드"
    )
    year = models.IntegerField(verbose_name="연도")
    month = models.IntegerField(verbose_name="월")
    count = models.PositiveIntegerField(default=0, verbose_name="지각 횟수")

    history = HistoricalRecords()

    class Meta:
        db_table = 'late_record'
        unique_together = ('emp', 'year', 'month')
        verbose_name = '지각 기록'
        verbose_name_plural = '지각 기록'

    def __str__(self):
        return f"{self.year}년 {self.month}월 {self.emp.emp_nm} 지각 {self.count}회"


class AnnualLeave(models.Model):
    """연차 관리 — 사원별 연도별 연차 부여/사용 현황"""
    emp = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        db_column='emp_id',
        related_name='annual_leaves',
        verbose_name="사원코드"
    )
    year = models.IntegerField(verbose_name="연도")
    total_days = models.DecimalField(
        max_digits=5, decimal_places=1, default=0, verbose_name="사용가능한연차(A)"
    )

    history = HistoricalRecords()

    class Meta:
        db_table = 'annual_leave'
        unique_together = ('emp', 'year')
        verbose_name = '연차 관리'
        verbose_name_plural = '연차 관리'

    def __str__(self):
        return f"{self.year}년 {self.emp.emp_nm} 연차"


class User(AbstractUser):
    """
    ERP 통합 계정 모델
    - Employee 모델과 1:1 연결되어 인적 사항을 참조합니다.
    - permission 앱의 UserRole을 참조하여 세부 권한을 제어합니다.
    """

    # 1. 사원 정보와 1:1 연결
    # Employee 모델의 emp_nm, dept, emp_tel 등을 직접 활용할 수 있습니다.
    employee = models.OneToOneField(
        'Employee',
        on_delete=models.CASCADE,
        related_name='user_account',
        null=True,
        blank=True,
        verbose_name="연결 사원"
    )

    # 2. 권한 및 역할 관리 (permission 앱 참조)
    role = models.ForeignKey(
        'permission.UserRole',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="권한 역할"
    )

    # 3. 소속 회사 구분 (dst / jsystem)
    # Department의 dept_comp와 일치시켜 데이터 필터링 시 기준으로 사용합니다.
    COMPANY_CHOICES = [
        ('dst', 'DST'),
        ('jsystem', 'J-System'),
    ]
    company = models.CharField(
        max_length=10,
        choices=COMPANY_CHOICES,
        default='dst',
        verbose_name="소속 회사"
    )

    # 4. 계정 상태 및 보안 (중복 필드 제거)
    is_approved = models.BooleanField(default=False, verbose_name="가입 승인 여부")
    last_login_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="최근 접속 IP")

    class Meta:
        db_table = 'erp_user'
        verbose_name = '사용자 계정'
        verbose_name_plural = '사용자 계정'

    def __str__(self):
        # 실명과 사번을 Employee 모델에서 가져와 표시합니다.
        if self.employee:
            return f"{self.username} ({self.employee.emp_nm} / {self.employee.dept.dept_nm})"
        return f"{self.username} (사원 미배정)"

    @property
    def phone_number(self):
        """Employee 모델의 연락처를 가져옵니다."""
        return self.employee.emp_tel if self.employee else ""

    @property
    def department(self):
        """Employee 모델의 부서 객체를 가져옵니다."""
        return self.employee.dept if self.employee else None
