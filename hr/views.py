import calendar
import html
import json
from functools import lru_cache
from itertools import zip_longest

import holidays as holidays_lib
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

from django.db.models import Sum, Case, When, Value, FloatField
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from permission.decorators import erp_permission_required
from permission.services import filter_queryset_by_scope, has_permission
from .forms import SalarySearchForm, PtoSearchForm
from django.db.models import F
from .models import Employee, Department, Salary, AttendanceLog, AnnualLeave, LateRecord, AttendanceRemark
from . import services


@lru_cache(maxsize=5)
@lru_cache(maxsize=5)
def _get_kr_holidays(year: int) -> dict:
    """연도별 한국 공휴일을 캐싱하여 반환한다 (서버 재시작 전까지 유지)."""
    return dict(holidays_lib.KR(years=year))


def _null(val):
    """빈 문자열을 None으로 정규화한다 (nullable 필드에 빈 문자열이 저장되는 것을 방지)."""
    return val if val not in ('', None) else None


def _parse_decimal(value, field_name, *, min_value=None):
    try:
        parsed = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f'{field_name}은(는) 숫자로 입력해주세요.')

    if not parsed.is_finite():
        raise ValueError(f'{field_name}은(는) 올바른 숫자로 입력해주세요.')

    if min_value is not None and parsed < Decimal(str(min_value)):
        raise ValueError(f'{field_name}은(는) {min_value} 이상이어야 합니다.')

    return parsed


def _period_from_form(form, default_year, default_month=None):
    if form.is_valid():
        selected_year = int(form.cleaned_data['year'])
        selected_month = int(form.cleaned_data['month']) if default_month is not None and 'month' in form.cleaned_data else None
    else:
        selected_year = default_year
        selected_month = default_month

    if selected_month is None:
        return selected_year

    return selected_year, selected_month


def _is_valid_work_date(year, month, day):
    try:
        calendar.monthrange(year, month)
        date(year, month, day)
    except ValueError:
        return False
    return True


def _aggregate_salary_totals(queryset):
    return queryset.aggregate(
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


@erp_permission_required('hr_employee', 'view')
def hr_list(request):
    # 실시간 검색(JS)을 사용하므로 서버에서는 전체 목록을 반환합니다.
    employees = filter_queryset_by_scope(
        Employee.objects.select_related('dept'),
        request.user,
        'hr_employee',
        employee_field='self',
        department_field='dept',
    ).order_by('emp_hire', 'emp_no')
    departments = Department.objects.filter(in_use=True).order_by('dept_nm')
    companies = Department.objects.filter(in_use=True).values_list(
        'dept_comp', flat=True).distinct().order_by('dept_comp')
    return render(request, 'hr/hr_list.html', {
        'employees': employees,
        'departments': departments,
        'companies': companies,
        'can_create': has_permission(request.user, 'hr_employee', 'create'),
        'can_edit': has_permission(request.user, 'hr_employee', 'edit'),
    })


@erp_permission_required('hr_employee', 'create')
@require_POST
def employee_create(request):
    try:
        data = json.loads(request.body)

        # 부서 ID로 부서 객체 조회 (없으면 에러 발생시켜 예외 처리)
        dept_id = data.get('dept')
        if not dept_id:
            raise ValueError("부서를 선택해야 합니다.")
        dept_instance = Department.objects.get(pk=dept_id)

        Employee.objects.create(
            emp_no=data['emp_id'],  # 프론트에서 보낸 사번(emp_id)을 모델의 emp_no에 저장
            emp_nm=data['name'],
            dept=dept_instance,     # ForeignKey 객체 할당
            emp_pos=data['position'],
            emp_tel=data['phone'],
            emp_hire=data['join_date'],
            emp_rn=data.get('resident_number', ''),  # 주민등록번호 필수 필드 추가
            emp_add=data['address'],
            emp_stat='재직'
        )

        # [AuditLog] 사원 생성 로그 기록
        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            category='인사관리/사원리스트',
            target_name=data['name'],
            changes={
                '사원번호': data['emp_id'],
                '이름': data['name'],
                '부서': dept_instance.dept_nm,
                '직급': data.get('position') or '',
                '입사일': data['join_date'],
            },
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_employee', 'edit')
@require_POST
def employee_update_status(request):
    try:
        data = json.loads(request.body)
        # emp_id(PK)가 아닌 emp_no(사번)으로 조회
        emp = filter_queryset_by_scope(
            Employee.objects.all(),
            request.user,
            'hr_employee',
            action='edit',
            employee_field='self',
            department_field='dept',
        ).get(emp_no=data['emp_id'])
        emp.emp_stat = data['status']
        change_reason = data.get('change_reason', '').strip()
        if change_reason:
            emp._change_reason = change_reason
        emp.save()

        # [AuditLog] 상태 변경 로그 기록
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리/사원리스트',
            target_name=emp.emp_nm,
            changes={'재직상태': {'이전': emp.emp_stat, '이후': data['status']}, '변경사유': change_reason},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'status': 'success'})
    except Employee.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '존재하지 않는 사원입니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_employee', 'edit')
