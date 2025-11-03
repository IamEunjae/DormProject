# reservation/views.py
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from typing import Dict, List

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Lounge, Reservation

# ===== google_sheets.py가 import하는 심볼 =====
SLOT_MINUTES = 30  # 30분 슬롯

def allowed_starts_for_date(target_date) -> List[datetime]:
    """
    허용된 시작시각(TZ-aware) 리스트:
      - 일요일: 22:00, 22:30, 23:00 (22:00~23:30)
      - 월~목 : 21:30, 22:00, 22:30, 23:00 (21:30~23:30)
      - 금/토 : 없음
    """
    tz = timezone.get_current_timezone()
    weekday = target_date.weekday()  # Mon=0 ... Sun=6
    slots: List[datetime] = []

    def _make_series(start_h: int, start_m: int, end_h: int, end_m: int):
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

    # 하루 범위 계산
    if slots:
        day_start = slots[0]
        day_end = slots[-1] + timedelta(minutes=SLOT_MINUTES)
    else:
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
def make_reservation(request):
    """
    30분 1칸 예약 생성.
    POST body:
      - lounge_id: int
      - start: '%Y-%m-%d %H:%M:%S' (schedule.html에서 보내는 형식)
    검증:
      - 허용된 슬롯인지
      - 과거 시간이 아닌지
      - 해당 라운지/시간이 비어있는지
      - (옵션) 본인 예약과 겹치지 않는지
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    # 1) 입력 파싱
    lounge_id = request.POST.get("lounge_id")
    start_str = request.POST.get("start")
    if not lounge_id or not start_str:
        messages.error(request, "요청 데이터가 올바르지 않습니다.")
        return redirect("reservation_page")

    try:
        lounge = Lounge.objects.get(id=int(lounge_id))
    except (ValueError, Lounge.DoesNotExist):
        messages.error(request, "라운지를 찾을 수 없습니다.")
        return redirect("reservation_page")

    try:
        # schedule.html에서 '%Y-%m-%d %H:%M:%S'로 전송
        naive = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(naive, tz)
    except Exception:
        messages.error(request, "시작 시간이 올바르지 않습니다.")
        return redirect("reservation_page")

    # 2) 허용 슬롯 검증
    allowed = allowed_starts_for_date(start_dt.date())
    if start_dt not in allowed:
        messages.error(request, "허용된 시간대가 아닙니다.")
        return redirect(f"/reservation/?date={start_dt.date().isoformat()}")

    # 3) 과거 시간 제한 (원치 않으면 주석 처리)
    if start_dt < timezone.now():
        messages.error(request, "이미 지난 시간은 예약할 수 없습니다.")
        return redirect(f"/reservation/?date={start_dt.date().isoformat()}")

    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)

    # 4) 중복/겹침 체크 (라운지)
    exists = Reservation.objects.filter(
        lounge=lounge, start_time=start_dt, end_time=end_dt
    ).exists()
    if exists:
        messages.error(request, "이미 예약된 슬롯입니다.")
        return redirect(f"/reservation/?date={start_dt.date().isoformat()}")

    # 5) 본인 예약 겹침 체크 (동시간대)
    overlap_my = Reservation.objects.filter(
        user=request.user,
        start_time__lt=end_dt,
        end_time__gt=start_dt,
    ).exists()
    if overlap_my:
        messages.error(request, "본인 예약과 시간이 겹칩니다.")
        return redirect(f"/reservation/?date={start_dt.date().isoformat()}")

    # 6) 생성
    Reservation.objects.create(
        user=request.user,
        lounge=lounge,
        start_time=start_dt,
        end_time=end_dt,
    )
    messages.success(request, "예약이 완료되었습니다.")
    return redirect(f"/reservation/?date={start_dt.date().isoformat()}")


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

    reservation.delete()
    messages.success(request, "예약이 취소되었습니다.")

    # 사용자가 보고 있던 날짜 유지
    date_str = reservation.start_time.astimezone(
        timezone.get_current_timezone()
    ).date().isoformat()
    return redirect(f"/reservation/?date={date_str}")
