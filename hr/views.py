import calendar
import html
import json

import holidays as holidays_lib
from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from .forms import SalarySearchForm, PtoSearchForm
from .models import Employee, Department, Salary, AttendanceLog, AnnualLeave
from . import services

# 급여/사원 수정 시 감사 로그에서 제외할 민감 필드
_SENSITIVE_KEYS = frozenset({'emp_rn', 'resident_number'})


def _null(val):
    """빈 문자열을 None으로 정규화한다 (nullable 필드에 빈 문자열이 저장되는 것을 방지)."""
    return val if val not in ('', None) else None


@login_required
def hr_list(request):
    # 실시간 검색(JS)을 사용하므로 서버에서는 전체 목록을 반환합니다.
    employees = Employee.objects.select_related('dept').order_by('-emp_id')
    # 부서 선택을 위해 부서 목록 조회
    departments = Department.objects.filter(in_use=True).order_by('dept_nm')
    return render(request, 'hr/hr_list.html', {'employees': employees, 'departments': departments})


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

        # [AuditLog] 사원 생성 로그 기록 (주민등록번호 등 민감정보 제외)
        audit_data = {k: v for k, v in data.items() if k not in _SENSITIVE_KEYS}
        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            category='인사관리',
            target_name=data['name'],
            changes=audit_data,
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
            category='인사관리',
            target_name=f"{emp.emp_nm} (상태변경)",
            changes={'status': data['status'], 'change_reason': change_reason},
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
        emp = Employee.objects.get(emp_no=data['emp_id'])

        # 프론트엔드에서 dept 값으로 ID(PK)를 전송하므로 pk로 조회해야 합니다.
        if data.get('dept'):
            emp.dept = Department.objects.get(pk=data['dept'])

        emp.emp_nm = data['name']
        emp.emp_pos = _null(data.get('position'))
        emp.emp_tel = _null(data.get('phone'))
        emp.emp_hire = data['join_date']
        emp.emp_add = _null(data.get('address'))
        # 주민등록번호 수정이 필요한 경우 (보안상 주의 필요)
        if 'resident_number' in data and data['resident_number']:
            emp.emp_rn = data['resident_number']
        emp.save()

        # [AuditLog] 정보 수정 로그 기록 (주민등록번호 등 민감정보 제외)
        audit_data = {k: v for k, v in data.items() if k not in _SENSITIVE_KEYS}
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리',
            target_name=emp.emp_nm,
            changes=audit_data,
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
    departments = Department.objects.all().order_by('dept_id')
    return render(request, 'hr/department_list.html', {'departments': departments})


