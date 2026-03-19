from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0003_late_record"),
    ]

    operations = [
        # unique_together 제거
        migrations.AlterUniqueTogether(
            name="laterecord",
            unique_together=set(),
        ),
        # LateRecord에 month 추가
        migrations.AddField(
            model_name="laterecord",
            name="month",
            field=models.IntegerField(default=1, verbose_name="월"),
            preserve_default=False,
        ),
        # HistoricalLateRecord에 month 추가
        migrations.AddField(
            model_name="historicallaterecord",
            name="month",
            field=models.IntegerField(default=1, verbose_name="월"),
            preserve_default=False,
        ),
        # 새 unique_together 적용
        migrations.AlterUniqueTogether(
            name="laterecord",
            unique_together={("emp", "year", "month")},
        ),
    ]
