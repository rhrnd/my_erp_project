from functools import lru_cache


ACTION_FIELD_MAP = {
    'view': 'can_view',
    'create': 'can_create',
    'edit': 'can_edit',
    'delete': 'can_delete',
    'approve': 'can_approve',
    'export': 'can_export',
    'sensitive': 'view_sensitive',
    'log': 'can_view_log',
}

SCOPE_ORDER = {
    'OWN': 1,
    'DEPT': 2,
    'ALL': 3,
}


def is_admin_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    role = getattr(user, 'role', None)
    return bool(role and role.is_admin_role)


def get_role(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    return getattr(user, 'role', None)


def get_action_field(action):
    try:
        return ACTION_FIELD_MAP[action]
    except KeyError:
        raise ValueError(f'Unknown permission action: {action}')


def get_permissions(user, menu_code):
    role = get_role(user)
    if not role:
        return []

    return list(
        role.permissions
        .select_related('menu')
        .filter(menu__code=menu_code)
    )


def has_permission(user, menu_code, action='view'):
    if is_admin_user(user):
        return True

    action_field = get_action_field(action)
    return any(
        getattr(permission, action_field, False)
        for permission in get_permissions(user, menu_code)
    )


def get_scope(user, menu_code, action='view'):
    if is_admin_user(user):
        return 'ALL'

    action_field = get_action_field(action)
    scopes = [
        permission.scope
        for permission in get_permissions(user, menu_code)
        if getattr(permission, action_field, False)
    ]
    if not scopes:
        return None

    return max(scopes, key=lambda scope: SCOPE_ORDER.get(scope, 0))


def filter_queryset_by_scope(queryset, user, menu_code, action='view', employee_field='emp', department_field='emp__dept'):
    scope = get_scope(user, menu_code, action)
    if scope in (None, 'ALL'):
        return queryset if scope == 'ALL' else queryset.none()

    employee = getattr(user, 'employee', None)
    if not employee:
        return queryset.none()

    if scope == 'OWN':
        if employee_field == 'self':
            return queryset.filter(pk=employee.pk)
        return queryset.filter(**{employee_field: employee})

    if scope == 'DEPT':
        department = getattr(employee, 'dept', None)
        if not department:
            return queryset.none()
        return queryset.filter(**{department_field: department})

    return queryset.none()


@lru_cache(maxsize=1)
def menu_catalog():
    return {
        'hr_employee': '사원 관리',
        'hr_department': '부서 관리',
        'hr_salary': '급여 관리',
        'hr_attendance': '근태 관리',
        'hr_pto': '연차 관리',
        'tax_salary_rate': '급여 요율 관리',
        'audit_log': '시스템 작업 내역',
        'scm_ta810': 'T/A 810',
        'scm_ta840': 'T/A 840',
        'scm_ta870': 'T/A 870',
    }