@require_POST
def employee_update(request):
    try:
        data = json.loads(request.body)
        emp = filter_queryset_by_scope(
            Employee.objects.select_related('dept'),
            request.user,
            'hr_employee',
            action='edit',
            employee_field='self',
            department_field='dept',
        ).get(emp_no=data['emp_id'])

        # 변경 전 값 캡처
        old = {
            '이름': emp.emp_nm,
            '부서': emp.dept.dept_nm if emp.dept else '',
            '직급': emp.emp_pos or '',
            '연락처': emp.emp_tel or '',
            '입사일': str(emp.emp_hire) if emp.emp_hire else '',
            '퇴사일': str(emp.emp_retire_dt) if emp.emp_retire_dt else '',
            '주소': emp.emp_add or '',
        }

        # 값 업데이트
        if data.get('dept'):
            emp.dept = Department.objects.get(pk=data['dept'])
        emp.emp_nm = data['name']
        emp.emp_pos = _null(data.get('position'))
        emp.emp_tel = _null(data.get('phone'))
        emp.emp_hire = data['join_date']
        emp.emp_add = _null(data.get('address'))
        emp.emp_retire_dt = _null(data.get('retire_date'))
        if 'resident_number' in data and data['resident_number']:
            emp.emp_rn = data['resident_number']
        emp.save()

        # 변경 후 값 — 변경된 필드만 before/after로 기록
        new = {
            '이름': emp.emp_nm,
            '부서': emp.dept.dept_nm if emp.dept else '',
            '직급': emp.emp_pos or '',
            '연락처': emp.emp_tel or '',
            '입사일': str(emp.emp_hire) if emp.emp_hire else '',
            '퇴사일': str(emp.emp_retire_dt) if emp.emp_retire_dt else '',
            '주소': emp.emp_add or '',
        }
        changes = {k: {'이전': old[k], '이후': new[k]} for k in old if old[k] != new[k]}

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리/사원리스트',
            target_name=emp.emp_nm,
            changes=changes if changes else {'메시지': '변경 내용 없음'},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'status': 'success'})
    except Employee.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '존재하지 않는 사원입니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_department', 'view')
def department_list(request):
    """부서 관리 페이지"""
    departments = Department.objects.all().order_by('dept_comp', 'dept_nm')
    # 회사별 그룹핑
    companies_map = {}
    for dept in departments:
        companies_map.setdefault(dept.dept_comp, []).append(dept)
    companies = [{'name': comp, 'depts': depts} for comp, depts in companies_map.items()]
    return render(request, 'hr/department_list.html', {
        'departments': departments,
        'companies': companies,
        'can_create': has_permission(request.user, 'hr_department', 'create'),
        'can_edit': has_permission(request.user, 'hr_department', 'edit'),
    })


@erp_permission_required('hr_department', 'create')
@require_POST
def department_create(request):
    """부서 등록 API"""
    try:
        data = json.loads(request.body)
        dept_comp = data.get('comp')
        dept_nm = data.get('name')

        if not dept_comp:
            return JsonResponse({'status': 'error', 'message': '소속회사명을 입력해주세요.'}, status=400)
        if not dept_nm:
            return JsonResponse({'status': 'error', 'message': '부서명을 입력해주세요.'}, status=400)

        dept = Department.objects.create(
            dept_comp=dept_comp,
            dept_nm=dept_nm,
            in_use=True
        )

        # [AuditLog] 부서 생성 로그
        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            category='인사관리/부서관리',
            target_name=dept.dept_nm,
            changes={'소속회사명': dept_comp, '부서명': dept_nm},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_department', 'edit')
@require_POST
def department_update(request):
    """부서 수정 API"""
    try:
        data = json.loads(request.body)
        dept_id = data.get('id')
        dept_comp = data.get('comp')
        dept_nm = data.get('name')
        in_use = data.get('in_use')

        dept = Department.objects.get(pk=dept_id)

        # 변경 전 값 캡처
        old = {'소속회사명': dept.dept_comp, '부서명': dept.dept_nm, '사용여부': dept.in_use}

        dept.dept_comp = dept_comp
        dept.dept_nm = dept_nm
        dept.in_use = in_use
        dept.save()

        new = {'소속회사명': dept_comp, '부서명': dept_nm, '사용여부': in_use}
        changes = {k: {'이전': old[k], '이후': new[k]} for k in old if str(old[k]) != str(new[k])}

        # [AuditLog] 부서 수정 로그
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리/부서관리',
            target_name=dept.dept_nm,
            changes=changes if changes else {'메시지': '변경 내용 없음'},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'status': 'success'})
    except Department.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '존재하지 않는 부서입니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_salary', 'view')
