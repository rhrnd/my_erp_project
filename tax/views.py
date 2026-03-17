from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from decimal import Decimal, InvalidOperation
import json
from .models import SalaryRate


@login_required
def salary_rate_list(request):
    rates = SalaryRate.objects.all()
    return render(request, 'tax/salary_rate.html', {'rates': rates})


@login_required
@require_POST
def salary_rate_create(request):
    try:
        data = json.loads(request.body)
        year = data.get('year')
        if not year:
            return JsonResponse({'status': 'error', 'message': '연도를 입력해주세요.'}, status=400)
        if SalaryRate.objects.filter(year=year).exists():
            return JsonResponse({'status': 'error', 'message': f'{year}년 요율이 이미 존재합니다.'}, status=400)
        SalaryRate.objects.create(year=year)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
def salary_rate_update(request):
    try:
        data = json.loads(request.body)
        rate_id = data.get('rate_id')
        field = data.get('field')
        value = data.get('value')

        ALLOWED_FIELDS = {
            'min_hourly_wage', 'work_hours_monthly',
            'health_ins_rate', 'longterm_care_rate',
            'pension_rate', 'emp_ins_rate',
        }
        if field not in ALLOWED_FIELDS:
            return JsonResponse({'status': 'error', 'message': '수정 불가능한 필드입니다.'}, status=400)

        try:
            value = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            return JsonResponse({'status': 'error', 'message': '올바른 숫자를 입력해주세요.'}, status=400)

        rate = SalaryRate.objects.get(pk=rate_id)
        setattr(rate, field, value)
        rate.save()
        return JsonResponse({'status': 'success'})
    except SalaryRate.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '데이터를 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
