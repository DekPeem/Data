"""ตัวอ่านไฟล์ "รายงานใช้ไฟ - รายเดือน" จากอุปกรณ์วัด/บันทึกข้อมูลไฟฟ้าที่ไม่ใช่ export จากเว็บ
AMRWEB ของ กฟภ. โดยตรง (พบครั้งแรกจากไฟล์จริงที่ผู้ใช้ส่งมา — metadata ของไฟล์ระบุซอฟต์แวร์ที่สร้าง
ว่า "NPO") — เป็นไฟล์ Excel ไบนารีแท้ๆ รูปแบบเก่า (BIFF/.xls แบบ OLE2 Compound File) ไม่ใช่ HTML
แฝงเป็น .xls แบบไฟล์ AMRWEB ปกติ (pea_ingest.py) และไม่ใช่ .xlsx แบบไฟล์ AMI (pea_ami_ingest.py)

โครงสร้างข้อมูลต่างจากไฟล์ AMRWEB/AMI มาก: ไม่มีคอลัมน์ Rate A/B/C แยกช่วงเวลาให้พร้อมใช้เลย มีแค่
กำลังไฟฟ้าขณะนั้น (kW) ทุก 15 นาที ต้อง "คำนวณเอง" ว่าแต่ละจุดข้อมูลตกอยู่ช่วง Peak/Off-Peak/
Holiday ไหน โดยใช้กฎ TOU เดียวกับที่ pea_ingest.py ใช้ (ดู RATE_TO_PERIOD comment ในไฟล์นั้น):
  - วันจันทร์-ศุกร์ 09:00-22:00 -> Peak (P)
  - วันจันทร์-ศุกร์ 22:00-09:00 (ข้ามคืน) -> Off-Peak (OP)
  - วันเสาร์-อาทิตย์ ทั้งวัน -> Holiday (H)

⚠️ ข้อจำกัด: ไม่ได้เช็ควันหยุดนักขัตฤกษ์ (Thai public holiday) เลย — วันหยุดราชการที่ตรงกับวัน
ธรรมดา (จันทร์-ศุกร์) จะถูกคำนวณผิดเป็น Peak/Off-Peak แทนที่จะเป็น Holiday ผลกระทบเล็กน้อยเพราะมี
แค่ไม่กี่วันต่อปี เทียบกับข้อมูลทั้งเดือน (~20 วันทำการ) แต่ควรรู้ไว้ถ้าต้องการความแม่นยำสูง

หัวรายงานไม่มีเลขบัญชีผู้ใช้ไฟ/ชื่อบริษัทเลย (มีแค่หมายเลขเครื่องวัดฯ) — คืนแค่ "หมายเลขมิเตอร์"
ด้วย key เดียวกับ pea_ingest.parse_report_header เพื่อให้ผู้เรียกใช้ต่อได้โดยไม่ต้องรู้ว่าไฟล์เป็น
รูปแบบไหน ส่วนบัญชีผู้ใช้ไฟ/ชื่อบริษัทว่างเปล่าเสมอ (ต้องพึ่งชื่อโฟลเดอร์แทนเหมือนไฟล์ที่อ่านหัว
รายงานไม่ได้เลยกรณีอื่นๆ)
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import List, Union

try:
    import xlrd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ต้องติดตั้ง xlrd ก่อนใช้งาน pea_meter_log_ingest: pip install xlrd"
    ) from exc

from .pea_ingest import IntervalReading

# magic bytes ของ OLE2 Compound File (BIFF .xls แท้) — ต่างจากไฟล์ HTML แฝงเป็น .xls (เริ่มด้วย
# ตัวอักษรอ่านได้) และไฟล์ .xlsx แท้ (ZIP, เริ่มด้วย "PK" — ดู pea_ingest.is_ami_xlsx)
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_TIMESTAMP_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})$")

# ปีที่มากกว่านี้ถือว่าเป็น พ.ศ. แน่นอน (เหมือนหลักการเดียวกับ pea_ami_ingest._BE_YEAR_THRESHOLD)
_BE_YEAR_THRESHOLD = 2100


def is_meter_log_xls(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์นี้เป็นไฟล์ Excel ไบนารีแท้ๆ (.xls รูปแบบเก่า BIFF/OLE2 Compound File) หรือไม่
    — ต่างจากไฟล์ HTML แฝงเป็น .xls แบบ AMRWEB ปกติที่ pea_ingest.py อ่าน (เช็คจาก magic bytes
    ไม่ใช่นามสกุลไฟล์ เหมือนหลักการเดียวกับ pea_ingest.is_ami_xlsx)"""

    try:
        with open(path, "rb") as f:
            return f.read(8) == _OLE2_MAGIC
    except OSError:
        return False