def salary_list(request):
    """급여 관리 페이지"""
    # 1. 폼 초기화: GET 데이터가 있으면 바인딩, 없으면 기본값(None)
    # 초기값이 현재 연월로 설정된 폼을 생성합니다.
    now = datetime.now()
    form = SalarySearchForm(request.GET or None)

    # 2. 폼 유효성 검사: 비정상 GET 값은 현재 연월로 되돌립니다.
    selected_year, selected_month = _period_from_form(form, now.year, now.month)

    # 3. 급여 데이터 조회
    # DB에는 'YYYY-MM' 문자열 형태로 저장되어 있으므로 포맷팅
    target_month = f"{selected_year}-{selected_month:02d}"
    can_edit = has_permission(request.user, 'hr_salary', 'edit')

    if can_edit:
        # 해당 월에 급여 데이터가 없는 재직 사원이 있다면, 초기 데이터를 생성해줍니다.
        services.ensure_salary_records(target_month)

        # 근태 O/T 합계를 급여 잔업시간에 자동 반영
        services.sync_ot_from_attendance(target_month, selected_year, selected_month)

    selected_company = request.GET.get('company', '')

    salary_qs = filter_queryset_by_scope(
        Salary.objects.filter(salary_month=target_month).select_related('emp__dept'),
        request.user,
        'hr_salary',
        employee_field='emp',
        department_field='emp__dept',
    )
    if selected_company:
        salary_qs = salary_qs.filter(emp__dept__dept_comp=selected_company)
    salaries = list(salary_qs.order_by('emp__emp_no'))

    # 지각 사이클 계산 (LateRecord 기반)
    emp_ids = [s.emp_id for s in salaries]
    # 해당 월까지의 누적 지각 (이전 달 포함)
    from django.db.models import Q
    cum_map = dict(
        LateRecord.objects.filter(emp_id__in=emp_ids)
        .filter(Q(year__lt=selected_year) | Q(year=selected_year, month__lte=selected_month))
        .values('emp_id').annotate(total=Sum('count'))
        .values_list('emp_id', 'total')
    )
    # 전달까지의 누적 (사이클 리셋 판단용)
    prev_year, prev_month = (selected_year, selected_month - 1) if selected_month > 1 else (selected_year - 1, 12)
    prev_map = dict(
        LateRecord.objects.filter(emp_id__in=emp_ids)
        .filter(Q(year__lt=prev_year) | Q(year=prev_year, month__lte=prev_month))
        .values('emp_id').annotate(total=Sum('count'))
        .values_list('emp_id', 'total')
    )
    for s in salaries:
        cumulative = cum_map.get(s.emp_id, 0)
        prev_cumulative = prev_map.get(s.emp_id, 0)
        # 이번 달에 새로운 3의 배수에 도달했으면 3 표시, 아니면 cumulative % 3
        if cumulative % 3 == 0 and cumulative > 0 and cumulative > prev_cumulative:
            s.late_cycle = 3
        else:
            s.late_cycle = cumulative % 3
        s.late_cumulative = cumulative
        s.late_deductions = cumulative // 3

    # 4. 합계 계산 (Footer 표시용)
    totals = _aggregate_salary_totals(salary_qs)

    # 해당 연도 요율 (자동계산 안내용)
    from tax.models import SalaryRate
    try:
        salary_rate = SalaryRate.objects.get(year=selected_year)
    except SalaryRate.DoesNotExist:
        salary_rate = None

    # 5. 권한 체크 (템플릿에서 버튼 노출 제어용)
    can_export = has_permission(request.user, 'hr_salary', 'export')

    companies = Department.objects.filter(in_use=True).values_list(
        'dept_comp', flat=True).distinct().order_by('dept_comp')

    context = {
        'form': form,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'salaries': salaries,
        'totals': totals,
        'can_edit': can_edit,
        'can_export': can_export,
        'companies': companies,
        'selected_company': selected_company,
        'salary_rate': salary_rate,
    }

    return render(request, 'hr/salary.html', context)


