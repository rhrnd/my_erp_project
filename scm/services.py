from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from .models import Inbound, Material, Outbound


# ── 커스텀 예외 ────────────────────────────────────────────────────────────────

class InsufficientStockError(Exception):
    """재고가 출고 수량보다 부족할 때 발생한다."""
    def __init__(self, mat_id, available: Decimal, requested: Decimal):
        self.mat_id = mat_id
        self.available = available
        self.requested = requested
        super().__init__(
            f"재고 부족 (mat_id={mat_id}): 현재 {available}, 요청 {requested}"
        )


# ── 입고 ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def process_inbound(
    mat_id: int,
    qty: Decimal,
    price: Decimal,
    emp_id: int,
    purchase_dt: date,
) -> Inbound:
    """
    입고 처리.
    - Material 행을 select_for_update()로 잠근 뒤 Inbound 레코드를 생성하고
      mat_current_stock을 F() 표현식으로 증가시킨다.
    """
    qty = Decimal(str(qty))
    price = Decimal(str(price))

    mat = Material.objects.select_for_update().get(pk=mat_id)

    inbound = Inbound.objects.create(
        mat=mat,
        emp_id=emp_id,
        in_purchase_dt=purchase_dt,
        in_purchase_price=price,
        in_qty=qty,
    )

    Material.objects.filter(pk=mat_id).update(
        mat_current_stock=F('mat_current_stock') + qty
    )

    return inbound


# ── 출고 ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def process_outbound(
    mat_id: int,
    qty: Decimal,
    emp_id: int,
    out_date: date,
    remark: str = '',
) -> Outbound:
    """
    출고 처리.
    - 재고 부족 시 InsufficientStockError 발생.
    - Outbound 레코드를 생성하고 mat_current_stock을 F() 표현식으로 차감한다.
    """
    qty = Decimal(str(qty))

    mat = Material.objects.select_for_update().get(pk=mat_id)

    if mat.mat_current_stock < qty:
        raise InsufficientStockError(
            mat_id=mat_id,
            available=mat.mat_current_stock,
            requested=qty,
        )

    outbound = Outbound.objects.create(
        mat=mat,
        emp_id=emp_id,
        out_date=out_date,
        out_qty=qty,
        out_remark=remark or None,
    )

    Material.objects.filter(pk=mat_id).update(
        mat_current_stock=F('mat_current_stock') - qty
    )

    return outbound


# ── 특정 시점 재고 조회 ────────────────────────────────────────────────────────

def get_stock_at(mat_id: int, as_of: date) -> Decimal:
    """
    특정 날짜(as_of) 기준 재고를 Inbound/Outbound 합산으로 계산해 반환한다.
    mat_current_stock 캐시를 사용하지 않고 트랜잭션 이력에서 직접 계산한다.
    """
    total_in = (
        Inbound.objects.filter(mat_id=mat_id, in_purchase_dt__lte=as_of)
        .aggregate(total=Sum('in_qty'))['total']
        or Decimal('0')
    )
    total_out = (
        Outbound.objects.filter(mat_id=mat_id, out_date__lte=as_of)
        .aggregate(total=Sum('out_qty'))['total']
        or Decimal('0')
    )
    return total_in - total_out


# ── 재고 캐시 재계산 ──────────────────────────────────────────────────────────

@transaction.atomic
def rebuild_stock_cache(mat_id: int) -> Decimal:
    """
    전체 Inbound/Outbound 합산으로 mat_current_stock을 재계산하고 DB에 저장한다.
    데이터 정합성 점검 또는 수동 복구 시 사용한다.
    """
    total_in = (
        Inbound.objects.filter(mat_id=mat_id)
        .aggregate(total=Sum('in_qty'))['total']
        or Decimal('0')
    )
    total_out = (
        Outbound.objects.filter(mat_id=mat_id)
        .aggregate(total=Sum('out_qty'))['total']
        or Decimal('0')
    )
    correct_stock = total_in - total_out

    Material.objects.filter(pk=mat_id).update(mat_current_stock=correct_stock)

    return correct_stock
