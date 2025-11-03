# reservation/views.py
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from typing import Dict, List

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Lounge, Reservation

# ===== google_sheets.py가 import하는 심볼 =====
SLOT_MINUTES = 30  # 30분 슬롯

def allowed_starts_for_date(target_date) -> List[datetime]:
    """
    해당 날짜에 허용되는 시작시각(TZ-aware) 리스트를 반환.
      - 일요일: 22:00, 22:30, 23:00 (22:00~23:30)
      - 월~목 : 21:30, 22:00, 22:30, 23:00 (21:30~23:30)
      - 금/토 : 없음
    """
    tz = timezone.get_current_timezone()
    weekday = target_date.weekday()  # Mon=0 ... Sun=6
    slots: List[datetime] = []

    def _make_series(start_h: int, start_m: int, end_h: int, end_m: int):
        # zoneinfo에서는 localize가 없으므로 make_aware 사용
        start_naive = datetime.combine(target_date, dtime(start_h, start_m))
        end_naive   = datetime.combine(target_date, dtime(end_h, end_m))
        start_dt = timezone.make_aware(start_naive, tz)
        end_dt   = timezone.make_aware(end_naive, tz)

        cur = start_dt
        while cur < end_dt:
            slots.append(cur)
            cur += timedelta(minutes=SLOT_MINUTES)

    if weekday == 6:          # Sun
        _make_series(22, 0, 23, 30)
    elif 0 <= weekday <= 3:   # Mon~Thu
        _make_series(21, 30, 23, 30)
    else:                     # Fri / Sat
        pass

    return slots
# ===== 여기까지 google_sheets 호환 =====


def _build_slots_for_date(target_date):
    # 화면 표시용: 허용 시작시각 그대로 사용
    return allowed_starts_for_date(target_date)


@login_required
def reservation_page(request):
    """기숙사 라운지 예약 페이지"""
    date_str = request.GET.get("date")
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = timezone.localdate()
    else:
        target_date = timezone.localdate()

    slots = _build_slots_for_date(target_date)
    lounges = Lounge.objects.all().order_by("id")

    # 하루 범위 계산 (마지막 슬롯 시작 + SLOT_MINUTES)
    if slots:
        day_start = slots[0]
        day_end = slots[-1] + timedelta(minutes=SLOT_MINUTES)
    else:
        # 금/토 등 슬롯 없을 때 최소 범위
        day_start = timezone.now()
        day_end = day_start + timedelta(minutes=SLOT_MINUTES)

    reservations = (
        Reservation.objects
        .filter(start_time__gte=day_start, end_time__lte=day_end)
        .select_related("lounge", "user")
    )

    # (lounge_id, start_time) -> reservation
    cell_map: Dict[tuple, Reservation | None] = {}
    for lg in lounges:
        for st in slots:
            cell_map[(lg.id, st)] = None
    for r in reservations:
        cell_map[(r.lounge_id, r.start_time)] = r

    ctx = {
        "target_date": target_date,
        "slots": slots,
        "lounges": lounges,
        "cell_map": cell_map,
    }
    return render(request, "reservation/schedule.html", ctx)


@login_required
def cancel_reservation(request, reservation_id: int):
    """본인 예약 취소 (POST만 허용)"""
    if request.method != "POST":
        messages.error(request, "잘못된 접근입니다.")
        return redirect("reservation_page")

    reservation = get_object_or_404(Reservation, id=reservation_id)

    if reservation.user_id != request.user.id:
        messages.error(request, "본인 예약만 취소할 수 있습니다.")
        return redirect("reservation_page")

    # 필요 시: 시작 시간이 지난 예약 취소 제한 로직
    # if timezone.now() >= reservation.start_time:
    #     messages.error(request, "시작 시간이 지난 예약은 취소할 수 없습니다.")
    #     return redirect("reservation_page")

    reservation.delete()
    messages.success(request, "예약이 취소되었습니다.")

    # 사용자가 보고 있던 날짜 유지
    date_str = reservation.start_time.astimezone(
        timezone.get_current_timezone()
    ).date().isoformat()
    return redirect(f"/reservation/?date={date_str}")
