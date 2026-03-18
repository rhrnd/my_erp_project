from django.urls import path
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from . import views

app_name = 'hr'

urlpatterns = [
    # 사원 관리
    path('list/', views.hr_list, name='hr_list'),
    path('api/employee/create/', views.employee_create, name='employee_create'),
    path('api/employee/update/', views.employee_update, name='employee_update'),
    path('api/employee/update_status/', views.employee_update_status, name='employee_update_status'),

    # 부서 관리
    path('department/', views.department_list, name='department_list'),
    path('api/department/create/', views.department_create, name='department_create'),
    path('api/department/update/', views.department_update, name='department_update'),

    # 급여 관리
    path('salary/', views.salary_list, name='salary'),
    path('api/salary/update/', views.salary_update, name='salary_update'),

    # 근태 관리
    path('attendance/', views.attendance_list, name='attendance'),
    path('attendance/edit/<int:emp_id>/<int:year>/<int:month>/<int:day>/<str:work_type>/',
         views.edit_attendance_cell, name='edit_attendance_cell'),
    path('attendance/save/<int:emp_id>/<int:year>/<int:month>/<int:day>/<str:work_type>/',
         views.save_attendance_cell, name='save_attendance_cell'),
    path('attendance/cancel/<int:emp_id>/<int:year>/<int:month>/<int:day>/<str:work_type>/',
         views.cancel_attendance_cell, name='cancel_attendance_cell'),

    # 급여명세서 인쇄
    path('payslip/print/', views.print_payslip, name='print_payslip'),

    # 연차 관리
    path('pto/', views.pto_list, name='pto'),
    path('api/pto/update/', views.pto_update, name='pto_update'),
]