@erp_permission_required('hr_salary', 'edit')
@require_POST
def salary_update(request):
    """급여 항목 실시간 수정 API"""
    try:
        data = json.loads(request.body)
        salary_id = data.get('salary_id')
        field = data.get('field')
        value = data.get('value', 0)
        selected_company = data.get('company', '')

        # remark는 텍스트 필드로 별도 처리
        if field == 'remark':
            salary = filter_queryset_by_scope(
                Salary.objects.select_related('emp__dept'),
                request.user,
                'hr_salary',
                action='edit',
                employee_field='emp',
                department_field='emp__dept',
            ).get(pk=salary_id)
            salary.remark = str(value or '').strip()
            salary.save(update_fields=['remark'])
            return JsonResponse({'status': 'success'})

        if field not in services.ALLOWED_SALARY_FIELDS:
            return JsonResponse({'status': 'error', 'message': '수정 불가능한 필드입니다.'}, status=400)

        value = _parse_decimal(value, '급여 항목')

        salary = filter_queryset_by_scope(
            Salary.objects.select_related('emp__dept'),
            request.user,
            'hr_salary',
            action='edit',
            employee_field='emp',
            department_field='emp__dept',
        ).get(pk=salary_id)
        setattr(salary, field, value)
        salary.save()

        # 합계를 서비스 레이어에서 계산 후 DB에 반영
        row_totals = services.calculate_salary_totals(salary)
        Salary.objects.filter(pk=salary_id).update(
            total_gross_amt=row_totals['total_gross_amt'],
            total_deduction_amt=row_totals['total_deduction_amt'],
            net_pay_amt=row_totals['net_pay_amt'],
            tax_free_exclusion=row_totals['tax_free_exclusion'],
        )

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리/급여관리',
            target_name=f"{salary.emp.emp_nm} ({salary.salary_month} 급여)",
            changes={field: float(value)},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        scoped_salary_qs = filter_queryset_by_scope(
            Salary.objects.filter(salary_month=salary.salary_month),
            request.user,
            'hr_salary',
            employee_field='emp',
            department_field='emp__dept',
        )
        if selected_company:
            scoped_salary_qs = scoped_salary_qs.filter(emp__dept__dept_comp=selected_company)
        totals = _aggregate_salary_totals(scoped_salary_qs)
        response_totals = {k: float(v or 0) for k, v in totals.items()}

        return JsonResponse({
            'status': 'success',
            'row_total_gross': float(row_totals['total_gross_amt']),
            'row_total_deduction': float(row_totals['total_deduction_amt']),
            'row_net_pay': float(row_totals['net_pay_amt']),
            'row_tax_free_exclusion': float(row_totals['tax_free_exclusion']),
            'totals': response_totals,
        })
    except Salary.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '데이터를 찾을 수 없습니다.'}, status=404)
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@erp_permission_required('hr_attendance', 'view')
def attendance_list(request):
    now = datetime.now()

    # 1. 연/월 선택 값 가져오기
    searched = 'year' in request.GET or 'month' in request.GET
    form = SalarySearchForm(request.GET or None)
    selected_year, selected_month = _period_from_form(form, now.year, now.month)

    # 2. 폼 객체 생성 (사용자 선택값 유지)
    if not request.GET:
        form = SalarySearchForm(initial={
            'year': selected_year,
            'month': selected_month
        })

    # 3. 날짜 범위 계산
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    days_range = range(1, last_day + 1)

    # 4. 주말 / 공휴일
    weekend_days = [d for d in days_range if calendar.weekday(selected_year, selected_month, d) >= 5]
    kr_holidays = _get_kr_holidays(selected_year)
    holiday_days = {date.day: name for date, name in kr_holidays.items()
                    if date.month == selected_month and date.day not in weekend_days}

    # 5. 사원 목록 (항상 로드)
    selected_company = request.GET.get('company', '')
    companies = Department.objects.filter(in_use=True).values_list(
        'dept_comp', flat=True).distinct().order_by('dept_comp')

    emp_qs = filter_queryset_by_scope(
        Employee.objects.filter(emp_stat='재직').select_related('dept'),
        request.user,
        'hr_attendance',
        employee_field='self',
        department_field='dept',
    ).order_by('dept__dept_id', 'emp_no')
    if selected_company:
        emp_qs = emp_qs.filter(dept__dept_comp=selected_company)
    employees = list(emp_qs)
    employee_ids = [e.emp_id for e in employees]

    # 6. 근태 상세 데이터 — 조회 버튼을 눌렀을 때만 실행
    logs_map = {}
    cumulative_map = {}
    leave_monthly_map = {}
    leave_cum_map = {}
    remark_map = {}
    late_month_map = {}

    if searched:
        logs_map = {
            (log.emp_id, log.work_dt.day): log
            for log in AttendanceLog.objects.filter(
                emp_id__in=employee_ids,
                work_dt__year=selected_year,
                work_dt__month=selected_month,
            )
        }
        late_month_map = dict(
            LateRecord.objects.filter(
                emp_id__in=employee_ids, year=selected_year, month=selected_month
            ).values_list('emp_id', 'count')
        )
        cumulative_map = {
            item['emp_id']: {
                'cum_normal':  float(item['cum_normal']  or 0),
                'cum_ot':      float(item['cum_ot']      or 0),
                'cum_holiday': float(item['cum_holiday'] or 0),
            }
            for item in AttendanceLog.objects.filter(
                emp_id__in=employee_ids,
                work_dt__year=selected_year,
                work_dt__month__lte=selected_month,
            ).values('emp_id').annotate(
                cum_normal=Sum('normal_hours'),
                cum_ot=Sum('ot_hours'),
                cum_holiday=Sum('weekend_hours'),
            )
        }
        _leave_expr = Sum(Case(
            When(status_text='연차', then=Value(1.0)),
            When(status_text='반차', then=Value(0.5)),
            default=Value(0.0), output_field=FloatField()
        ))
        leave_monthly_map = dict(
            AttendanceLog.objects.filter(
                emp_id__in=employee_ids,
                work_dt__year=selected_year,
                work_dt__month=selected_month,
                status_text__in=['연차', '반차'],
            ).values('emp_id').annotate(total=_leave_expr).values_list('emp_id', 'total')
        )
        leave_cum_map = dict(
            AttendanceLog.objects.filter(
                emp_id__in=employee_ids,
                work_dt__year=selected_year,
                work_dt__month__lte=selected_month,
                status_text__in=['연차', '반차'],
            ).values('emp_id').annotate(total=_leave_expr).values_list('emp_id', 'total')
        )
        remark_map = dict(
            AttendanceRemark.objects.filter(
                emp_id__in=employee_ids, year=selected_year, month=selected_month,
            ).values_list('emp_id', 'remark')
        )

    # 7. 사원별 데이터 조립
    attendance_data = []
    for emp in employees:
        emp_dict = {
            'id': emp.emp_id, 'dept': emp.dept, 'name': emp.emp_nm,
            'daily': {},
            'total_normal': 0.0, 'total_ot': 0.0, 'total_holiday': 0.0,
            'cum_normal': 0.0,   'cum_ot': 0.0,   'cum_holiday': 0.0,
            'total_leave': 0.0,  'cum_leave': 0.0,
            'late_month': 0,     'remark': '',
        }
        if searched:
            cum = cumulative_map.get(emp.emp_id, {})
            emp_dict['cum_normal']  = cum.get('cum_normal', 0.0)
            emp_dict['cum_ot']      = cum.get('cum_ot', 0.0)
            emp_dict['cum_holiday'] = cum.get('cum_holiday', 0.0)
            emp_dict['total_leave'] = leave_monthly_map.get(emp.emp_id, 0.0)
            emp_dict['cum_leave']   = leave_cum_map.get(emp.emp_id, 0.0)
            emp_dict['remark']      = remark_map.get(emp.emp_id, '')
            emp_dict['late_month']  = late_month_map.get(emp.emp_id, 0)

            for d in days_range:
                log = logs_map.get((emp.emp_id, d))
                day_data = {'normal': '', 'status': '', 'ot': '', 'weekend': ''}
                if log:
                    if log.normal_hours > 0:
                        val = float(log.normal_hours)
                        day_data['normal'] = str(int(val)) if val % 1 == 0 else str(val)
                        emp_dict['total_normal'] += val
                    day_data['status'] = log.status_text.strip() if log.status_text else ''
                    val = float(log.ot_hours or 0)
                    if val > 0:
                        emp_dict['total_ot'] += val
                        day_data['ot'] = str(int(val)) if val % 1 == 0 else str(val)
                    if log.weekend_hours > 0:
                        val = float(log.weekend_hours)
                        day_data['weekend'] = str(int(val)) if val % 1 == 0 else str(val)
                        emp_dict['total_holiday'] += val
                emp_dict['daily'][d] = day_data

        attendance_data.append(emp_dict)

    # 8. 템플릿 전달
    return render(request, 'hr/attendance.html', {
        'form': form,
        'selected_year': selected_year,
        'selected_month': str(selected_month).zfill(2),
        'days_range': days_range,
        'weekend_days': weekend_days,
        'holiday_days': holiday_days,
        'attendance_data': attendance_data,
        'companies': companies,
        'selected_company': selected_company,
        'searched': searched,
        'can_edit': has_permission(request.user, 'hr_attendance', 'edit'),
        'can_export': has_permission(request.user, 'hr_attendance', 'export'),
    })


