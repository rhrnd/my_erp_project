from django.contrib import admin
from .models import MenuCategory, PermissionItem, UserRole


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    # 상위 메뉴(parent)가 있다면 같이 표시해주는 것이 관리하기 편합니다.
    list_display = ('name', 'code', 'parent')
    search_fields = ('name', 'code')


@admin.register(PermissionItem)
class PermissionItemAdmin(admin.ModelAdmin):
    # 1. 새로운 필드명(scope, can_delete 등)에 맞게 list_display 수정
    list_display = (
        'menu',
        'get_scope_name',      # scope를 읽기 쉽게 표시
        'get_actions_summary',  # 조회/입력/수정/삭제/승인을 한눈에 요약
        'can_export',
        'view_sensitive',
        'can_view_log'
    )

    # 2. auth_level 대신 scope로 필터링 변경
    list_filter = ('menu', 'scope', 'view_sensitive', 'can_export')
    search_fields = ('menu__name',)

    # 'scope'를 관리자 화면에서 한글로 친절하게 보여주는 메서드
    def get_scope_name(self, obj):
        return obj.get_scope_display()
    get_scope_name.short_description = "접근 범위"

    # 권한 상태를 '조/입/수/삭/승' 형태로 요약해서 보여줌 (가로 길이 절약)
    def get_actions_summary(self, obj):
        actions = []
        if obj.can_view:
            actions.append("조회")
        if obj.can_create:
            actions.append("입력")
        if obj.can_edit:
            actions.append("수정")
        if obj.can_delete:
            actions.append("삭제")
        if obj.can_approve:
            actions.append("승인")
        return "/".join(actions) if actions else "권한없음"
    get_actions_summary.short_description = "기본 권한"


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    # 관리자 역할인지 여부(is_admin_role)를 추가하여 시인성 확보
    list_display = ('name', 'is_admin_role', 'description')
    filter_horizontal = ('permissions',)
    search_fields = ('name',)

    def get_queryset(self, request):
        # 쿼리 최적화: select_related는 ForeignKey, prefetch_related는 ManyToMany에 사용
        return super().get_queryset(request).prefetch_related('permissions__menu')