@login_required
@require_POST
def department_create(request):
    """부서 등록 API"""
    try:
        data = json.loads(request.body)
        dept_nm = data.get('name')

        if not dept_nm:
            return JsonResponse({'status': 'error', 'message': '부서명을 입력해주세요.'}, status=400)

        dept = Department.objects.create(
            dept_nm=dept_nm,
            dept_comp=request.user.get_company_display(),  # 로그인한 유저의 소속 회사명으로 설정
            in_use=True
        )

        # [AuditLog] 부서 생성 로그
        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            category='인사관리',
            target_name=dept.dept_nm,
            changes=data,
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
        dept_nm = data.get('name')
        in_use = data.get('in_use')

        dept = Department.objects.get(pk=dept_id)

        # 변경 전 데이터 저장 (로그용)
        old_data = {'name': dept.dept_nm, 'in_use': dept.in_use}

        dept.dept_nm = dept_nm
        dept.in_use = in_use
        dept.save()

        # [AuditLog] 부서 수정 로그
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리',
            target_name=dept.dept_nm,
            changes={'before': old_data, 'after': data},
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

    salaries = Salary.objects.filter(salary_month=target_month).select_related('emp').order_by('emp__emp_no')

    # 4. 합계 계산 (Footer 표시용)
    totals = services.get_salary_totals(target_month)

    # 5. 권한 체크 (템플릿에서 버튼 노출 제어용)
    # 유저의 역할에 '엑셀 다운로드' 권한이 포함되어 있는지 확인합니다.
    can_export = False
    if request.user.role:
        can_export = request.user.role.permissions.filter(
            menu__code='hr_salary',  # 메뉴 카테고리에 등록한 코드와 일치해야 합니다.
            can_export=True
        ).exists()

    context = {
        'form': form,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'salaries': salaries,
        'totals': totals,
        'can_export': can_export,  # 템플릿에서 {% if can_export %} 로 사용
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

        # 수정 허용 필드 화이트리스트 (보안: 클라이언트가 임의 필드를 변조하지 못하도록 제한)
        if field not in services.ALLOWED_SALARY_FIELDS:
            return JsonResponse({'status': 'error', 'message': '수정 불가능한 필드입니다.'}, status=400)

        # 문자열로 들어온 값을 Decimal로 변환 (모델의 save() 메서드 내 연산 오류 방지)
        try:
            value = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            value = Decimal('0')

        # 해당 급여 레코드 조회
        salary = Salary.objects.select_related('emp').get(pk=salary_id)

        # 필드 값 업데이트 (문자열 필드명으로 동적 할당)
        setattr(salary, field, value)
        salary.save()  # 모델의 save() 메서드에서 합계가 자동 계산됨

        # [AuditLog] 급여 수정 로그 기록
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            category='인사관리',
            target_name=f"{salary.emp.emp_nm} ({salary.salary_month} 급여)",
            changes={field: float(value)},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        # 하단 합계 재계산 (페이지 새로고침 없이 실시간 반영을 위함)
        totals = services.get_salary_totals(salary.salary_month)

        # Decimal 객체들을 JSON 직렬화 가능한 float으로 변환
        response_totals = {k: float(v or 0) for k, v in totals.items()}

        return JsonResponse({
            'status': 'success',
            'row_total_gross': float(salary.total_gross_amt),
            'row_total_deduction': float(salary.total_deduction_amt),
            'row_net_pay': float(salary.net_pay_amt),
            'totals': response_totals
        })
    except Salary.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '데이터를 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


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
    kr_holidays = holidays_lib.KR(years=selected_year)
    holiday_days = {}  # { 일(int): 공휴일명(str) }
    for date, name in kr_holidays.items():
        if date.month == selected_month and date.day not in weekend_days:
            holiday_days[date.day] = name

    # 5. [중요] 사원별 근태 데이터 가공 (DB 쿼리)
    attendance_data = []
    # 재직 중인 사원 조회 (부서 정보 포함)
    employees = Employee.objects.filter(emp_stat='재직').select_related('dept').order_by('dept__dept_id', 'emp_no')

    # 해당 월의 전체 근태 기록 조회 (쿼리 최적화)
    logs = AttendanceLog.objects.filter(
        work_dt__year=selected_year,
        work_dt__month=selected_month
    )
    # (사원ID, 일) -> 로그 객체 매핑
    logs_map = {(log.emp_id, log.work_dt.day): log for log in logs}

    # 누계 데이터 계산 (해당 연도 1월 1일부터 선택된 월의 마지막 날까지)
    cumulative_logs = AttendanceLog.objects.filter(
        emp__in=employees,
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

        for d in days_range:
            log = logs_map.get((emp.emp_id, d))
            day_data = {'normal': '', 'ot': '', 'weekend': ''}

            if log:
                # 1. 정상 근무
                if log.normal_hours > 0:
                    val = float(log.normal_hours)
                    day_data['normal'] = str(int(val)) if val % 1 == 0 else str(val)
                    emp_dict['total_normal'] += val

                # 2. OT (상태 텍스트와 시간을 조합하여 표시)
                # DB에 저장된 상태 텍스트(예: 지각, 조퇴 등)가 있으면 가져옴
                s_text = log.status_text.strip() if log.status_text else ""

                # OT 시간 (Decimal -> float 변환)
                val = float(log.ot_hours or 0)

                s_hours = ""
                if val > 0:
                    # 시간 합계 누적
                    emp_dict['total_ot'] += val
                    # 정수/소수점 표현 처리 (예: 2.0 -> "2", 2.5 -> "2.5")
                    s_hours = str(int(val)) if val % 1 == 0 else str(val)

                # 텍스트와 숫자를 공백으로 연결하여 표시 (예: "지각", "2", "지각 2")
                day_data['ot'] = f"{s_text} {s_hours}".strip()

                # 3. 주말/휴일 근무
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
    }

    return render(request, 'hr/attendance.html', context)


# 1. 클릭 시 칸 자체가 입력창으로 변함
@login_required
def edit_attendance_cell(request, emp_id, year, month, day, work_type):
    try:
        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
        log = AttendanceLog.objects.filter(emp_id=emp_id, work_dt=date_str).first()

        # 현재 칸에 들어갈 값 결정 (글자 우선, 없으면 숫자)
        current_val = ""
        if log:
            if work_type == 'ot':
                current_val = log.status_text if log.status_text else (log.ot_hours if log.ot_hours > 0 else "")
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
        bg_class = " bg-weekend" if calendar.weekday(year, month, day) >= 5 else ""
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

        hours = 0
        status = ""
        if log:
            if work_type == 'ot':
                hours = log.ot_hours
                status = log.status_text or ""
            elif work_type == 'normal':
                hours = log.normal_hours
            elif work_type == 'weekend':
                hours = log.weekend_hours

        bg_class = " bg-weekend" if calendar.weekday(year, month, day) >= 5 else ""

        display = html.escape(f"{status} {hours if float(hours) > 0 else ''}".strip())
        return HttpResponse(f'<td class="editable-cell text-center{bg_class}" hx-get="/hr/attendance/edit/{emp_id}/{year}/{month}/{day}/{work_type}/" hx-trigger="click" hx-target="this" hx-swap="outerHTML">{display}</td>')
    except Exception as e:
        bg_class = " bg-weekend" if calendar.weekday(year, month, day) >= 5 else ""
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

        log, _ = AttendanceLog.objects.get_or_create(emp_id=emp_id, work_dt=date_str)

        # 숫자/문자 판별
        is_num = False
        num_val = Decimal(0)
        try:
            num_val = Decimal(user_input)
            is_num = True
        except (InvalidOperation, ValueError):
            is_num = False

        # 필드 매칭 로직
        if work_type == 'ot':
            if is_num:
                log.ot_hours = num_val
                log.status_text = ""
            else:
                log.status_text = user_input
                log.ot_hours = 0
        elif work_type == 'normal':
            log.normal_hours = num_val if is_num else 0
        elif work_type == 'weekend':
            log.weekend_hours = num_val if is_num else 0

        log.save()

        # work_type → 필드명 매핑 (월합계/누계 공용)
        cum_field_map = {'normal': 'normal_hours', 'ot': 'ot_hours', 'weekend': 'weekend_hours'}
        cum_id_map = {'normal': f'cum-normal-{emp_id}', 'ot': f'cum-ot-{emp_id}', 'weekend': f'cum-holiday-{emp_id}'}

        # 월 합계 재계산 (실시간 업데이트용)
        total = AttendanceLog.objects.filter(
            emp_id=emp_id, work_dt__year=year, work_dt__month=month
        ).aggregate(res=Sum(cum_field_map[work_type]))['res'] or 0

        # 결과 HTML 조립 (셀 복구 + 합계 OOB 스왑)
        s_text = log.status_text if log.status_text else ""
        s_hours = ""
        if log.ot_hours > 0:
            val = float(log.ot_hours)
            s_hours = str(int(val)) if val % 1 == 0 else str(val)

        display = html.escape(f"{s_text} {s_hours}".strip())

        if work_type != 'ot':
            display = html.escape(f"{num_val if is_num and num_val > 0 else ''}")

        target_total_id = f"total-{work_type}-{emp_id}"

        # 누계 재계산 (해당 연도 1월부터 선택 월까지의 합계)
        cum_total = AttendanceLog.objects.filter(
            emp_id=emp_id,
            work_dt__year=year,
            work_dt__month__lte=month
        ).aggregate(res=Sum(cum_field_map[work_type]))['res'] or 0

        bg_class = " bg-weekend" if calendar.weekday(year, month, day) >= 5 else ""

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
        bg_class = " bg-weekend" if calendar.weekday(year, month, day) >= 5 else ""
        return HttpResponse(
            f'<td class="editable-cell text-center{bg_class} text-danger" '
            f'title="{html.escape(str(e))}">오류</td>',
            status=500
        )


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

        pto_data.append({
            'leave_id': leave.pk,
            'dept': emp.dept.dept_nm,
            'emp_nm': emp.emp_nm,
            'total_days': total_days,
            'used_days': used_days,
            'remaining_days': remaining_days,
        })

    return render(request, 'hr/pto.html', {
        'pto_data': pto_data,
        'selected_year': selected_year,
        'form': form,
    })


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
