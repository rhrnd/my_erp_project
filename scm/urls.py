from django.urls import path
from . import views

app_name = 'scm'

urlpatterns = [
    # T/A 810
    path('ta/810/management/', views.ta810_management, name='ta810_management'),
    path('ta/810/unsuitable/', views.ta810_unsuitable_list, name='ta810_unsuitable_list'),
    path('ta/810/total/', views.ta810_total, name='ta810_total'),
    # T/A 840
    path('ta/840/management/', views.ta840_management, name='ta840_management'),
    path('ta/840/unsuitable/', views.ta840_unsuitable_list, name='ta840_unsuitable_list'),
    path('ta/840/total/', views.ta840_total, name='ta840_total'),
    # T/A 870
    path('ta/870/management/', views.ta870_management, name='ta870_management'),
    path('ta/870/unsuitable/', views.ta870_unsuitable_list, name='ta870_unsuitable_list'),
    path('ta/870/total/', views.ta870_total, name='ta870_total'),
]
