from django.urls import path
from . import views

app_name = 'tax'

urlpatterns = [
    path('salary-rate/', views.salary_rate_list, name='salary_rate'),
    path('api/salary-rate/create/', views.salary_rate_create, name='salary_rate_create'),
    path('api/salary-rate/update/', views.salary_rate_update, name='salary_rate_update'),
]