# 1. 클릭 시 칸 자체가 입력창으로 변함
@erp_permission_required('hr_attendance', 'edit')
def edit_attendance_cell(request, emp_id, year, month, day, work_type):
    if work_type not in {'status', 'normal', 'ot', 'weekend'} or not _is_valid_work_date(year, month, day):
        return HttpResponse('잘못된 근태 요청입니다.', status=400)

    try:
        filter_queryset_by_scope(
            Employee.objects.all(),
            request.user,
            'hr_attendance',
            action='edit',
            employee_field='self',
            department_field='dept',
        ).get(pk=emp_id)
        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
        log = AttendanceLog.objects.filter(emp_id=emp_id, work_dt=date_str).first()

        # 현재 칸에 들어갈 값 결정
        current_val = ""
        if log:
            if work_type == 'status':
                current_val = log.status_text or ""
            elif work_type == 'ot':
                current_val = log.ot_hours if log.ot_hours > 0 else ""
            elif work_type == 'normal':
                current_val = log.normal_hours if log.normal_hours > 0 else ""
            elif work_type == 'weekend':
                current_val = log.weekend_hours if log.weekend_hours > 0 else ""

        # 팝업 대신 바로 입력창(<input>) 반환
        safe_val = html.escape(str(current_val)) if current_val != "" else ""
        response_html = f'''
        <td class="p-0">
            <input type="text" name="value" value="{safe_val}"
                   class="form-control form-control-sm text-center border-primary"
                   style="height: 28px; font-size: 11px; border-radius: 0; outline: none;"
                   hx-post="/hr/attendance/save/{emp_id}/{year}/{month}/{day}/{work_type}/"
                   hx-trigger="blur, keyup[key=='Enter']"
                   hx-target="closest td" hx-swap="outerHTML" autofocus>
        </td>
        '''
        return HttpResponse(response_html)
    except Exception as e:
        _is_weekend = calendar.weekday(year, month, day) >= 5
        _is_holiday = date(year, month, day) in _get_kr_holidays(year) and not _is_weekend
        bg_class = " bg-weekend" if _is_weekend else (" bg-holiday" if _is_holiday else "")
        return HttpResponse(
            f'<td class="editable-cell text-center{bg_class} text-danger" '
            f'title="{html.escape(str(e))}">오류</td>',
            status=500
        )


