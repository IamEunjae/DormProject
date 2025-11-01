# reservation/google_sheets.py
from __future__ import annotations
import json
import os
from datetime import datetime, time, timedelta

import gspread
from django.utils import timezone
from django.conf import settings
from google.oauth2.service_account import Credentials

from .models import Lounge, Reservation

# === 사용할 스프레드시트(ID 고정) ===
SPREADSHEET_ID = "1NjCXZH-B6uNp0wMWIWnm_wd-i6n-OyZHP4-G3lxjM1k"
WORKSHEET_TITLE = getattr(settings, "GOOGLE_SHEETS_WORKSHEET_NAME", "")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# === 슬롯 규칙/상수 (views.py에 의존하지 않도록 이 파일에 직접 정의) ===
SLOT_MINUTES = 30  # 30분 고정

def allowed_starts_for_date(local_date):
    """
    요일별 허용 시작 시각(aware datetime) 목록을 반환.
    - 일(6): 22:00, 22:30, 23:00 (3칸)
    - 월~목(0~3): 21:30, 22:00, 22:30, 23:00 (4칸)
    - 금(4), 토(5): 예약 불가(빈 리스트)
    """
    wd = local_date.weekday()
    tz = timezone.get_current_timezone()
    table = {
        6: [(22, 0), (22, 30), (23, 0)],                           # 일
        0: [(21, 30), (22, 0), (22, 30), (23, 0)],                 # 월
        1: [(21, 30), (22, 0), (22, 30), (23, 0)],                 # 화
        2: [(21, 30), (22, 0), (22, 30), (23, 0)],                 # 수
        3: [(21, 30), (22, 0), (22, 30), (23, 0)],                 # 목
        # 4, 5는 없음
    }
    starts = []
    for (h, m) in table.get(wd, []):
        naive = datetime.combine(local_date, time(hour=h, minute=m))
        starts.append(timezone.make_aware(naive, tz))
    return starts

# === 시트 레이아웃: 제목 A1 / 시간 A열 / 라운지1=B열 / 라운지2=G열 / 슬롯행 3~6 ===
LAYOUT = {
    "title_cell": "A1",
    "time_col": "A",
    "lounge1_col": "B",
    "lounge2_col": "G",
    "first_row": 3,
    "max_rows": 4,  # 월~목 4칸, 일요일은 3칸만 쓰고 마지막 1칸은 비움
}

def _client():
    """
    서비스계정 자격증명:
      - GS_CREDS_JSON (JSON 문자열) 또는
      - GS_CREDS_PATH (파일 경로)
    중 하나를 사용.
    """
    if os.getenv("GS_CREDS_JSON"):
        info = json.loads(os.getenv("GS_CREDS_JSON"))
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        path = os.getenv("GS_CREDS_PATH")
        if not path or not os.path.exists(path):
            raise RuntimeError("서비스계정 키를 GS_CREDS_JSON 또는 GS_CREDS_PATH로 제공하세요.")
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return gspread.authorize(creds)

def _ws(cli):
    sh = cli.open_by_key(SPREADSHEET_ID)
    if WORKSHEET_TITLE:
        try:
            return sh.worksheet(WORKSHEET_TITLE)
        except gspread.exceptions.WorksheetNotFound:
            return sh.add_worksheet(title=WORKSHEET_TITLE, rows=100, cols=20)
    return sh.sheet1

def _format_people(res: Reservation | None) -> str:
    """
    셀에 쓸 텍스트:
    1) 화면에서 입력한 applicant_names가 있으면 '그대로' 사용.
    2) 없을 때만 대표 + participants(M2M)를 "학번 이름, ..." 로 조합.
    """
    if not res:
        return ""

    if getattr(res, "applicant_names", None):
        s = res.applicant_names.strip()
        if s:
            return s

    # (보조) M2M participants 조합
    people, seen = [], set()
    users = [res.user]
    try:
        users += list(res.participants.all())
    except Exception:
        pass

    for u in users:
        if not u:
            continue
        key = (getattr(u, "student_number", None), getattr(u, "name", None))
        if key in seen:
            continue
        seen.add(key)

        sn = (getattr(u, "student_number", "") or "").strip()
        nm = (getattr(u, "name", "") or "").strip()
        txt = f"{sn} {nm}".strip() or nm or sn
        if txt:
            people.append(txt)

    return ", ".join(people)

def sync_sheet(for_date=None, write_times=False):
    """
    지정 날짜(기본=오늘)의 현황을 시트에 반영.
    - 제목(A1) 업데이트
    - (옵션) 시간(A3~A6) 업데이트
    - 라운지1(B3~B6), 라운지2(G3~G6) 값 업데이트
    """
    if for_date is None:
        for_date = timezone.localdate()

    cli = _client()
    ws = _ws(cli)

    # 제목
    ws.update(LAYOUT["title_cell"], f"애인관 라운지 신청 시트  -  {for_date:%Y-%m-%d}")

    starts = allowed_starts_for_date(for_date)
    rows = list(range(LAYOUT["first_row"], LAYOUT["first_row"] + LAYOUT["max_rows"]))

    # (선택) 시간 텍스트도 쓰고 싶다면 True로 호출 (초기 1회 세팅에 유용)
    if write_times:
        labels = []
        tz = timezone.get_current_timezone()
        for i in range(LAYOUT["max_rows"]):
            if i < len(starts):
                st = starts[i].astimezone(tz)
                en = st + timedelta(minutes=SLOT_MINUTES)
                labels.append([f"{st:%H:%M}~{en:%H:%M}"])
            else:
                labels.append([""])
        ws.update(
            f'{LAYOUT["time_col"]}{rows[0]}:{LAYOUT["time_col"]}{rows[-1]}',
            labels,
        )

    def col_vals(lounge_no: int):
        try:
            lg = Lounge.objects.get(number=lounge_no)
        except Lounge.DoesNotExist:
            return [[""] for _ in range(LAYOUT["max_rows"])]

        vals = []
        # i < len(starts) 까지만 데이터, 나머지는 빈 칸
        for i in range(LAYOUT["max_rows"]):
            if i < len(starts):
                res = (
                    Reservation.objects
                    .filter(lounge=lg, start_time=starts[i])
                    .select_related("user")
                    .first()
                )
                vals.append([_format_people(res)])
            else:
                vals.append([""])
        return vals

    l1 = col_vals(1)
    l2 = col_vals(2)

    # 병합된 셀의 좌상단(B3/G3 ...)만 채워도 전체 병합 영역에 표시됨
    ws.batch_update([
        {"range": f'{LAYOUT["lounge1_col"]}{rows[0]}:{LAYOUT["lounge1_col"]}{rows[-1]}', "values": l1},
        {"range": f'{LAYOUT["lounge2_col"]}{rows[0]}:{LAYOUT["lounge2_col"]}{rows[-1]}', "values": l2},
    ])
