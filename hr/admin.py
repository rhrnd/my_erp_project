from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from simple_history.admin import SimpleHistoryAdmin
from .models import Employee, Department, User


@admin.register(Department)
class DepartmentAdmin(SimpleHistoryAdmin):
    list_display = ('dept_id', 'dept_nm', 'dept_comp', 'in_use')
    search_fields = ('dept_nm',)


@admin.register(Employee)
class EmployeeAdmin(SimpleHistoryAdmin):
    list_display = ('emp_no', 'emp_nm', 'dept', 'emp_pos', 'emp_stat', 'emp_hire')
    search_fields = ('emp_nm', 'emp_no', 'dept__dept_nm')
    list_filter = ('dept', 'emp_stat')

    history_list_display = ['get_change_type', 'get_changed_fields']
    history_list_filter = ['history_type', 'history_user']

    FIELD_LABELS = {
        'dept_id': '부서',
        'emp_nm': '성명',
        'emp_pos': '직급',
        'emp_type': '고용형태',
        'emp_stat': '재직상태',
        'emp_tel': '연락처',
        'emp_add': '주소',
        'emp_hire': '입사일',
        'emp_retire_dt': '퇴사일',
    }

    def get_change_type(self, obj):
        labels = {'+': '생성', '~': '수정', '-': '삭제'}
        return labels.get(obj.history_type, obj.history_type)
    get_change_type.short_description = '유형'

    def get_changed_fields(self, obj):
        if obj.history_type == '+':
            return '신규 사원 등록'
        try:
            delta = obj.diff_against(obj.prev_record)
            parts = []
            for c in delta.changes:
                label = self.FIELD_LABELS.get(c.field, c.field)
                parts.append(f'{label}: {c.old} → {c.new}')
            return ' / '.join(parts) if parts else '-'
        except Exception:
            return '-'
    get_changed_fields.short_description = '변경 내용'

    def history_view(self, request, object_id, extra_context=None):
        extra_context = extra_context or {}
        # history_list_display 각 메서드의 short_description을 dict로 전달
        labels = {}
        for col in self.history_list_display:
            method = getattr(self, col, None)
            labels[col] = getattr(method, 'short_description', col)
        extra_context['history_list_display_labels'] = labels
        return super().history_view(request, object_id, extra_context=extra_context)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # 어드민 상세 화면 설정
    fieldsets = UserAdmin.fieldsets + (
        ('ERP 권한 및 소속', {'fields': ('employee', 'role', 'company', 'is_approved')}),
    )
    # 리스트 화면에서 부서와 실명을 바로 확인
    list_display = ('username', 'get_real_name', 'get_dept', 'company', 'role', 'is_approved')
    # get_real_name / get_dept에서 employee → dept 접근 시 N+1 방지
    list_select_related = ('employee', 'employee__dept', 'role')

    def get_real_name(self, obj):
        return obj.employee.emp_nm if obj.employee else "-"
    get_real_name.short_description = "실명"

    def get_dept(self, obj):
        return obj.employee.dept.dept_nm if obj.employee else "-"
    get_dept.short_description = "부서"