@erp_permission_required('hr_attendance', 'view')
def cancel_attendance_cell(request, emp_id, year, month, day, work_type):
    if work_type not in {'status', 'normal', 'ot', 'weekend'} or not _is_valid_work_date(year, month, day):
        return HttpResponse('잘못된 근태 요청입니다.', status=400)

    try:
        filter_queryset_by_scope(
            Employee.objects.all(),
            request.user,
            'hr_attendance',
            employee_field='self',
            department_field='dept',
        ).get(pk=emp_id)
        date_str = f"{year}-{month:02d}-{day:02d}"
        log = AttendanceLog.objects.filter(emp_id=emp_id, work_dt=date_str).first()

        display_val = ""
        if log:
            if work_type == 'status':
                display_val = html.escape(log.status_text or "")
            else:
                hours = 0
                if work_type == 'ot':
                    hours = log.ot_hours
                elif work_type == 'normal':
                    hours = log.normal_hours
                elif work_type == 'weekend':
                    hours = log.weekend_hours
                val = float(hours)
                if val > 0:
                    display_val = str(int(val)) if val % 1 == 0 else str(val)

        _is_weekend = calendar.weekday(year, month, day) >= 5
        _is_holiday = date(year, month, day) in _get_kr_holidays(year) and not _is_weekend
        bg_class = " bg-weekend" if _is_weekend else (" bg-holiday" if _is_holiday else "")

        return HttpResponse(f'<td class="editable-cell text-center{bg_class}" hx-get="/hr/attendance/edit/{emp_id}/{year}/{month}/{day}/{work_type}/" hx-trigger="click" hx-target="this" hx-swap="outerHTML">{display_val}</td>')
    except Exception as e:
        _is_weekend = calendar.weekday(year, month, day) >= 5
        _is_holiday = date(year, month, day) in _get_kr_holidays(year) and not _is_weekend
        bg_class = " bg-weekend" if _is_weekend else (" bg-holiday" if _is_holiday else "")
        return HttpResponse(
            f'<td class="editable-cell text-center{bg_class} text-danger" '
            f'title="{html.escape(str(e))}">오류</td>',
            status=500
        )


