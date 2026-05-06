from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from .services import has_permission


def _wants_json(request):
    accept = request.headers.get('Accept', '')
    return (
        request.path.startswith('/api/')
        or '/api/' in request.path
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in accept
        or request.method not in {'GET', 'HEAD', 'OPTIONS'}
    )


def erp_permission_required(menu_code, action='view'):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if has_permission(request.user, menu_code, action):
                return view_func(request, *args, **kwargs)

            if _wants_json(request):
                return JsonResponse(
                    {'status': 'error', 'message': '해당 작업에 대한 권한이 없습니다.'},
                    status=403,
                )
            raise PermissionDenied('해당 메뉴에 대한 권한이 없습니다.')

        return wrapper

    return decorator
