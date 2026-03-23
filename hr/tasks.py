import logging

from celery import shared_task

from .models import Salary
from . import services

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='hr.calculate_monthly_payroll',
    max_retries=3,
    default_retry_delay=60,  # 60초 후 재시도
)
def calculate_monthly_payroll(self, emp_id: int, salary_month: str):
    """
    특정 사원의 월 급여를 계산하고 Salary 레코드에 합계를 반영한다.

    Args:
        emp_id      : 사원 PK (Employee.emp_id)
        salary_month: 급여 귀속월 (예: '2025-03')

    재시도: 최대 3회 / 60초 간격

    Beat 예약 예시 (admin > Periodic Tasks):
        Task      : hr.calculate_monthly_payroll
        Signature : apply_async(args=[emp_id, salary_month])
    """
    try:
        salary = Salary.objects.select_related('emp').get(
            emp_id=emp_id,
            salary_month=salary_month,
        )
    except Salary.DoesNotExist:
        logger.warning(
            "[calculate_monthly_payroll] Salary 없음 emp_id=%s, month=%s",
            emp_id, salary_month
        )
        return None

    try:
        totals = services.calculate_salary_totals(salary)

        # 계산 결과를 Salary 필드에 반영 후 저장
        salary.total_gross_amt = totals['total_gross_amt']
        salary.total_deduction_amt = totals['total_deduction_amt']
        salary.net_pay_amt = totals['net_pay_amt']
        salary.total_labor_cost = totals['total_labor_cost']
        salary.save(update_fields=[
            'total_gross_amt', 'total_deduction_amt',
            'net_pay_amt', 'total_labor_cost',
        ])

        logger.info(
            "[calculate_monthly_payroll] 완료 emp_id=%s, month=%s, 실수령=%s",
            emp_id, salary_month, totals['net_pay_amt']
        )
        return {
            'emp_id': emp_id,
            'salary_month': salary_month,
            'net_pay_amt': str(totals['net_pay_amt']),
        }

    except Exception as exc:
        logger.error(
            "[calculate_monthly_payroll] 오류 emp_id=%s, month=%s | %s",
            emp_id, salary_month, exc
        )
        raise self.retry(exc=exc, countdown=60)
