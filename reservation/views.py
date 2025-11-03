# reservation/views.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from .models import Lounge, Reservation

SLOT_MINUTES = 30


def _build_slots_for_date(target_date):
    tz = timezone.get_current_timezone()
    start_dt = tz.localize(datetime.combine(target_date, datetime.min.time()).replace(hour=21, minute=30))
    end_dt = tz.localize(datetime.combine(target_date, datetime.min.time()).replace(hour=23, minute=30))
    slots = []
    cur = start_dt
    while cur < end_dt:
        slots.append(cur)
        cur += timedelta(minutes=SLOT_MINUTES)
    return slots


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

    # 하루 예약 전부 불러오기
    if slots:
        day_start = slots[0]
        day_end = slots[-1] + timedelta(minutes=SLOT_MINUTES)
    else:
        day_start = timezone.now()
        day_end = day_start + timedelta(minutes=SLOT_MINUTES)

    reservations = Reservation.objects.filter(
        start_time__gte=day_start, end_time__lte=day_end
    ).select_related("lounge", "user")

    # (lounge_id, start_time) → reservation
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
    """본인 예약 취소"""
    if request.method != "POST":
        messages.error(request, "잘못된 접근입니다.")
        return redirect("reservation_page")

    reservation = get_object_or_404(Reservation, id=reservation_id)

    if reservation.user_id != request.user.id:
        messages.error(request, "본인 예약만 취소할 수 있습니다.")
        return redirect("reservation_page")

    reservation.delete()
    messages.success(request, "예약이 취소되었습니다.")

    date_str = reservation.start_time.astimezone(timezone.get_current_timezone()).date().isoformat()
    return redirect(f"/reservation/?date={date_str}")
