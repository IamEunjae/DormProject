# reservation/signals.py
from __future__ import annotations

import logging
import threading

from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import Reservation
from .google_sheets import sync_sheet

logger = logging.getLogger(__name__)


def _run_sync(target_date):
    """실제 동기화를 수행하는 함수(스레드에서 호출)."""
    try:
        sync_sheet(for_date=target_date)
        logger.debug("Google Sheet synced for %s", target_date)
    except Exception:
        # 동기화 중 예외가 나도 앱 흐름에는 영향 없도록 안전하게 로깅만
        logger.exception("Failed to sync Google Sheet for %s", target_date)


def _async_sync(target_date):
    """비동기(daemon) 스레드로 시트 동기화 실행."""
    threading.Thread(target=_run_sync, args=(target_date,), daemon=True).start()


@receiver(post_save, sender=Reservation)
def _saved(sender, instance: Reservation, **kwargs):
    # start_time은 aware datetime 가정
    target_date = timezone.localtime(instance.start_time).date()
    # DB 커밋이 확정된 뒤에만 동기화 실행
    transaction.on_commit(lambda: _async_sync(target_date))


@receiver(post_delete, sender=Reservation)
def _deleted(sender, instance: Reservation, **kwargs):
    target_date = timezone.localtime(instance.start_time).date()
    transaction.on_commit(lambda: _async_sync(target_date))
