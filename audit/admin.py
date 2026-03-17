from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'category', 'target_name')
    list_filter = ('action', 'category', 'timestamp')
    search_fields = ('user__username', 'target_name', 'changes')
    readonly_fields = ('timestamp', 'user', 'action', 'category', 'target_name', 'changes', 'ip_address')
