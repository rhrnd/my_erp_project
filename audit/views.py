from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from .models import AuditLog
from hr.models import Department


@staff_member_required  # 스태프(관리자) 권한이 있는 사람만 접근 가능
def audit_list(request):
    logs = AuditLog.objects.all().select_related('user')
    dept_map = {str(d.dept_id): d.dept_nm for d in Department.objects.all()}
    return render(request, 'audit/audit_list.html', {'logs': logs, 'dept_map': dept_map})
