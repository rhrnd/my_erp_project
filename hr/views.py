import calendar
import html
import json
from functools import lru_cache
from itertools import zip_longest

import holidays as holidays_lib
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Case, When, Value, FloatField
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from audit.models import AuditLog
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


@login_required
def hr_list(request):
    # 실시간 검색(JS)을 사용하므로 서버에서는 전체 목록을 반환합니다.
    employees = Employee.objects.select_related('dept').order_by('emp_hire', 'emp_no')
    departments = Department.objects.filter(in_use=True).order_by('dept_nm')
    companies = Department.objects.filter(in_use=True).values_list(
        'dept_comp', flat=True).distinct().order_by('dept_comp')
    return render(request, 'hr/hr_list.html', {'employees': employees, 'departments': departments, 'companies': companies})


@login_required
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


@login_required
@require_POST
def employee_update_status(request):
    try:
        data = json.loads(request.body)
        # emp_id(PK)가 아닌 emp_no(사번)으로 조회
        emp = Employee.objects.get(emp_no=data['emp_id'])
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


@login_required
@require_POST
def employee_update(request):
    try:
        data = json.loads(request.body)
        emp = Employee.objects.select_related('dept').get(emp_no=data['emp_id'])

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


@login_required
def department_list(request):
    """부서 관리 페이지"""
    departments = Department.objects.all().order_by('dept_comp', 'dept_nm')
    return render(request, 'hr/department_list.html', {'departments': departments})


@login_required
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


@login_required
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


@login_required
def salary_list(request):
    """급여 관리 페이지"""
    # 1. 폼 초기화: GET 데이터가 있으면 바인딩, 없으면 기본값(None)
    # 초기값이 현재 연월로 설정된 폼을 생성합니다.
    form = SalarySearchForm(request.GET or None)

    # 기본값 설정 (현재 시점)
    selected_year = datetime.now().year
    selected_month = datetime.now().month

    # 2. 폼 유효성 검사: 사용자가 조회를 눌렀을 때 선택한 연월 반영
    if form.is_valid():
        selected_year = int(form.cleaned_data['year'])
        selected_month = int(form.cleaned_data['month'])

    # 3. 급여 데이터 조회
    # DB에는 'YYYY-MM' 문자열 형태로 저장되어 있으므로 포맷팅
    target_month = f"{selected_year}-{selected_month:02d}"

    # 해당 월에 급여 데이터가 없는 재직 사원이 있다면, 초기 데이터를 생성해줍니다.
    services.ensure_salary_records(target_month)

    # 근태 O/T 합계를 급여 잔업시간에 자동 반영
    services.sync_ot_from_attendance(target_month, selected_year, selected_month)

    selected_company = request.GET.get('company', '')

    salaries = list(
        Salary.objects.filter(salary_month=target_month)
        .select_related('emp__dept')
        .order_by('emp__emp_no')
    )
    if selected_company:
        salaries = [s for s in salaries if s.emp.dept.dept_comp == selected_company]

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
    totals = services.get_salary_totals(target_month, company=selected_company or None)

    # 해당 연도 요율 (자동계산 안내용)
    from tax.models import SalaryRate
    try:
        salary_rate = SalaryRate.objects.get(year=selected_year)
    except SalaryRate.DoesNotExist:
        salary_rate = None

    # 5. 권한 체크 (템플릿에서 버튼 노출 제어용)
    can_export = False
    if request.user.role:
        can_export = request.user.role.permissions.filter(
            menu__code='hr_salary',
            can_export=True
        ).exists()

    companies = Department.objects.filter(in_use=True).values_list(
        'dept_comp', flat=True).distinct().order_by('dept_comp')

    context = {
        'form': form,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'salaries': salaries,
        'totals': totals,
        'can_export': can_export,
        'companies': companies,
        'selected_company': selected_company,
        'salary_rate': salary_rate,
    }

    return render(request, 'hr/salary.html', context)


