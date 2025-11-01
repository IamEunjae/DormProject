# reservation/google_sheets.py
from __future__ import annotations

import json
import os
from typing import List, Optional
from datetime import timedelta
import gspread
from google.oauth2.service_account import Credentials

from django.conf import settings
from django.utils import timezone

from .models import Lounge, Reservation
from .views import allowed_starts_for_date, SLOT_MINUTES


# =========================
# Google Sheets 연결 설정
# =========================

# 사용할 스프레드시트 ID (고정)
SPREADSHEET_ID = "1NjCXZH-B6uNp0wMWIWnm_wd-i6n-OyZHP4-G3lxjM1k"

# 사용할 시트(탭) 이름. 시트 탭 이름이 'Sheet1'이면 이 값도 'Sheet1'로 해주세요.
# settings 에서 덮어쓰고 싶다면 settings.GOOGLE_SHEETS_WORKSHEET_NAME 로 지정 가능
WORKSHEET_TITLE = getattr(settings, "GOOGLE_SHEETS_WORKSHEET_NAME", "Sheet1")

# 구글 시트 API 권한 범위
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# 현재 시트 레이아웃(스크린샷 기준)
#  - 제목: A1
#  - 시간: A열
#  - 라운지 A: B열(왼쪽 시작 셀; B~F 병합 가능)
#  - 라운지 G: G열(왼쪽 시작 셀; G~K 병합 가능)
#  - 슬롯 행: 3 ~ 6 (총 4칸; 일요일은 3칸이라도 빈칸으로 채움)
LAYOUT = {
    "title_cell": "A1",
    "time_col": "A",
    "lounge1_col": "B",   # 라운지 A
    "lounge2_col": "G",   # 라운지 G
    "first_row": 3,
    "max_rows": 4,
}


# -------------------------
# 내부 유틸
# -------------------------
def _client() -> gspread.Client:
    """
    서비스계정 키를 다음 둘 중 하나로 제공:
      1) 환경변수 GS_CREDS_JSON (키 내용 전체 JSON 문자열)
      2) 환경변수 GS_CREDS_PATH (키 파일 경로; 예 /home/ubuntu/creds/sheets-sa.json)
    """
    info = os.getenv("GS_CREDS_JSON")
    path = os.getenv("GS_CREDS_PATH")

    if info:
        creds = Credentials.from_service_account_info(json.loads(info), scopes=SCOPES)
        return gspread.authorize(creds)

    if path and os.path.exists(path):
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
        return gspread.authorize(creds)

    raise RuntimeError("서비스계정 키를 GS_CREDS_JSON 또는 GS_CREDS_PATH로 제공하세요.")


def _ws(cli: gspread.Client) -> gspread.Worksheet:
    sh = cli.open_by_key(SPREADSHEET_ID)
    if WORKSHEET_TITLE:
        try:
            return sh.worksheet(WORKSHEET_TITLE)
        except gspread.exceptions.WorksheetNotFound:
            # 탭이 없으면 생성
            return sh.add_worksheet(title=WORKSHEET_TITLE, rows=200, cols=20)
    # 기본 첫 탭
    return sh.sheet1


def _format_people(res: Optional[Reservation]) -> str:
    """
    셀에 넣을 텍스트. 우선 예약 화면에서 입력한 applicant_names를 그대로 사용.
    없으면 user / participants로 "학번 이름"을 조합해 콤마로 연결.
    """
    if not res:
        return ""

    txt = (getattr(res, "applicant_names", "") or "").strip()
    if txt:
        return txt

    people, seen = [], set()
    users = [res.user]
    try:
        users += list(res.participants.all())  # participants M2M 필드가 있다면
    except Exception:
        pass

    for u in users:
        if not u:
            continue
        sn = (getattr(u, "student_number", "") or "").strip()
        nm = (getattr(u, "name", "") or "").strip()
        key = (sn, nm)
        if key in seen:
            continue
        seen.add(key)
        label = f"{sn} {nm}".strip()
        if label:
            people.append(label)
    return ", ".join(people)


# -------------------------
# 공개 함수: 시트 동기화
# -------------------------
def sync_sheet(for_date=None, write_times: bool = False) -> None:
    """
    주어진 날짜(for_date)의 슬롯(30분 간격)에 맞게
    - (옵션) 시간(A열) 텍스트 업데이트
    - 라운지 A(B열), 라운지 G(G열) 셀 값을 '신청자 나열 문자열'로 업데이트

    Args:
        for_date (date | None): 없으면 로컬 오늘 날짜
        write_times (bool): True면 A열 시간 레이블도 쓴다 (최초 셋업/점검에 유용)
    """
    if for_date is None:
        for_date = timezone.localdate()

    cli = _client()
    ws = _ws(cli)

    # 1) 제목 갱신 (반드시 2차원 리스트로!)
    ws.update(LAYOUT["title_cell"], [[f"애인관 라운지 신청 시트  -  {for_date:%Y-%m-%d}"]])

    # 2) 해당 날짜의 허용 슬롯 시작시각 가져오기
    starts = allowed_starts_for_date(for_date)
    tz = timezone.get_current_timezone()

    # 업데이트할 행 인덱스들 (예: 3,4,5,6)
    rows = list(range(LAYOUT["first_row"], LAYOUT["first_row"] + LAYOUT["max_rows"]))

    # 3) (옵션) 시간 레이블 쓰기: A열에 'HH:MM~HH:MM'
    if write_times:
        time_values: List[List[str]] = []
        for i in range(LAYOUT["max_rows"]):
            if i < len(starts):
                st = starts[i].astimezone(tz)
                en = st + timedelta(minutes=SLOT_MINUTES)
                time_values.append([f"{st:%H:%M}~{en:%H:%M}"])
            else:
                time_values.append([""])
        # 예: A3:A6 범위에 2차원 리스트로 업데이트
        ws.update(
            f'{LAYOUT["time_col"]}{rows[0]}:{LAYOUT["time_col"]}{rows[-1]}',
            time_values,
        )

    # 4) 각 라운지 컬럼 값 준비 함수
    def build_col_values(lounge_number: int) -> List[List[str]]:
        try:
            lg = Lounge.objects.get(number=lounge_number)
        except Lounge.DoesNotExist:
            # 라운지가 아직 DB에 없다면 빈칸으로 채움
            return [[""] for _ in range(LAYOUT["max_rows"])]

        col_vals: List[List[str]] = []
        for i in range(LAYOUT["max_rows"]):
            if i < len(starts):
                res = Reservation.objects.filter(lounge=lg, start_time=starts[i]).first()
                col_vals.append([_format_people(res)])
            else:
                col_vals.append([""])
        return col_vals

    # 라운지 A(1), 라운지 G(2) 기준
    lounge_a_values = build_col_values(1)
    lounge_g_values = build_col_values(2)

    # 5) 배치 업데이트 (왼쪽 시작 셀만 쓰면 병합영역 전체에 표시됨)
    ws.batch_update(
        [
            {
                "range": f'{LAYOUT["lounge1_col"]}{rows[0]}:{LAYOUT["lounge1_col"]}{rows[-1]}',
                "values": lounge_a_values,
            },
            {
                "range": f'{LAYOUT["lounge2_col"]}{rows[0]}:{LAYOUT["lounge2_col"]}{rows[-1]}',
                "values": lounge_g_values,
            },
        ]
    )
