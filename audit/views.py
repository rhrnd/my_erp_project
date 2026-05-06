from django.shortcuts import render
from permission.decorators import erp_permission_required
from .models import AuditLog
from hr.models import Department


@erp_permission_required('audit_log', 'log')
def audit_list(request):
    logs = AuditLog.objects.all().select_related('user')
    dept_map = {str(d.dept_id): d.dept_nm for d in Department.objects.all()}
    return render(request, 'audit/audit_list.html', {'logs': logs, 'dept_map': dept_map})
