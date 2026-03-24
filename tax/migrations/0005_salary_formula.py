from django.db import migrations, models


DEFAULT_FORMULAS = [
    ('weekly_holiday_pay',   '주휴수당',       'round(통상시급 * 8 * 4)',            '월 4주 기준. 통상시급 = 통상임금 / 209', 1),
    ('ot_pay',               '시간외수당',     'round(통상시급 * ot시간 * 1.5)',      '잔업시간에 1.5배 가산',                  2),
    ('non_smoke_allowance',  '비흡연수당',     '0',                                   '고정 지급액을 직접 입력하세요.',          3),
    ('func_allowance',       '업무기능수당',   '0',                                   '고정 지급액을 직접 입력하세요.',          4),
    ('comm_allowance',       '통신보조비',     '0',                                   '고정 지급액을 직접 입력하세요.',          5),
    ('special_allowance',    '특별수당',       '0',                                   '고정 지급액을 직접 입력하세요.',          6),
    ('car_allowance',        '자가운전보조금', '0',                                   '고정 지급액을 직접 입력하세요.',          7),
]


def insert_defaults(apps, schema_editor):
    SalaryFormula = apps.get_model('tax', 'SalaryFormula')
    for field, name, expr, desc, order in DEFAULT_FORMULAS:
        SalaryFormula.objects.get_or_create(
            salary_field=field,
            defaults=dict(display_name=name, formula_expr=expr, description=desc, order=order),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('tax', '0004_remove_wage_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='SalaryFormula',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('salary_field', models.CharField(max_length=50, unique=True, verbose_name='Salary 필드명')),
                ('display_name', models.CharField(max_length=50, verbose_name='항목명')),
                ('formula_expr', models.CharField(max_length=300, verbose_name='계산식')),
                ('description', models.TextField(blank=True, verbose_name='설명')),
                ('is_active', models.BooleanField(default=True, verbose_name='사용 여부')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name='순서')),
            ],
            options={
                'verbose_name': '급여 계산식',
                'verbose_name_plural': '급여 계산식',
                'db_table': 'tax_salary_formula',
                'ordering': ['order'],
            },
        ),
        migrations.RunPython(insert_defaults, migrations.RunPython.noop),
    ]