@login_required
@require_POST
def salary_update(request):
    """급여 항목 실시간 수정 API"""
    try:
        data = json.loads(request.body)
        salary_id = data.get('salary_id')
        field = data.get('field')
        value = data.get('value', 0)

        if field not in services.ALLOWED_SALARY_FIELDS:
            return JsonResponse({'status': 'error', 'message': '수정 불가능한 필드입니다.'}, status=400)

        try:
            value = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            value = Decimal('0')

        salary = Salary.objects.select_related('emp').get(pk=salary_id)
        setattr(salary, field, value)
        salary.save()

        # 합계를 서비스 레이어에서 계산
        row_totals = services.calculate_salary_totals(salary)

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리/급여관리',
            target_name=f"{salary.emp.emp_nm} ({salary.salary_month} 급여)",
            changes={field: float(value)},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        totals = services.get_salary_totals(salary.salary_month)
        response_totals = {k: float(v or 0) for k, v in totals.items()}

        return JsonResponse({
            'status': 'success',
            'row_total_gross': float(row_totals['total_gross_amt']),
            'row_total_deduction': float(row_totals['total_deduction_amt']),
            'row_net_pay': float(row_totals['net_pay_amt']),
            'totals': response_totals,
        })
    except Salary.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '데이터를 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def attendance_list(request):
    now = datetime.now()

    # 1. 연/월 선택 값 가져오기
    try:
        selected_year = int(request.GET.get('year', now.year))
        selected_month = int(request.GET.get('month', now.month))
    except ValueError:
        selected_year = now.year
        selected_month = now.month

    # 2. 폼 객체 생성 (사용자 선택값 유지)
    form = SalarySearchForm(initial={
        'year': selected_year,
        'month': selected_month
    })

    # 3. 해당 월의 날짜 범위 계산 (예: 1일 ~ 31일)
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    days_range = range(1, last_day + 1)

    # 4. 주말(토, 일) 날짜 리스트 추출 (배경색 처리용)
    weekend_days = []
    for d in days_range:
        if calendar.weekday(selected_year, selected_month, d) >= 5:  # 5:토, 6:일
            weekend_days.append(d)

    # 4-1. 한국 공휴일 추출 (주말 제외 평일 공휴일만)
    kr_holidays = _get_kr_holidays(selected_year)
    holiday_days = {}  # { 일(int): 공휴일명(str) }
    for date, name in kr_holidays.items():
        if date.month == selected_month and date.day not in weekend_days:
            holiday_days[date.day] = name

    # 5. [중요] 사원별 근태 데이터 가공 (DB 쿼리)
    attendance_data = []
    selected_company = request.GET.get('company', '')
    companies = Department.objects.filter(in_use=True).values_list(
        'dept_comp', flat=True).distinct().order_by('dept_comp')

    # 재직 중인 사원 조회 — 한 번만 평가해서 재사용
    emp_qs = Employee.objects.filter(emp_stat='재직').select_related('dept').order_by('dept__dept_id', 'emp_no')
    if selected_company:
        emp_qs = emp_qs.filter(dept__dept_comp=selected_company)
    employees = list(emp_qs)
    employee_ids = [e.emp_id for e in employees]

    # 해당 월의 근태 기록 — 해당 사원만 로드
    logs = AttendanceLog.objects.filter(
        emp_id__in=employee_ids,
        work_dt__year=selected_year,
        work_dt__month=selected_month
    )
    # (사원ID, 일) -> 로그 객체 매핑
    logs_map = {(log.emp_id, log.work_dt.day): log for log in logs}

    # 지각 사이클 계산 (LateRecord 기반 배치 조회)
    from django.db.models import Q
    late_cum_map = dict(
        LateRecord.objects.filter(emp_id__in=employee_ids)
        .filter(Q(year__lt=selected_year) | Q(year=selected_year, month__lte=selected_month))
        .values('emp_id').annotate(total=Sum('count'))
        .values_list('emp_id', 'total')
    )
    prev_year, prev_month = (selected_year, selected_month - 1) if selected_month > 1 else (selected_year - 1, 12)
    late_prev_map = dict(
        LateRecord.objects.filter(emp_id__in=employee_ids)
        .filter(Q(year__lt=prev_year) | Q(year=prev_year, month__lte=prev_month))
        .values('emp_id').annotate(total=Sum('count'))
        .values_list('emp_id', 'total')
    )

    # 누계 데이터 계산 (해당 연도 1월 1일부터 선택된 월의 마지막 날까지)
    cumulative_logs = AttendanceLog.objects.filter(
        emp_id__in=employee_ids,
        work_dt__year=selected_year,
        work_dt__month__lte=selected_month
    ).values('emp_id').annotate(
        cum_normal=Sum('normal_hours'),
        cum_ot=Sum('ot_hours'),
        cum_holiday=Sum('weekend_hours')
    )
    # 계산된 누계 데이터를 emp_id를 키로 하는 딕셔너리로 변환
    cumulative_map = {
        item['emp_id']: {
            'cum_normal': float(item['cum_normal'] or 0),
            'cum_ot': float(item['cum_ot'] or 0),
            'cum_holiday': float(item['cum_holiday'] or 0)
        } for item in cumulative_logs
    }

    # 연차/반차 환산 합계 (연차=1, 반차=0.5)
    _leave_expr = Sum(Case(
        When(status_text='연차', then=Value(1.0)),
        When(status_text='반차', then=Value(0.5)),
        default=Value(0.0),
        output_field=FloatField()
    ))
    leave_monthly_map = dict(
        AttendanceLog.objects.filter(
            emp_id__in=employee_ids,
            work_dt__year=selected_year,
            work_dt__month=selected_month,
            status_text__in=['연차', '반차']
        ).values('emp_id').annotate(total=_leave_expr).values_list('emp_id', 'total')
    )
    leave_cum_map = dict(
        AttendanceLog.objects.filter(
            emp_id__in=employee_ids,
            work_dt__year=selected_year,
            work_dt__month__lte=selected_month,
            status_text__in=['연차', '반차']
        ).values('emp_id').annotate(total=_leave_expr).values_list('emp_id', 'total')
    )

    # 비고 (월별) 배치 조회
    remark_map = dict(
        AttendanceRemark.objects.filter(
            emp_id__in=employee_ids,
            year=selected_year,
            month=selected_month,
        ).values_list('emp_id', 'remark')
    )

    for emp in employees:
        emp_dict = {
            'id': emp.emp_id,
            'dept': emp.dept,
            'name': emp.emp_nm,
            'daily': {},         # { 1: {'normal': 8.0, 'ot': 2.0}, ... }
            'total_normal': 0.0,
            'total_ot': 0.0,
            'total_holiday': 0.0,  # 템플릿 변수명과 일치 (total_weekend -> total_holiday)
            'cum_normal': 0.0,
            'cum_ot': 0.0,         # 누적 OT 근무
            'cum_holiday': 0.0,    # 누적 휴일 근무
        }

        # 해당 사원의 누계 데이터 할당
        emp_cum_data = cumulative_map.get(emp.emp_id, {})
        emp_dict['cum_normal'] = emp_cum_data.get('cum_normal', 0.0)
        emp_dict['cum_ot'] = emp_cum_data.get('cum_ot', 0.0)
        emp_dict['cum_holiday'] = emp_cum_data.get('cum_holiday', 0.0)

        # 연차/반차 환산 합계 (연차=1, 반차=0.5)
        emp_dict['total_leave'] = leave_monthly_map.get(emp.emp_id, 0.0)
        emp_dict['cum_leave'] = leave_cum_map.get(emp.emp_id, 0.0)

        # 월별 비고
        emp_dict['remark'] = remark_map.get(emp.emp_id, '')

        # 지각 사이클 계산
        cumulative = late_cum_map.get(emp.emp_id, 0)
        prev_cumulative = late_prev_map.get(emp.emp_id, 0)
        if cumulative % 3 == 0 and cumulative > 0 and cumulative > prev_cumulative:
            emp_dict['late_cycle'] = 3
        else:
            emp_dict['late_cycle'] = cumulative % 3
        emp_dict['late_cumulative'] = cumulative
        emp_dict['late_deductions'] = cumulative // 3

        for d in days_range:
            log = logs_map.get((emp.emp_id, d))
            day_data = {'normal': '', 'status': '', 'ot': '', 'weekend': ''}

            if log:
                # 1. 정상 근무
                if log.normal_hours > 0:
                    val = float(log.normal_hours)
                    day_data['normal'] = str(int(val)) if val % 1 == 0 else str(val)
                    emp_dict['total_normal'] += val

                # 2. 상태 텍스트 (연차/지각/조퇴/반차 등)
                day_data['status'] = log.status_text.strip() if log.status_text else ""

                # 3. OT (숫자만)
                val = float(log.ot_hours or 0)
                if val > 0:
                    emp_dict['total_ot'] += val
                    day_data['ot'] = str(int(val)) if val % 1 == 0 else str(val)

                # 4. 주말/휴일 근무
                if log.weekend_hours > 0:
                    val = float(log.weekend_hours)
                    day_data['weekend'] = str(int(val)) if val % 1 == 0 else str(val)
                    emp_dict['total_holiday'] += val

            emp_dict['daily'][d] = day_data

        attendance_data.append(emp_dict)

    # 6. 템플릿 전달
    context = {
        'form': form,
        'selected_year': selected_year,
        'selected_month': str(selected_month).zfill(2),
        'days_range': days_range,        # 1~31 헤더 생성용
        'weekend_days': weekend_days,    # 주말 배경색용
        'holiday_days': holiday_days,    # 공휴일 { 일: 이름 }
        'attendance_data': attendance_data,  # 본문 데이터
        'companies': companies,
        'selected_company': selected_company,
    }

    return render(request, 'hr/attendance.html', context)


