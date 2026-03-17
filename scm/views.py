from audit.models import AuditLog
from .models import Material, Inbound, Outbound, IncomingInspection, TA_management
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
import json
from datetime import datetime
from hr.models import Employee
from django.shortcuts import render
from django.db.models import Prefetch


@login_required
def scm_list(request):
    """재고 조회 페이지"""
    # 사용 중인 자재만 조회, 최신순 정렬
    materials = Material.objects.filter(in_use=True).order_by('-mat_id')
    return render(request, 'scm/scm_list.html', {'materials': materials})


@login_required
@require_POST
def material_create(request):
    """자재(물품) 등록 API"""
    try:
        data = json.loads(request.body)

        material = Material.objects.create(
            mat_code=data['code'],
            mat_nm=data['name'],
            mat_maker=data.get('maker', ''),
            mat_spec=data.get('spec', ''),
            mat_unit=data['unit'],
            mat_current_stock=float(data.get('qty', 0))
        )

        # [AuditLog] 생성 로그 기록
        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            category='재고관리',
            target_name=material.mat_nm,
            changes=data,
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return JsonResponse({'status': 'success', 'mat_id': material.mat_id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def scm_history(request):
    """재고 내역 페이지"""
    # 모달 내 드롭다운을 위한 데이터 조회
    materials = Material.objects.filter(in_use=True).order_by('mat_nm')

    # 로그인한 사용자와 연결된 직원 정보 조회 (User 모델의 OneToOneField 활용)
    # 연결된 사원이 없을 경우(관리자 계정 등) None 처리
    current_emp = getattr(request.user, 'employee', None)

    # 입고 및 출고 내역 조회 (자재 정보 포함)
    inbounds = Inbound.objects.select_related('mat').all()
    outbounds = Outbound.objects.select_related('mat').all()

    history = []

    # 입고 데이터 리스트 변환
    for item in inbounds:
        history.append({
            'mat_id': item.mat.mat_code,
            'mat_nm': item.mat.mat_nm,
            'mat_spec': item.mat.mat_spec,
            'type': '입고',
            'desc': '구매 입고',
            'qty': item.in_qty,
            'date': item.in_purchase_dt,
            'class': 'success'  # 배지 및 텍스트 색상용
        })

    # 출고 데이터 리스트 변환
    for item in outbounds:
        history.append({
            'mat_id': item.mat.mat_code,
            'mat_nm': item.mat.mat_nm,
            'mat_spec': item.mat.mat_spec,
            'type': '출고',
            'desc': '생산 불출',
            'qty': item.out_qty,
            'date': item.out_date if item.out_date else item.out_dtm,
            'class': 'danger'
        })

    # 날짜 기준 내림차순 정렬 (최신순)
    history.sort(key=lambda x: x['date'].date() if isinstance(x['date'], datetime) else x['date'], reverse=True)

    context = {
        'history': history,
        'materials': materials,
        'current_emp': current_emp,
    }
    return render(request, 'scm/scm_history.html', context)


@login_required
def ta810_management(request):
    """T/A 810 이력관리"""
    return render(request, 'ta/ta810_management.html', {})

@login_required
def ta810_unsuitable_list(request):
    """T/A 810 부적합품 목록"""
    return render(request, 'ta/ta810_unsuitable_list.html', {})

@login_required
def ta840_management(request):
    """T/A 840 이력관리"""
    return render(request, 'ta/ta840_management.html', {})

@login_required
def ta840_unsuitable_list(request):
    """T/A 840 부적합품 목록"""
    return render(request, 'ta/ta840_unsuitable_list.html', {})

@login_required
def ta870_management(request):
    """T/A 870 이력관리"""
    return render(request, 'ta/ta870_management.html', {})

@login_required
def ta870_unsuitable_list(request):
    """T/A 870 부적합품 목록"""
    return render(request, 'ta/ta870_unsuitable_list.html', {})


@login_required
@require_POST
def scm_inout_create(request):
    """입고/출고 등록 API"""
    try:
        data = json.loads(request.body)
        io_type = data.get('type')  # 'in' or 'out'
        mat_id = data.get('mat_id')
        qty = float(data.get('qty', 0))

        # 현재 로그인한 사용자의 사원 정보 가져오기
        if not hasattr(request.user, 'employee') or not request.user.employee:
            return JsonResponse({'status': 'error', 'message': '로그인한 계정에 연결된 사원 정보가 없습니다.'}, status=400)

        employee = request.user.employee
        material = Material.objects.get(pk=mat_id)

        if io_type == 'out' and qty > material.mat_current_stock:
            return JsonResponse({'status': 'error', 'message': '제품 수량이 부족합니다.'}, status=400)

        if io_type == 'in':
            # 입고 등록
            Inbound.objects.create(
                mat=material,
                emp=employee,
                in_qty=qty,
                in_purchase_price=float(data.get('price', 0)),
                in_purchase_dt=data.get('date')
            )
            material.mat_current_stock += qty
        else:
            # 출고 등록
            Outbound.objects.create(
                mat=material,
                emp=employee,
                out_qty=qty,
                out_date=data.get('date')
            )
            material.mat_current_stock -= qty

        material.save()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def inspection_table(request):
    inspections = IncomingInspection.objects.prefetch_related(
        Prefetch("lots", queryset=TA_management.objects.order_by("lot_number"))  # ← 변경
    ).order_by("incoming_date")

    table_data = []

    for inspection in inspections:
        lots = list(inspection.lots.all())
        lot_count = len(lots)
        total_qty = sum(lot.quantity for lot in lots)

        for i, lot in enumerate(lots):
            table_data.append({
                "is_first_row": i == 0,
                "rowspan": lot_count,
                "incoming_date": inspection.incoming_date,
                "total_quantity": total_qty,
                "lot_number": lot.lot_number,
                "quantity": lot.quantity,
                "incoming_defect": lot.incoming_defect,
                "defect": lot.defect,
                "rework": lot.rework,
                "pending": lot.pending,
                "process_defect": lot.process_defect,
                "note": lot.note,
            })

    return render(request, "inspection_table.html", {"table_data": table_data})
