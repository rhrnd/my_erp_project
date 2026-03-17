from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from .models import AuditLog


@staff_member_required  # 스태프(관리자) 권한이 있는 사람만 접근 가능
def audit_list(request):
    # 최신순으로 로그 조회
    logs = AuditLog.objects.all().select_related('user')
    return render(request, 'audit/audit_list.html', {'logs': logs})
