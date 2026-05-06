from .services import has_permission, is_admin_user


class PermissionChecker:
    def __init__(self, user):
        self.user = user

    def can(self, menu_code, action='view'):
        return has_permission(self.user, menu_code, action)

    @property
    def is_erp_admin(self):
        return is_admin_user(self.user)


def erp_permissions(request):
    return {
        'erp_perms': PermissionChecker(request.user),
    }
