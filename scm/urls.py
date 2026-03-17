from django.urls import path
from . import views

app_name = 'scm'

urlpatterns = [
    # 재고 조회
    path('list/', views.scm_list, name='scm_list'),
    # 자재 등록 (API)
    path('create/', views.material_create, name='material_create'),
    # 재고 내역
    path('history/', views.scm_history, name='scm_history'),
    # 입출고 등록 (API)
    path('inout/create/', views.scm_inout_create, name='scm_inout_create'),
]
