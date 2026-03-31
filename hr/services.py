from decimal import Decimal

from django.db.models import Sum

from .models import AttendanceLog, Employee, Salary


# ── 커스텀 예외 ────────────────────────────────────────────────────────────────

class SalaryCalculationError(Exception):
    """급여 계산 중 예기치 않은 오류 발생 시 사용한다."""

# 급여 수정 허용 필드 화이트리스트 (views와 공유)
ALLOWED_SALARY_FIELDS = {
    'base_amt', 'pos_allowance', 'exp_allowance', 'weekly_holiday_pay',
    'ot_pay', 'non_smoke_allowance', 'func_allowance',
    'comm_allowance', 'special_allowance', 'hourly_adj_amt', 'meal_pay',
    'car_allowance', 'income_tax', 'local_income_tax', 'health_ins',
    'national_pension', 'emp_ins', 'longterm_care_ins', 'other_deduction', 'refund_amt',
    'health_ins_comp', 'pension_comp', 'emp_ins_comp', 'ind_acc_comp',
    'tax_free_exclusion', 'remark',
}


def ensure_salary_records(target_month: str) -> None:
    """재직 사원 중 해당 월 급여 레코드가 없는 사원에게 초기 레코드를 생성한다."""
    active_employees = Employee.objects.filter(emp_stat='재직')
    existing_emp_ids = set(
        Salary.objects.filter(salary_month=target_month).values_list('emp_id', flat=True)
    )

    new_salaries = [
        Salary(emp=emp, salary_month=target_month)
        for emp in active_employees
        if emp.pk not in existing_emp_ids
    ]
    if new_salaries:
        Salary.objects.bulk_create(new_salaries, ignore_conflicts=True)


def sync_ot_from_attendance(target_month: str, year: int, month: int) -> None:
    """근태 기록의 월별 OT 합계를 급여 테이블의 ot_hours에 반영한다."""
    ot_totals = AttendanceLog.objects.filter(
        work_dt__year=year,
        work_dt__month=month,
    ).values('emp_id').annotate(total_ot=Sum('ot_hours'))

    ot_map = {
        item['emp_id']: item['total_ot'] or Decimal('0')
        for item in ot_totals
    }

    to_update = []
    for s in Salary.objects.filter(salary_month=target_month):
        att_ot = ot_map.get(s.emp_id, Decimal('0'))
        if s.ot_hours != att_ot:
            s.ot_hours = att_ot
            to_update.append(s)

    if to_update:
        Salary.objects.bulk_update(to_update, ['ot_hours'])


def get_salary_totals(target_month: str, company: str = None) -> dict:
    """해당 월 전체 급여 합계를 집계하여 반환한다 (footer/API 공용)."""
    qs = Salary.objects.filter(salary_month=target_month)
    if company:
        qs = qs.filter(emp__dept__dept_comp=company)
    return qs.aggregate(
        base_amt=Sum('base_amt'),
        pos_allowance=Sum('pos_allowance'),
        exp_allowance=Sum('exp_allowance'),
        weekly_holiday_pay=Sum('weekly_holiday_pay'),
        ot_hours=Sum('ot_hours'),
        ot_pay=Sum('ot_pay'),
        non_smoke_allowance=Sum('non_smoke_allowance'),
        func_allowance=Sum('func_allowance'),
        comm_allowance=Sum('comm_allowance'),
        special_allowance=Sum('special_allowance'),
        hourly_adj_amt=Sum('hourly_adj_amt'),
        meal_pay=Sum('meal_pay'),
        car_allowance=Sum('car_allowance'),
        income_tax=Sum('income_tax'),
        local_income_tax=Sum('local_income_tax'),
        health_ins=Sum('health_ins'),
        national_pension=Sum('national_pension'),
        emp_ins=Sum('emp_ins'),
        longterm_care_ins=Sum('longterm_care_ins'),
        other_deduction=Sum('other_deduction'),
        refund_amt=Sum('refund_amt'),
        total_gross_amt=Sum('total_gross_amt'),
        total_deduction_amt=Sum('total_deduction_amt'),
        net_pay_amt=Sum('net_pay_amt'),
        tax_free_exclusion=Sum('tax_free_exclusion'),
    )


# ── 급여 합계 계산 (순수 함수) ────────────────────────────────────────────────

def calculate_salary_totals(salary: Salary) -> dict:
    """
    Salary 인스턴스의 각 항목을 합산하여 계산값을 반환한다.
    DB 저장은 하지 않으며, Salary.save()의 계산 로직과 동일하다.

    반환값 예시:
        {
            'total_gross_amt': Decimal('3000000'),
            'total_deduction_amt': Decimal('300000'),
            'net_pay_amt': Decimal('2700000'),
            'total_labor_cost': Decimal('3150000'),
        }
    """
    def _d(val) -> Decimal:
        return Decimal(str(val)) if val else Decimal('0')

    total_gross = (
        _d(salary.base_amt) + _d(salary.pos_allowance) + _d(salary.exp_allowance) +
        _d(salary.weekly_holiday_pay) + _d(salary.ot_pay) + _d(salary.non_smoke_allowance) +
        _d(salary.func_allowance) + _d(salary.comm_allowance) + _d(salary.special_allowance) +
        _d(salary.hourly_adj_amt) + _d(salary.meal_pay) + _d(salary.car_allowance)
    )
    total_deduction = (
        _d(salary.income_tax) + _d(salary.local_income_tax) + _d(salary.health_ins) +
        _d(salary.national_pension) + _d(salary.emp_ins) + _d(salary.longterm_care_ins) +
        _d(salary.other_deduction) + _d(salary.refund_amt)
    )
    net_pay = total_gross - total_deduction
    tax_free_exclusion = total_gross - _d(salary.meal_pay) - _d(salary.car_allowance)
    total_labor_cost = total_gross + (
        _d(salary.health_ins_comp) + _d(salary.pension_comp) +
        _d(salary.emp_ins_comp) + _d(salary.ind_acc_comp)
    )

    return {
        'total_gross_amt': total_gross,
        'total_deduction_amt': total_deduction,
        'net_pay_amt': net_pay,
        'tax_free_exclusion': tax_free_exclusion,
        'total_labor_cost': total_labor_cost,
    }


# ── 월별 근태 집계 ─────────────────────────────────────────────────────────────

def get_monthly_attendance_summary(emp_id: int, year: int, month: int) -> dict:
    """
    특정 사원의 해당 월 AttendanceLog를 집계하여 반환한다.

    반환값 예시:
        {
            'normal_hours': Decimal('160.0'),
            'ot_hours': Decimal('12.5'),
            'weekend_hours': Decimal('8.0'),
        }
    """
    result = AttendanceLog.objects.filter(
        emp_id=emp_id,
        work_dt__year=year,
        work_dt__month=month,
    ).aggregate(
        normal_hours=Sum('normal_hours'),
        ot_hours=Sum('ot_hours'),
        weekend_hours=Sum('weekend_hours'),
    )

    return {
        'normal_hours': result['normal_hours'] or Decimal('0'),
        'ot_hours': result['ot_hours'] or Decimal('0'),
        'weekend_hours': result['weekend_hours'] or Decimal('0'),
    }
