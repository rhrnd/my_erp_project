from datetime import datetime

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

from permission.decorators import erp_permission_required
from permission.services import filter_queryset_by_scope, has_permission
from .models import SalaryRate


@erp_permission_required('tax_salary_rate', 'view')
def salary_rate_list(request):
    current_year = datetime.now().year
    try:
        selected_year = int(request.GET.get('year', current_year))
    except (ValueError, TypeError):
        selected_year = current_year

    can_edit = has_permission(request.user, 'tax_salary_rate', 'edit')
    try:
        rate = SalaryRate.objects.get(year=selected_year)
        created = False
    except SalaryRate.DoesNotExist:
        if can_edit:
            rate = SalaryRate.objects.create(year=selected_year)
            created = True
        else:
            rate = SalaryRate(year=selected_year)
            created = False

    # 드롭다운용 연도 목록: 1998년 ~ 내년까지 전체
    existing = set(SalaryRate.objects.values_list('year', flat=True))
    years = sorted(existing | set(range(1998, current_year + 2)), reverse=True)

    return render(request, 'tax/salary_rate.html', {
        'rate': rate,
        'years': years,
        'selected_year': selected_year,
        'current_year': current_year,
        'created': created,
        'can_edit': can_edit,
    })



@erp_permission_required('tax_salary_rate', 'edit')
@require_POST
def salary_rate_update(request):
    try:
        data = json.loads(request.body)
        rate_id = data.get('rate_id')
        field = data.get('field')
        value = data.get('value')

        ALLOWED_FIELDS = {
            # 직원 부담
            'health_ins_rate', 'longterm_care_rate', 'pension_rate', 'emp_ins_rate',
            # 회사 부담
            'health_ins_rate_comp', 'longterm_care_rate_comp', 'pension_rate_comp',
            'emp_ins_rate_comp', 'ind_acc_rate',
        }
        if field not in ALLOWED_FIELDS:
            return JsonResponse({'status': 'error', 'message': '수정 불가능한 필드입니다.'}, status=400)

        try:
            value = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            return JsonResponse({'status': 'error', 'message': '올바른 숫자를 입력해주세요.'}, status=400)

        rate = SalaryRate.objects.get(pk=rate_id)
        setattr(rate, field, value)
        rate.save()
        return JsonResponse({'status': 'success'})
    except SalaryRate.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '데이터를 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_salary', 'edit')
@require_POST
def salary_auto_calculate(request):
    """해당 월의 급여 레코드에 등록된 요율을 적용해 보험료를 자동 계산 후 저장"""
    try:
        data = json.loads(request.body)
        salary_month = data.get('salary_month')  # 'YYYY-MM'
        if not salary_month:
            return JsonResponse({'status': 'error', 'message': '급여 귀속월을 지정해주세요.'}, status=400)

        year = int(salary_month[:4])

        try:
            rate = SalaryRate.objects.get(year=year)
        except SalaryRate.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'{year}년 요율 데이터가 없습니다. 요율 관리 페이지에서 먼저 등록해주세요.'
            }, status=400)

        from hr.models import Salary

        def r(val):
            """10원 단위 내림 (일의 자리 버림)"""
            return (Decimal(val).quantize(Decimal('1'), rounding=ROUND_HALF_UP) // 10) * 10

        exclude_ids = data.get('exclude_ids', [])
        salaries = filter_queryset_by_scope(
            Salary.objects.filter(salary_month=salary_month).select_related('emp__dept'),
            request.user,
            'hr_salary',
            action='edit',
            employee_field='emp',
            department_field='emp__dept',
        ).exclude(pk__in=exclude_ids)
        updated = 0

        for salary in salaries:
            # 과세 기준액: 총급여 - 비과세(식대 + 자가운전보조금)
            taxable = (salary.total_gross_amt or 0) - (salary.meal_pay or 0) - (salary.car_allowance or 0)
            if taxable < 0:
                taxable = Decimal('0')

            # ── 직원 부담 계산 ───────────────────────────────────────────────
            health_ins = r(taxable * rate.health_ins_rate / 100)
            longterm_care_ins = r(health_ins * rate.longterm_care_rate / 100)
            national_pension = r(taxable * rate.pension_rate / 100)
            emp_ins = r(taxable * rate.emp_ins_rate / 100)

            # ── 회사 부담 계산 ───────────────────────────────────────────────
            health_ins_comp = r(taxable * rate.health_ins_rate_comp / 100)
            pension_comp = r(taxable * rate.pension_rate_comp / 100)
            emp_ins_comp = r(taxable * rate.emp_ins_rate_comp / 100)
            ind_acc_comp = r(taxable * rate.ind_acc_rate / 100)

            salary.health_ins = health_ins
            salary.longterm_care_ins = longterm_care_ins
            salary.national_pension = national_pension
            salary.emp_ins = emp_ins
            salary.health_ins_comp = health_ins_comp
            salary.pension_comp = pension_comp
            salary.emp_ins_comp = emp_ins_comp
            salary.ind_acc_comp = ind_acc_comp
            salary.save()
            updated += 1

        return JsonResponse({'status': 'success', 'updated': updated})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
