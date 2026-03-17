"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),

    # 첫 화면: 로그인 페이지
    path('', auth_views.LoginView.as_view(template_name='login.html', redirect_authenticated_user=True), name='login'),
    # 로그인 성공 후 이동할 대시보드 (home.html 필요)
    path('home/', login_required(TemplateView.as_view(template_name='home.html')), name='home'),
    # 로그아웃
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('hr/', include('hr.urls')),
    path('scm/', include('scm.urls')),
    path('audit/', include('audit.urls')),
    path('tax/', include('tax.urls')),
]

# urls.py에 이 코드가 있어야 DEBUG=False에서도 이 폴더를 읽어옵니다.
if not settings.DEBUG:
    from django.views.static import serve
    from django.urls import re_path
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    ]
