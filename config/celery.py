import os
from celery import Celery

# Django 설정 모듈 지정
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# settings.py의 CELERY_ 접두사 설정을 자동으로 읽음
app.config_from_object('django.conf:settings', namespace='CELERY')

# 각 앱의 tasks.py를 자동 탐색
app.autodiscover_tasks()


# ── Windows 실행 참고 ──────────────────────────────────────────────────────────
# Windows에서는 기본 prefork 풀이 지원되지 않으므로 --pool=solo 옵션 필요
#
# Worker 실행:
#   celery -A config worker --pool=solo --loglevel=info
#
# Beat 스케줄러 실행 (별도 터미널):
#   celery -A config beat --loglevel=info
# ─────────────────────────────────────────────────────────────────────────────
