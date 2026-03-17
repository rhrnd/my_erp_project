from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('list/', views.audit_list, name='audit_list'),
]
