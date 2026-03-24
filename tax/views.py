from datetime import datetime

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import ast
import operator as _op

from .models import SalaryRate, SalaryFormula


# ── 안전한 수식 평가기 ────────────────────────────────────────────────────────
_SAFE_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub,
    ast.Mult: _op.mul, ast.Div: _op.truediv,
}

def _safe_eval(expr: str, variables: dict) -> float:
    def _eval(node):
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"알 수 없는 변수: {node.id}")
            return float(variables[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'round':
            if len(node.args) == 2:
                return round(_eval(node.args[0]), int(_eval(node.args[1])))
            return round(_eval(node.args[0]))
        raise ValueError(f"지원하지 않는 연산: {type(node).__name__}")
    tree = ast.parse(expr.strip(), mode='eval')
    return _eval(tree.body)


@login_required
def salary_rate_list(request):
    current_year = datetime.now().year
    try:
        selected_year = int(request.GET.get('year', current_year))
    except (ValueError, TypeError):
        selected_year = current_year

    # 선택한 연도가 없으면 기본값으로 자동 생성
    rate, created = SalaryRate.objects.get_or_create(year=selected_year)

    # 드롭다운용 연도 목록: 1998년 ~ 내년까지 전체
    existing = set(SalaryRate.objects.values_list('year', flat=True))
    years = sorted(existing | set(range(1998, current_year + 2)), reverse=True)

    return render(request, 'tax/salary_rate.html', {
        'rate': rate,
        'years': years,
        'selected_year': selected_year,
        'current_year': current_year,
        'created': created,
    })


@login_required
def salary_formula(request):
    formulas = SalaryFormula.objects.all()
    variables = [
        ('통상임금',  '기본급 + 직책수당 + 경력수당'),
        ('통상시급',  '통상임금 ÷ 209'),
        ('ot시간',    '해당 월 잔업시간 합계'),
        ('정상시간',  '해당 월 정상근무시간 합계'),
        ('토일시간',  '해당 월 토일근무시간 합계'),
    ]
    return render(request, 'tax/salary_formula.html', {
        'formulas': formulas,
        'variables': variables,
    })


@login_required
@require_POST
def salary_formula_update(request):
    try:
        data = json.loads(request.body)
        formula_id = data.get('formula_id')
        formula_expr = data.get('formula_expr', '').strip()

        if not formula_expr:
            return JsonResponse({'status': 'error', 'message': '계산식을 입력해주세요.'}, status=400)

        # 문법 검증
        _safe_eval(formula_expr, {
            '통상임금': 3000000, '통상시급': 14354,
            'ot시간': 10, '정상시간': 209, '토일시간': 0,
        })

        formula = SalaryFormula.objects.get(pk=formula_id)
        formula.formula_expr = formula_expr
        formula.save()
        return JsonResponse({'status': 'success', 'formula_expr': formula_expr})
    except SalaryFormula.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '항목을 찾을 수 없습니다.'}, status=404)
    except (ValueError, SyntaxError) as e:
        return JsonResponse({'status': 'error', 'message': f'계산식 오류: {e}'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
def salary_formula_apply(request):
    """해당 월 급여 레코드에 계산식을 적용"""
    try:
        data = json.loads(request.body)
        salary_month = data.get('salary_month')
        if not salary_month:
            return JsonResponse({'status': 'error', 'message': '급여 귀속월을 지정해주세요.'}, status=400)

        from hr.models import Salary, AttendanceLog
        from django.db.models import Sum

        formulas = SalaryFormula.objects.filter(is_active=True)
        salaries = Salary.objects.filter(salary_month=salary_month)

        year, month = int(salary_month[:4]), int(salary_month[5:7])

        # 사원별 근태 집계
        att_map = {
            item['emp_id']: item
            for item in AttendanceLog.objects.filter(
                work_dt__year=year, work_dt__month=month
            ).values('emp_id').annotate(
                정상시간=Sum('normal_hours'),
                ot시간_att=Sum('ot_hours'),
                토일시간=Sum('weekend_hours'),
            )
        }

        updated = 0
        for salary in salaries:
            통상임금 = float((salary.base_amt or 0) + (salary.pos_allowance or 0) + (salary.exp_allowance or 0))
            통상시급 = 통상임금 / 209
            att = att_map.get(salary.emp_id, {})
            variables = {
                '통상임금': 통상임금,
                '통상시급': 통상시급,
                'ot시간':   float(att.get('ot시간_att') or salary.ot_hours or 0),
                '정상시간': float(att.get('정상시간') or 0),
                '토일시간': float(att.get('토일시간') or 0),
            }
            for formula in formulas:
                try:
                    result = Decimal(str(_safe_eval(formula.formula_expr, variables))).quantize(
                        Decimal('1'), rounding=ROUND_HALF_UP
                    )
                    setattr(salary, formula.salary_field, result)
                except Exception:
                    pass
            salary.save()
            updated += 1

        return JsonResponse({'status': 'success', 'updated': updated})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
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


@login_required
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
            """원 단위 반올림"""
            return Decimal(val).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        salaries = Salary.objects.filter(salary_month=salary_month)
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
