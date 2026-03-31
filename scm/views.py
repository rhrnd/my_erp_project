from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def ta810_management(request):
    """T/A 810 이력관리"""
    return render(request, 'scm/ta/ta810_management.html', {})

@login_required
def ta810_unsuitable_list(request):
    """T/A 810 부적합품 목록"""
    return render(request, 'scm/ta/ta810_unsuitable_list.html', {})

@login_required
def ta840_management(request):
    """T/A 840 이력관리"""
    return render(request, 'scm/ta/ta840_management.html', {})

@login_required
def ta840_unsuitable_list(request):
    """T/A 840 부적합품 목록"""
    return render(request, 'scm/ta/ta840_unsuitable_list.html', {})

@login_required
def ta870_management(request):
    """T/A 870 이력관리"""
    return render(request, 'scm/ta/ta870_management.html', {})

@login_required
def ta870_unsuitable_list(request):
    """T/A 870 부적합품 목록"""
    return render(request, 'scm/ta/ta870_unsuitable_list.html', {})

@login_required
def ta810_total(request):
    """T/A 810 전체 목록"""
    return render(request, 'scm/ta/ta810_total.html', {'ta_type': '810'})

@login_required
def ta840_total(request):
    """T/A 840 전체 목록"""
    return render(request, 'scm/ta/ta840_total.html', {'ta_type': '840'})

@login_required
def ta870_total(request):
    """T/A 870 전체 목록"""
    return render(request, 'scm/ta/ta870_total.html', {'ta_type': '870'})
