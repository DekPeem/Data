"""ตัวอ่านไฟล์ export จากระบบ "AMI" ของ PEA (โครงการติดตั้งระบบมิเตอร์อัจฉริยะ) — ต่างจาก
pea_ingest.py (ไฟล์ HTML แฝงเป็น .xls จากเว็บ AMRWEB) เพราะไฟล์นี้เป็น Excel (.xlsx) แท้ๆ
(ZIP/OOXML) ตรวจพบครั้งแรกจากไฟล์จริงที่ผู้ใช้ส่งมา (ชื่อไฟล์ขึ้นต้นด้วย "kW" หัวรายงานระบุ
"โครงการติดตั้งระบบมิเตอร์อัจฉริยะ (AMI)" รายงาน "ข้อมูลกิโลวัตต์รายเดือน")

โครงสร้างข้อมูลราย 15 นาทีเหมือน pea_ingest ทุกอย่าง (คอลัมน์ Rate A/B/C ตามรอบ TOU
เดียวกัน — ดู pea_ingest.RATE_TO_PERIOD) ต่างแค่ container format (Excel จริง ไม่ใช่ HTML)
ป้ายชื่อหัวรายงาน (มีคำว่า "ไฟฟ้า" ต่อท้าย เช่น "บัญชีผู้ใช้ไฟฟ้า" แทน "บัญชีผู้ใช้ไฟ") และ
ปีในคอลัมน์เวลาเป็นปี พ.ศ. (ต้องแปลงเป็น ค.ศ. ก่อน เพื่อให้ pea_ingest._parse_interval_timestamp
คำนวณวันในสัปดาห์ถูกต้อง)

⚠️ หลักการความปลอดภัยเดียวกับ pea_ingest.py: ไฟล์ดิบมีข้อมูลระบุตัวตนลูกค้า อ่านเฉพาะตัวเลข
การใช้ไฟฟ้าเพื่อคำนวณค่าเฉลี่ยแบบ anonymized เท่านั้น ไม่ควร commit ไฟล์ดิบเข้า repo public
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Union

try:
    import openpyxl
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ต้องติดตั้ง openpyxl ก่อนใช้งาน pea_ami_ingest: pip install openpyxl"
    ) from exc

from .pea_ingest import IntervalReading, _to_float, is_ami_xlsx  # noqa: F401 (re-exported for callers)

# ป้ายชื่อหัวรายงานที่ต้องการอ่าน — คีย์ฝั่งซ้ายคือคำที่ปรากฏจริงในไฟล์ AMI (มี "ไฟฟ้า" ต่อท้าย)
# คีย์ฝั่งขวาคือชื่อมาตรฐานเดียวกับที่ pea_ingest.parse_report_header ใช้ (ไม่มี "ไฟฟ้า" ต่อท้าย)
# แปลงให้ตรงกันเพื่อให้โค้ดฝั่งเรียกใช้ (amr_import.py) ใช้ key เดียวกันได้ไม่ต้องรู้ว่าไฟล์เป็น
# รูปแบบไหน
_LABEL_ALIASES = {
    "บัญชีผู้ใช้ไฟฟ้า": "บัญชีผู้ใช้ไฟ",
    "ชื่อผู้ใช้ไฟฟ้า": "ชื่อผู้ใช้ไฟ",
}
_KNOWN_LABELS = {"บัญชีผู้ใช้ไฟ", "ชื่อผู้ใช้ไฟ", "หมายเลขมิเตอร์", "Tariff", "CT Ratio", "VT Ratio"}

_TIMESTAMP_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})(\s.*)$")


# ปีที่มากกว่านี้ถือว่าเป็น พ.ศ. แน่นอน (ไฟล์ AMR ทั้งหมดเป็นข้อมูลปัจจุบัน ไม่มีทางเป็นปี ค.ศ.
# เกิน 2100 ไปได้จริงๆ) — ไฟล์ AMI ที่เจอมาไม่ได้ใช้ พ.ศ. เสมอไป (บางไฟล์ใช้ ค.ศ. อยู่แล้วเหมือน
# ไฟล์ AMRWEB) เลยต้องเช็คก่อนแปลง ไม่ใช่ลบ 543 ทื่อๆ ทุกไฟล์
_BE_YEAR_THRESHOLD = 2100


def _convert_be_to_ce_timestamp(timestamp: str) -> str:
    """แปลงปี พ.ศ. เป็น ค.ศ. ในสตริง timestamp ดิบ ถ้าเป็น พ.ศ. จริง (เช่น "01/09/2568 00.15"
    -> "01/09/2025 00.15") — ไฟล์ AMI บางไฟล์ใช้ พ.ศ. บางไฟล์ใช้ ค.ศ. อยู่แล้วไม่แน่นอน จึงต้อง
    เช็คตัวเลขปีก่อนแปลง (ดู _BE_YEAR_THRESHOLD) ถ้า parse ไม่ได้ หรือเป็น ค.ศ. อยู่แล้ว
    คืนค่าเดิมโดยไม่แตะต้อง"""

    m = _TIMESTAMP_RE.match(timestamp.strip())
    if not m:
        return timestamp
    day, month, year, rest = m.groups()
    year_int = int(year)
    if year_int <= _BE_YEAR_THRESHOLD:
        return timestamp
    return f"{day}/{month}/{year_int - 543}{rest}"


def parse_ami_report_header(path: Union[str, Path]) -> dict:
    """อ่านหัวรายงาน (บัญชีผู้ใช้ไฟ/ชื่อผู้ใช้ไฟ/หมายเลขมิเตอร์/Tariff/CT-VT Ratio) จากไฟล์
    AMI .xlsx — คืน dict คีย์แบบเดียวกับ pea_ingest.parse_report_header (ดู _LABEL_ALIASES)
    เพื่อให้ผู้เรียกใช้ key เดียวกันได้โดยไม่ต้องรู้ว่าไฟล์เป็นรูปแบบไหน สแกนทุกเซลล์ของทุก
    sheet ในไฟล์ (ไม่ใช่แค่ sheet แรก) แทนการอิงตำแหน่งแถว/คอลัมน์/sheet ตายตัว — พบว่าไฟล์ AMI
    บางไฟล์แบ่งหัวรายงาน/ตารางข้อมูลราย 15 นาที/สรุปท้ายตาราง ไว้คนละ sheet กัน (Sheet1/2/3)
    ไม่ได้รวมอยู่ใน sheet เดียวเสมอไปแบบที่เจอไฟล์แรก"""

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        info: dict = {}
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=30):
                for i, cell in enumerate(row):
                    value = cell.value
                    if not isinstance(value, str):
                        continue
                    cleaned = value.strip().rstrip(":").strip()
                    label = _LABEL_ALIASES.get(cleaned, cleaned)
                    if label not in _KNOWN_LABELS or label in info:
                        continue
                    next_cell = row[i + 1] if i + 1 < len(row) else None
                    next_value = next_cell.value if next_cell is not None else None
                    info[label] = str(next_value).strip() if next_value is not None else ""
        return info
    finally:
        wb.close()


def _find_rate_columns(ws) -> tuple:
    """หาแถวหัวตาราง Rate A/B/C ใน sheet ที่ระบุ — คืน (เลขแถว, {period: col_idx}) หรือ
    (None, {}) ถ้าไม่เจอใน sheet นี้ (ให้ผู้เรียกลอง sheet อื่นต่อ) ถ้า Rate หนึ่งมีมากกว่า 1
    คอลัมน์ (เจอในบางไฟล์ — คอลัมน์ซ้ำค่าเดียวกัน) ใช้คอลัมน์สุดท้ายที่เจอ ซึ่งยังมีค่าอยู่เสมอ

    นับเลขแถวเองด้วย enumerate (ไม่ใช้ cell.row) เพราะโหมด read_only ของ openpyxl คืน
    EmptyCell ให้คอลัมน์แรกของแถวถ้าคอลัมน์นั้นไม่เคยมีค่าเลย ซึ่งไม่มี .row attribute"""

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=40), start=1):
        cells_upper = [(str(c.value).strip().upper() if c.value is not None else "") for c in row]
        if sum(1 for c in cells_upper if "RATE" in c) < 2:
            continue
        rate_col_idx: dict = {}
        for i, c in enumerate(cells_upper):
            for suffix, period in (("A", "P"), ("B", "OP"), ("C", "H")):
                if c == f"RATE {suffix}":
                    rate_col_idx[period] = i
        if len(rate_col_idx) >= 2:
            return row_idx, rate_col_idx
    return None, {}


def parse_ami_interval_report(path: Union[str, Path]) -> List[IntervalReading]:
    """อ่านตารางข้อมูลราย 15 นาทีจากไฟล์ AMI .xlsx — โครงสร้างข้อมูลเหมือน
    pea_ingest.parse_interval_report ทุกอย่าง (คอลัมน์ Rate A/B/C, 1 ค่าต่อแถวต่อคอลัมน์)
    แค่เป็นคอลัมน์ Excel จริงแทน <td> ของ HTML และปีในคอลัมน์เวลาเป็น พ.ศ. (แปลงเป็น ค.ศ.
    ก่อนคืนค่า — ดู _convert_be_to_ce_timestamp)

    ค้นหาตาราง Rate A/B/C ในทุก sheet ของไฟล์ (ไม่ใช่แค่ sheet แรก) — พบไฟล์จริงที่แบ่งหัว
    รายงานไว้ sheet หนึ่ง (Sheet1) แต่ตารางข้อมูลราย 15 นาทีอยู่อีก sheet หนึ่ง (Sheet2)"""

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        target_ws = None
        header_row_idx = None
        rate_col_idx: dict = {}
        for ws in wb.worksheets:
            header_row_idx, rate_col_idx = _find_rate_columns(ws)
            if header_row_idx is not None:
                target_ws = ws
                break

        if target_ws is None:
            raise ValueError(
                f"ไม่พบตารางรายงานราย 15 นาที (header ต้องมีคอลัมน์ Rate A/B/C) ในไฟล์ {path}"
            )

        readings: List[IntervalReading] = []
        for row in target_ws.iter_rows(min_row=header_row_idx + 1):
            timestamp_cell = row[0].value if len(row) else None
            timestamp = str(timestamp_cell).strip() if timestamp_cell is not None else ""
            if not _TIMESTAMP_RE.match(timestamp):
                continue  # ข้ามแถวสรุปท้ายตาราง (กิโลวัตต์สูงสุด/คำอธิบาย/พิมพ์โดย ฯลฯ)
            timestamp = _convert_be_to_ce_timestamp(timestamp)
            for period, col_idx in rate_col_idx.items():
                if col_idx >= len(row):
                    continue
                raw = row[col_idx].value
                val = _to_float(str(raw)) if raw is not None else None
                if val is not None:
                    readings.append(IntervalReading(timestamp=timestamp, period=period, kwh=val))
        return readings
    finally:
        wb.close()
