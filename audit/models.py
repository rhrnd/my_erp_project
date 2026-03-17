from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """
    시스템 내의 주요 작업(작성, 수정, 삭제) 이력을 저장하는 테이블
    """
    ACTION_CHOICES = [
        ('CREATE', '작성'),
        ('UPDATE', '수정'),
        ('DELETE', '삭제'),
        ('LOGIN', '로그인'),
        ('LOGOUT', '로그아웃'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="작업자")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name="작업 유형")

    # 어느 메뉴/기능에서 발생했는지 (예: 인사관리, 재고관리)
    category = models.CharField(max_length=50, verbose_name="카테고리")

    # 변경된 대상에 대한 정보 (예: 홍길동 사원, 강판 A-TYPE)
    target_name = models.CharField(max_length=200, verbose_name="대상 명칭", blank=True, null=True)

    # 변경 상세 내용 (JSON 형태로 저장하여 유연하게 관리)
    changes = models.JSONField(verbose_name="변경 내역", blank=True, null=True)

    ip_address = models.GenericIPAddressField(verbose_name="IP 주소", blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="작업 일시")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "작업 로그"
        verbose_name_plural = "작업 로그 목록"

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.user} - {self.action} {self.target_name}"
