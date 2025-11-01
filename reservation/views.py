# reservation/views.py
from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Lounge, Reservation

SLOT_MINUTES = 30


def allowed_starts_for_date(local_date):
    """
    요일별 허용 시작 시각(aware datetime) 목록을 반환.
    - 일(6): 22:00, 22:30, 23:00 (3칸)
    - 월~목(0~3): 21:30, 22:00, 22:30, 23:00 (4칸)
    - 금(4), 토(5): 예약 불가
    """
    wd = local_date.weekday()
    tz = timezone.get_current_timezone()
    table = {
        6: [(22, 0), (22, 30), (23, 0)],                               # 일
        0: [(21, 30), (22, 0), (22, 30), (23, 0)],                     # 월
        1: [(21, 30), (22, 0), (22, 30), (23, 0)],                     # 화
        2: [(21, 30), (22, 0), (22, 30), (23, 0)],                     # 수
        3: [(21, 30), (22, 0), (22, 30), (23, 0)],                     # 목
        # 4,5는 없음
    }
    starts = []
    for (h, m) in table.get(wd, []):
        naive = datetime.combine(local_date, time(hour=h, minute=m))
        starts.append(timezone.make_aware(naive, tz))
    return starts


@login_required
def schedule(request):
    """일자별 슬롯 그리드 화면."""
    # ?date=YYYY-MM-DD
    try:
        date_str = request.GET.get("date")
        local_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str
            else timezone.localdate()
        )
    except ValueError:
        local_date = timezone.localdate()

    lounges = list(Lounge.objects.order_by("number"))
    slot_starts = allowed_starts_for_date(local_date)

    now = timezone.localtime()
    grid = []
    for start in slot_starts:
        end = start + timedelta(minutes=SLOT_MINUTES)
        row = {
            "label": f"{start:%H:%M} ~ {end:%H:%M}",
            "start_key": start.strftime("%Y%m%d%H%M"),
            "cells": [],
        }

        for lg in lounges:
            res = (
                Reservation.objects.filter(lounge=lg, start_time=start)
                .select_related("user")
                .first()
            )
            cell = {
                "number": lg.number,
                "reserved": bool(res),
                "by": res.applicant_names if res else "",
                "start_key": row["start_key"],
                # 이미 예약됐거나, 슬롯 종료시각이 현재보다 과거면 비활성화
                "disabled": (res is not None) or (end <= now),
            }
            row["cells"].append(cell)

        grid.append(row)

    return render(
        request,
        "reservation/schedule.html",
        {
            "date": local_date,
            "grid": grid,
            "lounges": lounges,
            "no_slots": len(slot_starts) == 0,
        },
    )


@login_required
@require_POST
def reserve_slot(request, number, start_key):
    """슬롯 예약 처리(입력칸 name='names' 문자열을 그대로 저장)."""
    lounge = get_object_or_404(Lounge, number=number)

    # start_key = 'YYYYMMDDHHMM'
    try:
        naive = datetime.strptime(start_key, "%Y%m%d%H%M")
    except ValueError:
        return redirect("reservation:schedule")

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(naive, tz)
    end = start + timedelta(minutes=SLOT_MINUTES)

    # 요일 규칙/과거 슬롯/중복 예약 방지
    if start not in allowed_starts_for_date(start.date()):
        return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")
    if end <= timezone.localtime():
        return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")
    if Reservation.objects.filter(lounge=lounge, start_time=start).exists():
        return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")

    names = (request.POST.get("names") or "").strip()
    Reservation.objects.create(
        user=request.user,
        lounge=lounge,
        start_time=start,
        end_time=end,
        applicant_names=names,  # 화면 입력 그대로 저장
    )

    return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")
