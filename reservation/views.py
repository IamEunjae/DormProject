# reservation/views.py
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Dict, List
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from .models import Lounge, Reservation

# === 여기가 google_sheets가 임포트하는 심볼입니다 ===
SLOT_MINUTES = 30  # 30분 슬롯

def allowed_starts_for_date(target_date) -> List[datetime]:
    """
    해당 날짜에 허용되는 시작시각(datetime, TZ-aware) 리스트를 반환.
    규칙(페이지 공지 기준):
      - 일요일: 22:00~23:30 (3칸: 22:00, 22:30, 23:00)
      - 월~목: 21:30~23:30 (4칸: 21:30, 22:00, 22:30, 23:00)
      - 금, 토: 예약 불가
    """
    tz = timezone.get_current_timezone()
    weekday = target_date.weekday()  # Mon=0 ... Sun=6

    slots: List[datetime] = []

    def _make_series(start_h: int, start_m: int, end_h: int, end_m: int):
        start_dt = tz.localize(datetime.combine(target_date, time(start_h, start_m)))
        end_dt   = tz.localize(datetime.combine(target_date, time(end_h, end_m)))
        cur = start_dt
        while cur < end_dt:
            slots.append(cur)
            cur += timedelta(minutes=SLOT_MINUTES)

    if weekday == 6:  # Sunday
        # 22:00 ~ 23:30
        _make_series(22, 0, 23, 30)
    elif 0 <= weekday <= 3:  # Mon~Thu
        # 21:30 ~ 23:30
        _make_series(21, 30, 23, 30)
    else:
        # Fri(4), Sat(5): no slots
        pass

    return slots
# === 여기까지 google_sheets 호환 ===


def _build_slots_for_date(target_date):
    """
    화면 표시용 슬롯(월~목 21:30~23:30, 일 22:00~23:30)을 합쳐 사용.
    금/토는 빈 리스트.
    """
    return allowed_starts_for_date(target_date)


@login_required
def reservation_page(request):
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

    if slots:
        day_start = slots[0]
        day_end = slots[-1] + timedelta(minutes=SLOT_MINUTES)
    else:
        day_start = timezone.now()
        day_end = day_start + timedelta(minutes=SLOT_MINUTES)

    reservations = (Reservation.objects
                    .filter(start_time__gte=day_start, end_time__lte=day_end)
                    .select_related("lounge", "user"))

    cell_map: Dict[tuple, Reservation | None] = {}
    for lg in lounges:
        for st in slots:
            cell_map[(lg.id, st)] = None
    for r in reservations:
        cell_map[(r.lounge_id, r.start_time)] = r

    return render(request, "reservation/schedule.html", {
        "target_date": target_date,
        "slots": slots,
        "lounges": lounges,
        "cell_map": cell_map,
    })


@login_required
def cancel_reservation(request, reservation_id: int):
    if request.method != "POST":
        messages.error(request, "잘못된 접근입니다.")
        return redirect("reservation_page")

    reservation = get_object_or_404(Reservation, id=reservation_id)

    if reservation.user_id != request.user.id:
        messages.error(request, "본인 예약만 취소할 수 있습니다.")
        return redirect("reservation_page")

    reservation.delete()
    messages.success(request, "예약이 취소되었습니다.")
    date_str = reservation.start_time.astimezone(
        timezone.get_current_timezone()
    ).date().isoformat()
    return redirect(f"/reservation/?date={date_str}")
