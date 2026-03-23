import logging

from celery import shared_task

from .models import Material
from . import services

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='scm.rebuild_all_stock_cache')
def rebuild_all_stock_cache(self):
    """
    모든 Material의 재고 캐시를 트랜잭션 이력 합산으로 재계산한다.

    불일치가 발견된 항목은 WARNING 로그로 기록한다.

    Beat 예약 예시 (admin > Periodic Tasks):
        Task : scm.rebuild_all_stock_cache
        Cron : 매일 새벽 2시
    """
    mat_ids = list(Material.objects.values_list('mat_id', flat=True))
    fixed = 0
    errors = 0

    for mat_id in mat_ids:
        try:
            mat = Material.objects.get(pk=mat_id)
            before = mat.mat_current_stock
            after = services.rebuild_stock_cache(mat_id)

            if before != after:
                logger.warning(
                    "[재고 불일치 수정] mat_id=%s | %s → %s",
                    mat_id, before, after
                )
                fixed += 1

        except Exception as exc:
            logger.error("[재고 재계산 오류] mat_id=%s | %s", mat_id, exc)
            errors += 1

    result = f"완료: 총 {len(mat_ids)}개 중 {fixed}개 수정, {errors}개 오류"
    logger.info("[rebuild_all_stock_cache] %s", result)
    return result
