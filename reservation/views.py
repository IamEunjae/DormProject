from datetime import datetime, time, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Lounge, Reservation

SLOT_MINUTES = 30

def allowed_starts_for_date(local_date):
    # 일=6: 22:00, 22:30, 23:00 / 월~목=0~3: 21:30 추가 / 금=4, 토=5: 불가
    wd = local_date.weekday()
    tz = timezone.get_current_timezone()
    table = {
        6: [(22,0), (22,30), (23,0)],
        0: [(21,30), (22,0), (22,30), (23,0)],
        1: [(21,30), (22,0), (22,30), (23,0)],
        2: [(21,30), (22,0), (22,30), (23,0)],
        3: [(21,30), (22,0), (22,30), (23,0)],
    }
    starts = []
    for (h,m) in table.get(wd, []):
        naive = datetime.combine(local_date, time(hour=h, minute=m))
        starts.append(timezone.make_aware(naive, tz))
    return starts

@login_required
def schedule(request):
    # ?date=YYYY-MM-DD
    try:
        date_str = request.GET.get('date')
        local_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.localdate()
    except ValueError:
        local_date = timezone.localdate()

    lounges = list(Lounge.objects.order_by('number'))
    slot_starts = allowed_starts_for_date(local_date)
    now = timezone.localtime()
    grid = []
    for start in slot_starts:
        end = start + timedelta(minutes=SLOT_MINUTES)
        row = {"label": f"{start:%H:%M} ~ {end:%H:%M}",
               "start_key": start.strftime("%Y%m%d%H%M"),
               "cells": []}
        for lg in lounges:
            res = Reservation.objects.filter(lounge=lg, start_time=start).first()
            cell = {
                "number": lg.number,
                "reserved": bool(res),
                "by": res.applicant_names if res else "",
                "start_key": row["start_key"],
                "disabled": (res is not None) or (end <= now),
            }
            row["cells"].append(cell)
        grid.append(row)

    return render(request, "reservation/schedule.html", {
        "date": local_date,
        "grid": grid,
        "lounges": lounges,
        "no_slots": (len(slot_starts) == 0),
    })

@require_POST
@login_required
def reserve_slot(request, number, start_key):
    lounge = get_object_or_404(Lounge, number=number)
    from datetime import datetime
    try:
        naive = datetime.strptime(start_key, "%Y%m%d%H%M")
    except ValueError:
        return redirect("reservation:schedule")
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(naive, tz)
    end   = start + timedelta(minutes=SLOT_MINUTES)

    if start not in allowed_starts_for_date(start.date()):  # 요일 규칙
        return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")
    if end <= timezone.localtime():                         # 지난 슬롯 금지
        return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")
    if Reservation.objects.filter(lounge=lounge, start_time=start).exists():
        return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")

    names = (request.POST.get("names") or "").strip()
    Reservation.objects.create(
        user=request.user, lounge=lounge,
        start_time=start, end_time=end,
        applicant_names=names
    )
    return redirect(f"{reverse('reservation:schedule')}?date={start.date()}")
