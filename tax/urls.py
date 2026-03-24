from django.urls import path
from . import views

app_name = 'tax'

urlpatterns = [
    path('salary-rate/', views.salary_rate_list, name='salary_rate'),
    path('salary-formula/', views.salary_formula, name='salary_formula'),
    path('api/salary-rate/update/', views.salary_rate_update, name='salary_rate_update'),
    path('api/salary-rate/auto-calculate/', views.salary_auto_calculate, name='salary_auto_calculate'),
    path('api/salary-formula/update/', views.salary_formula_update, name='salary_formula_update'),
    path('api/salary-formula/apply/', views.salary_formula_apply, name='salary_formula_apply'),
]
