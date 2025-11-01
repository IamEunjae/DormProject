# reservation/apps.py
from django.apps import AppConfig

class ReservationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reservation"

    def ready(self):
        # 예약 저장/삭제 시 Google Sheets 동기화
        from . import signals  # noqa
