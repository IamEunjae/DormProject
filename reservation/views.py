# reservation/views.py
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from typing import List, Tuple

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from .models import Lounge, Reservation

# --- (선택) 구글시트 연동 함수가 있으면 사용, 없으면 무시 ---
try:
    # 새 훅(아래 2번 참고)
    from .google_sheets import append_reservation_with_applicants as _append_with
except Exception:
    _append_with = None
try:
    # 기존 프로젝트에 있을 수 있는 기본 append
    from .google_sheets import append_reservation as _append_basic
except Exception:
    _append_basic = None

SLOT_MINUTES = 30  # 30분 슬롯


def allowed_starts_for_date(target_date) -> List[datetime]:
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


def _build_slots_for_date(target_date):
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

    slots: List[datetime] = _build_slots_for_date(target_date)
    lounges = list(Lounge.objects.all().order_by("id"))

    # 표시 라벨: 라운지 A / 라운지 G
    for idx, lg in enumerate(lounges):
        label = "A" if idx == 0 else ("G" if idx == 1 else chr(ord("A") + idx))
        setattr(lg, "display_label", f"라운지 {label}")

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

    slot_index = {st: i for i, st in enumerate(slots)}
    lounge_index = {lg.id: j for j, lg in enumerate(lounges)}

    grid: List[List[Reservation | None]] = [
        [None for _ in lounges] for _ in slots
    ]
    for r in reservations:
        i = slot_index.get(r.start_time)
        j = lounge_index.get(r.lounge_id)
        if i is not None and j is not None:
            grid[i][j] = r

    rows: List[Tuple[datetime, datetime, list]] = []
    for i, st in enumerate(slots):
        end = st + timedelta(minutes=SLOT_MINUTES)
        pairs = [(lounges[j], grid[i][j]) for j in range(len(lounges))]
        rows.append((st, end, pairs))

    # 인사말 표기
    try:
        account_id = request.user.get_username()
    except Exception:
        account_id = str(request.user)

    full_name = ""
    if hasattr(request.user, "get_full_name"):
        try:
            full_name = request.user.get_full_name() or ""
        except Exception:
            full_name = ""
    display_name = full_name or account_id

    ctx = {
        "target_date": target_date,
        "rows": rows,
        "lounges": lounges,
        "display_name": display_name,
        "account_id": account_id,
    }
    return render(request, "reservation/schedule.html", ctx)


@login_required
def make_reservation(request):
    """
    30분 1칸 예약 생성.
    POST:
      - lounge_id: int
      - start: '%Y-%m-%d %H:%M:%S'
      - applicant: '이름1, 이름2, ...' (선택)
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    lounge_id = request.POST.get("lounge_id")
    start_str = request.POST.get("start")
    applicants_raw = (request.POST.get("applicant") or "").strip()

    if not lounge_id or not start_str:
        messages.error(request, "요청 데이터가 올바르지 않습니다.")
        return redirect("reservation_page")

    # 라운지
    try:
        lounge = Lounge.objects.get(id=int(lounge_id))
    except (ValueError, Lounge.DoesNotExist):
        messages.error(request, "라운지를 찾을 수 없습니다.")
        return redirect("reservation_page")

    # 시작 시간
    try:
        naive = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(naive, tz)
    except Exception:
        messages.error(request, "시작 시간이 올바르지 않습니다.")
        return redirect("reservation_page")

    # 허용/과거 체크
    allowed = allowed_starts_for_date(start_dt.date())
    if start_dt not in allowed:
        messages.error(request, "허용된 시간대가 아닙니다.")
        return redirect(f"{reverse('reservation_page')}?date={start_dt.date().isoformat()}")
    if start_dt < timezone.now():
        messages.error(request, "이미 지난 시간은 예약할 수 없습니다.")
        return redirect(f"{reverse('reservation_page')}?date={start_dt.date().isoformat()}")

    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)

    # 중복/겹침 체크
    if Reservation.objects.filter(lounge=lounge, start_time=start_dt, end_time=end_dt).exists():
        messages.error(request, "이미 예약된 슬롯입니다.")
        return redirect(f"{reverse('reservation_page')}?date={start_dt.date().isoformat()}")

    if Reservation.objects.filter(
        user=request.user, start_time__lt=end_dt, end_time__gt=start_dt
    ).exists():
        messages.error(request, "본인 예약과 시간이 겹칩니다.")
        return redirect(f"{reverse('reservation_page')}?date={start_dt.date().isoformat()}")

    # ---- 신청자 이름들 파싱/정리 ----
    # 쉼표(,), 전각쉼표(，), 가운뎃점(、) 모두 구분자로 취급
    import re
    names = [n.strip() for n in re.split(r"[,\u3001\uFF0C]+", applicants_raw) if n.strip()]
    # 중복 제거(순서 유지)
    seen = set()
    deduped = []
    for n in names:
        if n not in seen:
            deduped.append(n)
            seen.add(n)
    applicants_str = ", ".join(deduped) if deduped else ""

    # ---- 예약 생성 ----
    reservation = Reservation(
        user=request.user,
        lounge=lounge,
        start_time=start_dt,
        end_time=end_dt,
    )
    # 모델에 어떤 필드가 있는지 프로젝트마다 다를 수 있어 안전하게 처리
    if hasattr(reservation, "applicant_names"):
        reservation.applicant_names = applicants_str
    elif hasattr(reservation, "applicants"):
        reservation.applicants = applicants_str
    elif hasattr(reservation, "applicant"):
        reservation.applicant = applicants_str
    reservation.save()

    # ---- 구글 시트 반영 (있으면 호출) ----
    try:
        if _append_with is not None:
            _append_with(reservation, applicants_str)
        elif _append_basic is not None:
            # 기존 함수가 reservation만 받는 구조라면 이걸로도 반영될 수 있음
            _append_basic(reservation)
    except Exception:
        # 시트 실패해도 웹 예약은 성공으로 유지
        pass

    messages.success(request, "예약이 완료되었습니다.")
    return redirect(f"{reverse('reservation_page')}?date={start_dt.date().isoformat()}")


@login_required
def cancel_reservation(request, reservation_id: int):
    if request.method != "POST":
        messages.error(request, "잘못된 접근입니다.")
        return redirect("reservation_page")

    reservation = get_object_or_404(Reservation, id=reservation_id)
    if reservation.user_id != request.user.id:
        messages.error(request, "본인 예약만 취소할 수 있습니다.")
        return redirect("reservation_page")

    date_str = reservation.start_time.astimezone(
        timezone.get_current_timezone()
    ).date().isoformat()

    reservation.delete()
    messages.success(request, "예약이 취소되었습니다.")
    return redirect(f"{reverse('reservation_page')}?date={date_str}")