def _period_for(dt: _dt.datetime) -> str:
    """จัดช่วง TOU (P/OP/H) จาก timestamp ตามกฎเดียวกับ pea_ingest.RATE_TO_PERIOD — ดูข้อจำกัด
    เรื่องวันหยุดนักขัตฤกษ์ใน docstring ของโมดูลนี้"""

    if dt.weekday() >= 5:  # 5=เสาร์, 6=อาทิตย์
        return "H"
    if 9 <= dt.hour < 22:
        return "P"
    return "OP"


def parse_meter_log_header(path: Union[str, Path]) -> dict:
    """อ่านหัวรายงาน — มีแค่ "หมายเลขมิเตอร์" ให้เท่านั้น (ไม่มีเลขบัญชี/ชื่อบริษัทในไฟล์นี้เลย)
    คืน dict ว่างถ้าอ่านหัวรายงานไม่ได้ (ไม่ error — ดู pea_ingest.parse_report_header)"""

    wb = xlrd.open_workbook(path)
    sheet = wb.sheet_by_index(0)
    info: dict = {}
    for r in range(min(10, sheet.nrows)):
        cell = str(sheet.cell_value(r, 0) or "").strip()
        if cell.startswith("เครื่องวัดฯ"):
            info["หมายเลขมิเตอร์"] = cell.split(":", 1)[-1].strip()
    return info


def parse_meter_log_interval_report(path: Union[str, Path]) -> List[IntervalReading]:
    """อ่านตารางข้อมูลราย 15 นาทีจากไฟล์รูปแบบนี้ — คอลัมน์ [วันที่/เวลา, kW, (kVAR)] แปลง kW
    (กำลังไฟฟ้าขณะนั้น) เป็น kWh ของช่วง 15 นาทีนั้น (kW x 0.25) แล้วจัดช่วง P/OP/H เองจาก
    timestamp (ดู _period_for) เพราะไฟล์นี้ไม่มีคอลัมน์ Rate A/B/C ให้เหมือนไฟล์ AMRWEB/AMI"""

    wb = xlrd.open_workbook(path)
    sheet = wb.sheet_by_index(0)

    header_row = None
    for r in range(min(10, sheet.nrows)):
        row = [str(sheet.cell_value(r, c) or "").strip() for c in range(sheet.ncols)]
        if any("วันที่" in c for c in row) and any(c.upper() == "KW" for c in row):
            header_row = r
            break

    if header_row is None:
        raise ValueError(
            f'ไม่พบตารางรายงานราย 15 นาที (header ต้องมีคอลัมน์ "วันที่/เวลา" และ "kW") ในไฟล์ {path}'
        )

    readings: List[IntervalReading] = []
    for r in range(header_row + 1, sheet.nrows):
        timestamp_raw = str(sheet.cell_value(r, 0) or "").strip()
        m = _TIMESTAMP_RE.match(timestamp_raw)
        if not m:
            continue  # ข้ามแถวสรุปท้ายตาราง/แถวว่าง

        day, month, year, hour, minute = m.groups()
        year_int = int(year)
        if year_int > _BE_YEAR_THRESHOLD:
            year_int -= 543
        try:
            dt = _dt.datetime(year_int, int(month), int(day), int(hour), int(minute))
        except ValueError:
            continue

        kw_value = sheet.cell_value(r, 1)
        if not isinstance(kw_value, (int, float)):
            continue

        period = _period_for(dt)
        kwh = round(float(kw_value) * 0.25, 4)
        timestamp = dt.strftime("%d/%m/%Y %H.%M")
        readings.append(IntervalReading(timestamp=timestamp, period=period, kwh=kwh))

    return readings
