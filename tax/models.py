from django.db import models
from simple_history.models import HistoricalRecords


class SalaryRate(models.Model):
    year = models.IntegerField(unique=True, verbose_name="적용 연도")

    # ── 직원 부담 요율 ─────────────────────────────────────────────────────────
    health_ins_rate = models.DecimalField(max_digits=6, decimal_places=3, default=3.545, verbose_name="건강보험요율-직원(%)")
    longterm_care_rate = models.DecimalField(max_digits=6, decimal_places=3, default=12.95, verbose_name="노인장기요양요율(건강보험료 기준 %)")
    pension_rate = models.DecimalField(max_digits=5, decimal_places=2, default=4.50, verbose_name="국민연금요율-직원(%)")
    emp_ins_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.90, verbose_name="고용보험요율-직원(%)")

    # ── 회사 부담 요율 ─────────────────────────────────────────────────────────
    health_ins_rate_comp = models.DecimalField(max_digits=6, decimal_places=3, default=3.545, verbose_name="건강보험요율-회사(%)")
    longterm_care_rate_comp = models.DecimalField(max_digits=6, decimal_places=3, default=12.95, verbose_name="노인장기요양요율-회사(건강보험료 기준 %)")
    pension_rate_comp = models.DecimalField(max_digits=5, decimal_places=2, default=4.50, verbose_name="국민연금요율-회사(%)")
    emp_ins_rate_comp = models.DecimalField(max_digits=5, decimal_places=2, default=0.90, verbose_name="고용보험요율-회사(%)")
    ind_acc_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.73, verbose_name="산재보험요율-회사(%)")

    history = HistoricalRecords()

    class Meta:
        db_table = 'tax_salary_rate'
        ordering = ['-year']
        verbose_name = '연도별 급여 요율'
        verbose_name_plural = '연도별 급여 요율'

    def __str__(self):
        return f"{self.year}년 급여 요율"


class SalaryFormula(models.Model):
    salary_field = models.CharField(max_length=50, unique=True, verbose_name="Salary 필드명")
    display_name = models.CharField(max_length=50, verbose_name="항목명")
    formula_expr = models.CharField(max_length=300, verbose_name="계산식")
    description = models.TextField(blank=True, verbose_name="설명")
    is_active = models.BooleanField(default=True, verbose_name="사용 여부")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="순서")

    class Meta:
        db_table = 'tax_salary_formula'
        ordering = ['order']
        verbose_name = '급여 계산식'
        verbose_name_plural = '급여 계산식'

    def __str__(self):
        return f"{self.display_name} = {self.formula_expr}"
