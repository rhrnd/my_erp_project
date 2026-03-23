from django.db import models
from simple_history.models import HistoricalRecords


class SalaryRate(models.Model):
    year = models.IntegerField(unique=True, verbose_name="적용 연도")
    min_hourly_wage = models.DecimalField(max_digits=10, decimal_places=0, default=10030, verbose_name="최저시급(원)")
    work_hours_monthly = models.DecimalField(max_digits=5, decimal_places=1, default=209.0, verbose_name="월 통상근무시간(h)")
    health_ins_rate = models.DecimalField(max_digits=6, decimal_places=3, default=3.545, verbose_name="건강보험요율(%)")
    longterm_care_rate = models.DecimalField(max_digits=6, decimal_places=3, default=12.95, verbose_name="노인장기요양요율(건강보험료 기준 %)")
    pension_rate = models.DecimalField(max_digits=5, decimal_places=2, default=4.50, verbose_name="국민연금요율(%)")
    emp_ins_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.90, verbose_name="고용보험요율(%)")

    history = HistoricalRecords()

    class Meta:
        db_table = 'tax_salary_rate'
        ordering = ['-year']
        verbose_name = '연도별 급여 요율'
        verbose_name_plural = '연도별 급여 요율'

    def __str__(self):
        return f"{self.year}년 급여 요율"