# 2. 저장 시 숫자/문자 자동 판별 및 합계 업데이트
@erp_permission_required('hr_attendance', 'edit')
@require_POST
def save_attendance_cell(request, emp_id, year, month, day, work_type):
    if work_type not in {'status', 'normal', 'ot', 'weekend'} or not _is_valid_work_date(year, month, day):
        return JsonResponse({'status': 'error', 'message': '잘못된 근태 요청입니다.'}, status=400)

    try:
        filter_queryset_by_scope(
            Employee.objects.all(),
            request.user,
            'hr_attendance',
            action='edit',
            employee_field='self',
            department_field='dept',
        ).get(pk=emp_id)
        user_input = request.POST.get('value', '').strip()

        date_str = f"{year}-{int(month):02d}-{int(day):02d}"

        log, created = AttendanceLog.objects.get_or_create(emp_id=emp_id, work_dt=date_str)
        old_status = '' if created else (log.status_text or '')

        # 숫자/문자 판별
        is_num = False
        num_val = Decimal(0)
        try:
            num_val = Decimal(user_input)
            is_num = True
        except (InvalidOperation, ValueError):
            is_num = False

        if work_type in {'normal', 'ot', 'weekend'}:
            if not is_num:
                return JsonResponse({'status': 'error', 'message': '근무시간은 숫자로 입력해주세요.'}, status=400)
            if not num_val.is_finite() or num_val < 0:
                return JsonResponse({'status': 'error', 'message': '근무시간은 0 이상 숫자로 입력해주세요.'}, status=400)

        # 필드 매칭 로직
        if work_type == 'status':
            log.status_text = user_input
            # 지각 횟수 자동 증감
            was_late = (old_status == '지각')
            is_late  = (user_input == '지각')
            if was_late != is_late:
                lr, _ = LateRecord.objects.get_or_create(
                    emp_id=emp_id, year=year, month=month, defaults={'count': 0}
                )
                if is_late:
                    LateRecord.objects.filter(pk=lr.pk).update(count=F('count') + 1)
                else:
                    LateRecord.objects.filter(pk=lr.pk, count__gt=0).update(count=F('count') - 1)
        elif work_type == 'ot':
            log.ot_hours = num_val if is_num else 0
        elif work_type == 'normal':
            log.normal_hours = num_val if is_num else 0
        elif work_type == 'weekend':
            log.weekend_hours = num_val if is_num else 0

        log.save()

        _is_weekend = calendar.weekday(year, month, day) >= 5
        _is_holiday = date(year, month, day) in _get_kr_holidays(year) and not _is_weekend
        bg_class = " bg-weekend" if _is_weekend else (" bg-holiday" if _is_holiday else "")

        # 상태 칸 — 연차/반차 합계/누계 계산
        if work_type == 'status':
            _leave_expr = Sum(Case(
                When(status_text='연차', then=Value(1.0)),
                When(status_text='반차', then=Value(0.5)),
                default=Value(0.0),
                output_field=FloatField()
            ))
            monthly_leave = AttendanceLog.objects.filter(
                emp_id=emp_id, work_dt__year=year, work_dt__month=month,
                status_text__in=['연차', '반차']
            ).aggregate(total=_leave_expr)['total'] or 0.0
            cum_leave = AttendanceLog.objects.filter(
                emp_id=emp_id, work_dt__year=year, work_dt__month__lte=month,
                status_text__in=['연차', '반차']
            ).aggregate(total=_leave_expr)['total'] or 0.0
            late_count = LateRecord.objects.filter(
                emp_id=emp_id, year=year, month=month
            ).values_list('count', flat=True).first() or 0

            return JsonResponse({
                'status': 'success',
                'display': user_input,
                'total': round(float(monthly_leave), 1),
                'cum': round(float(cum_leave), 1),
                'total_id': f'total-status-{emp_id}',
                'cum_id': f'cum-status-{emp_id}',
                'late_month': late_count,
                'late_id': f'late-{emp_id}',
            })

        # work_type → 필드명 매핑
        cum_field_map = {'normal': 'normal_hours', 'ot': 'ot_hours', 'weekend': 'weekend_hours'}
        cum_id_map = {'normal': f'cum-normal-{emp_id}', 'ot': f'cum-ot-{emp_id}', 'weekend': f'cum-holiday-{emp_id}'}

        # 월 합계 재계산
        total = AttendanceLog.objects.filter(
            emp_id=emp_id, work_dt__year=year, work_dt__month=month
        ).aggregate(res=Sum(cum_field_map[work_type]))['res'] or 0

        # 결과 표시값
        if work_type == 'ot':
            val = float(log.ot_hours or 0)
            display = (str(int(val)) if val % 1 == 0 else str(val)) if val > 0 else ""
        else:
            display = (str(int(num_val)) if is_num and num_val > 0 and num_val % 1 == 0
                       else str(num_val) if is_num and num_val > 0 else "")

        # 누계 재계산
        cum_total = AttendanceLog.objects.filter(
            emp_id=emp_id, work_dt__year=year, work_dt__month__lte=month
        ).aggregate(res=Sum(cum_field_map[work_type]))['res'] or 0

        return JsonResponse({
            'status': 'success',
            'display': display,
            'total': round(float(total), 1),
            'cum': round(float(cum_total), 1),
            'total_id': f'total-{work_type}-{emp_id}',
            'cum_id': cum_id_map[work_type],
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ─── 근태 비고 ────────────────────────────────────────────────────────────────

@erp_permission_required('hr_attendance', 'edit')
def edit_attendance_remark(request, emp_id, year, month):
    filter_queryset_by_scope(
        Employee.objects.all(),
        request.user,
        'hr_attendance',
        action='edit',
        employee_field='self',
        department_field='dept',
    ).get(pk=emp_id)
    obj = AttendanceRemark.objects.filter(emp_id=emp_id, year=year, month=month).first()
    current = obj.remark if obj else ''
    safe_val = html.escape(current)
    return HttpResponse(f'''
        <div id="remark-{emp_id}" style="padding:2px;">
            <textarea name="remark"
                style="width:100%; height:86px; font-size:11px; border:1px solid #86b7fe; border-radius:4px; resize:none; outline:none; overflow-y:auto;"
                hx-post="/hr/attendance/remark/save/{emp_id}/{year}/{month}/"
                hx-trigger="blur, keyup[key==\'Escape\']"
                hx-target="#remark-{emp_id}" hx-swap="outerHTML"
                autofocus>{safe_val}</textarea>
        </div>
    ''')


@erp_permission_required('hr_attendance', 'edit')
@require_POST
def save_attendance_remark(request, emp_id, year, month):
    filter_queryset_by_scope(
        Employee.objects.all(),
        request.user,
        'hr_attendance',
        action='edit',
        employee_field='self',
        department_field='dept',
    ).get(pk=emp_id)
    remark = request.POST.get('remark', '').strip()
    obj, _ = AttendanceRemark.objects.get_or_create(
        emp_id=emp_id, year=year, month=month,
        defaults={'remark': ''}
    )
    obj.remark = remark
    obj.save()
    safe_val = html.escape(remark)
    return HttpResponse(f'''
        <div id="remark-{emp_id}"
             style="cursor:pointer; white-space:pre-wrap; height:90px; overflow-y:auto; padding:2px;"
             hx-get="/hr/attendance/remark/edit/{emp_id}/{year}/{month}/"
             hx-trigger="click"
             hx-target="#remark-{emp_id}" hx-swap="outerHTML">
            {safe_val}
        </div>
    ''')


# ─── 연차 관리 ────────────────────────────────────────────────────────────────

@erp_permission_required('hr_pto', 'view')
def pto_list(request):
    form = PtoSearchForm(request.GET or None)
    selected_year = _period_from_form(form, datetime.today().year)
    can_edit = has_permission(request.user, 'hr_pto', 'edit')

    employees = (
        filter_queryset_by_scope(
            Employee.objects.filter(emp_stat='재직').select_related('dept'),
            request.user,
            'hr_pto',
            employee_field='self',
            department_field='dept',
        )
        .order_by('dept__dept_nm', 'emp_nm')
    )

    # 연차 레코드 일괄 조회 (없으면 get_or_create로 생성)
    leave_map = {}
    for al in AnnualLeave.objects.filter(year=selected_year, emp__in=employees):
        leave_map[al.emp_id] = al

    # 올해 지각 합산 (월별 합산)
    late_year_map = {
        lr['emp_id']: lr
        for lr in LateRecord.objects.filter(year=selected_year, emp__in=employees)
        .values('emp_id').annotate(year_count=Sum('count'))
    }
    # 누적 지각 (선택 연도 이하까지만 합산)
    late_total_map = dict(
        LateRecord.objects.filter(emp__in=employees, year__lte=selected_year)
        .values('emp_id')
        .annotate(total=Sum('count'))
        .values_list('emp_id', 'total')
    )

    # 사용 연차: '연차'=1일, '반차'=0.5일로 집계
    from django.db.models import Case, When, Value, FloatField
    used_map = dict(
        AttendanceLog.objects
        .filter(work_dt__year=selected_year, status_text__in=['연차', '반차'])
        .values('emp_id')
        .annotate(
            used=Sum(Case(
                When(status_text='연차', then=Value(1.0)),
                When(status_text='반차', then=Value(0.5)),
                default=Value(0.0),
                output_field=FloatField(),
            ))
        )
        .values_list('emp_id', 'used')
    )

    pto_data = []
    for emp in employees:
        leave = leave_map.get(emp.emp_id)
        if leave is None:
            if can_edit:
                leave = AnnualLeave.objects.create(emp=emp, year=selected_year, total_days=0)
                leave_map[emp.emp_id] = leave

        total_days = leave.total_days if leave else Decimal('0')
        used_days = Decimal(str(used_map.get(emp.emp_id, 0)))
        remaining_days = total_days - used_days

        lr = late_year_map.get(emp.emp_id)
        pto_data.append({
            'leave_id': leave.pk if leave else '',
            'dept': emp.dept.dept_nm,
            'emp_nm': emp.emp_nm,
            'total_days': total_days,
            'used_days': used_days,
            'remaining_days': remaining_days,
            'late_year': lr['year_count'] if lr else 0,
            'late_total': late_total_map.get(emp.emp_id, 0),
            'emp_id': emp.emp_id,
        })

    return render(request, 'hr/pto.html', {
        'pto_data': pto_data,
        'selected_year': selected_year,
        'form': form,
        'can_edit': can_edit,
    })


@erp_permission_required('hr_salary', 'export')
def print_payslip(request):
    ids = [i.strip() for i in request.GET.get('salary_ids', '').split(',') if i.strip()]
    salaries = filter_queryset_by_scope(
        Salary.objects.select_related('emp__dept').filter(salary_rec_id__in=ids),
        request.user,
        'hr_salary',
        action='export',
        employee_field='emp',
        department_field='emp__dept',
    )

    salary_map = {str(s.salary_rec_id): s for s in salaries}
    ordered = [salary_map[i] for i in ids if i in salary_map]

    for s in ordered:
        s.company_title = s.emp.dept.dept_comp.upper()  # 띄어쓰기 없이 대문자
        year = int(s.salary_month[:4])
        leave = AnnualLeave.objects.filter(emp=s.emp, year=year).first()
        s.leave_used = '-'
        s.leave_remaining = leave.total_days if leave else '-'

    pairs = list(zip_longest(ordered[::2], ordered[1::2], fillvalue=None))
    return render(request, 'hr/print_payslip.html', {'pairs': pairs})


@erp_permission_required('hr_pto', 'edit')
@require_POST
def pto_update(request):
    try:
        data = json.loads(request.body)
        leave_id = data.get('leave_id')
        new_total = data.get('total_days')

        leave = filter_queryset_by_scope(
            AnnualLeave.objects.select_related('emp__dept'),
            request.user,
            'hr_pto',
            action='edit',
            employee_field='emp',
            department_field='emp__dept',
        ).get(pk=leave_id)
        leave.total_days = _parse_decimal(new_total, '사용가능한 연차', min_value=0)
        leave.save()
        return JsonResponse({'status': 'success'})
    except AnnualLeave.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '존재하지 않는 연차 레코드입니다.'}, status=404)
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@erp_permission_required('hr_pto', 'edit')
@require_POST
def late_count_update(request):
    try:
        data = json.loads(request.body)
        emp_id = data.get('emp_id')
        year = data.get('year')
        new_count = max(0, int(data.get('count', 0)))

        filter_queryset_by_scope(
            Employee.objects.all(),
            request.user,
            'hr_pto',
            action='edit',
            employee_field='self',
            department_field='dept',
        ).get(pk=emp_id)

        lr, _ = LateRecord.objects.get_or_create(
            emp_id=emp_id, year=year, defaults={'count': 0}
        )
        lr.count = new_count
        lr.save()

        total = LateRecord.objects.filter(emp_id=emp_id).aggregate(
            t=Sum('count')
        )['t'] or 0
        return JsonResponse({'status': 'success', 'total': total})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
