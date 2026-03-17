from django.db import models


class MenuCategory(models.Model):
    """
    1. 메뉴 카테고리: ERP의 각 대메뉴/소메뉴 단위
    """
    name = models.CharField(max_length=50, verbose_name="메뉴명")
    code = models.CharField(max_length=20, unique=True, verbose_name="메뉴 코드")
    # 확장성: 메뉴의 계층 구조 (대메뉴 > 소메뉴)를 위해 self-referential 추가 가능
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='sub_menus')

    class Meta:
        verbose_name = "1. 메뉴 카테고리"
        verbose_name_plural = "1. 메뉴 카테고리 관리"

    def __str__(self):
        return f"{self.parent.name} > {self.name}" if self.parent else self.name


class PermissionItem(models.Model):
    """
    2. 세부 권한 항목: 특정 메뉴에 대한 [범위 + 행위 + 보안] 정의
    """
    # 데이터 접근 범위 (Row-level Security를 위한 기준)
    SCOPE_CHOICES = [
        ('OWN', '본인 데이터만'),
        ('DEPT', '소속 부서 데이터'),
        ('ALL', '전사 데이터'),
    ]

    menu = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, verbose_name="대상 메뉴")
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default='OWN', verbose_name="접근 범위")

    # 기본 행위 권한
    can_view = models.BooleanField(default=True, verbose_name="조회 권한")
    can_create = models.BooleanField(default=False, verbose_name="입력 권한")
    can_edit = models.BooleanField(default=False, verbose_name="수정 권한")
    can_delete = models.BooleanField(default=False, verbose_name="삭제/비활성 권한")

    # 확장성: 특수 운영 권한
    can_approve = models.BooleanField(default=False, verbose_name="승인/확정 권한")  # 결재 및 마감용
    can_export = models.BooleanField(default=False, verbose_name="엑셀 다운로드")
    view_sensitive = models.BooleanField(default=False, verbose_name="민감 정보(마스킹 해제)")

    # 확장성: 시스템 감사 및 관리자 권한
    can_view_log = models.BooleanField(default=False, verbose_name="작업 로그 조회")  # 누가 수정했는지 확인

    class Meta:
        verbose_name = "2. 세부 권한 항목"
        verbose_name_plural = "2. 세부 권한 항목 설정"
        unique_together = ['menu', 'scope', 'can_view', 'can_create', 'can_edit',
                           'can_delete', 'can_approve', 'can_export', 'view_sensitive', 'can_view_log']

    def __str__(self):
        perms = []
        if self.can_view:
            perms.append("조회")
        if self.can_create:
            perms.append("입력")
        if self.can_edit:
            perms.append("수정")
        if self.can_delete:
            perms.append("삭제")
        if self.can_approve:
            perms.append("승인")

        # 권한이 하나도 없을 경우 처리
        if not perms:
            perm_str = "권한 없음"
        else:
            perm_str = ", ".join(perms)

        return f"[{self.menu.name}] {self.get_scope_display()} - {perm_str} (민감:{'O' if self.view_sensitive else 'X'})"


class UserRole(models.Model):
    """
    3. 사용자 역할: 권한 세트 (예: 인사팀장, 일반사원, 시스템관리자)
    """
    name = models.CharField(max_length=50, verbose_name="역할명")
    description = models.TextField(blank=True, verbose_name="역할 설명")
    permissions = models.ManyToManyField(PermissionItem, verbose_name="포함된 권한들")

    # 확장성: 이 역할이 시스템 관리자 역할인지 여부
    is_admin_role = models.BooleanField(default=False, verbose_name="관리자 역할 여부")

    class Meta:
        verbose_name = "3. 사용자 역할"
        verbose_name_plural = "3. 사용자 역할 관리"

    def __str__(self):
        return self.name
