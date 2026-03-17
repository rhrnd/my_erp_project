from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import SalaryRate


@admin.register(SalaryRate)
class SalaryRateAdmin(SimpleHistoryAdmin):
    list_display = ('year', 'min_hourly_wage', 'health_ins_rate', 'pension_rate', 'emp_ins_rate')
    ordering = ('-year',)