# 1. 클릭 시 칸 자체가 입력창으로 변함
@login_required
def edit_attendance_cell(request, emp_id, year, month, day, work_type):
    try:
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


@login_required
def cancel_attendance_cell(request, emp_id, year, month, day, work_type):
    try:
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
@login_required
@require_POST
def save_attendance_cell(request, emp_id, year, month, day, work_type):
    try:
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

        # 상태 칸 — 연차/반차 합계/누계 OOB 업데이트 포함
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

            display = html.escape(user_input)
            return HttpResponse(f'''
        <td class="editable-cell text-center{bg_class}"
            hx-get="/hr/attendance/edit/{emp_id}/{year}/{month}/{day}/{work_type}/"
            hx-trigger="click" hx-target="this" hx-swap="outerHTML">
            {display}
        </td>
        <td id="total-status-{emp_id}" hx-swap-oob="true" class="fw-bold">
            {monthly_leave:.1f}
        </td>
        <td id="cum-status-{emp_id}" hx-swap-oob="true" class="fw-bold">
            {cum_leave:.1f}
        </td>
        ''')

        # work_type → 필드명 매핑 (월합계/누계 공용)
        cum_field_map = {'normal': 'normal_hours', 'ot': 'ot_hours', 'weekend': 'weekend_hours'}
        cum_id_map = {'normal': f'cum-normal-{emp_id}', 'ot': f'cum-ot-{emp_id}', 'weekend': f'cum-holiday-{emp_id}'}

        # 월 합계 재계산
        total = AttendanceLog.objects.filter(
            emp_id=emp_id, work_dt__year=year, work_dt__month=month
        ).aggregate(res=Sum(cum_field_map[work_type]))['res'] or 0

        # 결과 표시값
        if work_type == 'ot':
            val = float(log.ot_hours or 0)
            display = html.escape(str(int(val)) if val % 1 == 0 else str(val)) if val > 0 else ""
        else:
            display = html.escape(str(num_val) if is_num and num_val > 0 else "")

        target_total_id = f"total-{work_type}-{emp_id}"

        # 누계 재계산 (해당 연도 1월부터 선택 월까지의 합계)
        cum_total = AttendanceLog.objects.filter(
            emp_id=emp_id,
            work_dt__year=year,
            work_dt__month__lte=month
        ).aggregate(res=Sum(cum_field_map[work_type]))['res'] or 0

        response_html = f'''
        <td class="editable-cell text-center{bg_class}"
            hx-get="/hr/attendance/edit/{emp_id}/{year}/{month}/{day}/{work_type}/"
            hx-trigger="click" hx-target="this" hx-swap="outerHTML">
            {display}
        </td>
        <td id="{target_total_id}" hx-swap-oob="true" class="fw-bold">
            {float(total):.1f}
        </td>
        <td id="{cum_id_map[work_type]}" hx-swap-oob="true" class="fw-bold">
            {float(cum_total):.1f}
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


# ─── 근태 비고 ────────────────────────────────────────────────────────────────

@login_required
def edit_attendance_remark(request, emp_id, year, month):
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


@login_required
@require_POST
def save_attendance_remark(request, emp_id, year, month):
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

@login_required
def pto_list(request):
    form = PtoSearchForm(request.GET or None)
    selected_year = int(request.GET.get('year', datetime.today().year))

    employees = (
        Employee.objects
        .filter(emp_stat='재직')
        .select_related('dept')
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
    # 전체 누적 지각 (연도 무관 전체 합산)
    late_total_map = dict(
        LateRecord.objects.filter(emp__in=employees)
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
            leave = AnnualLeave.objects.create(emp=emp, year=selected_year, total_days=0)
            leave_map[emp.emp_id] = leave

        total_days = leave.total_days
        used_days = Decimal(str(used_map.get(emp.emp_id, 0)))
        remaining_days = total_days - used_days

        lr = late_year_map.get(emp.emp_id)
        pto_data.append({
            'leave_id': leave.pk,
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
    })


@login_required
def print_payslip(request):
    if not request.user.is_staff:
        return redirect('/')

    ids = [i.strip() for i in request.GET.get('salary_ids', '').split(',') if i.strip()]
    salaries = Salary.objects.select_related('emp__dept').filter(salary_rec_id__in=ids)

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


@login_required
@require_POST
def pto_update(request):
    try:
        data = json.loads(request.body)
        leave_id = data.get('leave_id')
        new_total = data.get('total_days')

        leave = AnnualLeave.objects.get(pk=leave_id)
        leave.total_days = Decimal(str(new_total))
        leave.save()
        return JsonResponse({'status': 'success'})
    except AnnualLeave.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '존재하지 않는 연차 레코드입니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
def late_count_update(request):
    try:
        data = json.loads(request.body)
        emp_id = data.get('emp_id')
        year = data.get('year')
        new_count = max(0, int(data.get('count', 0)))

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
