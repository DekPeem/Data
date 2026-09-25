"""ตัวอ่านไฟล์ export จากระบบ PEA (รูปแบบ HTML table ที่นามสกุลไฟล์เป็น .xls)

รองรับ 2 รูปแบบไฟล์หลัก:

1. "แบบฟอร์มการอ่านหน่วยมิเตอร์ AMR" (register history)
   ตารางประวัติค่ามิเตอร์สะสมรายเดือน (Rate A/B/C ตามรอบ Reset) — ใช้คำนวณ
   พลังงานไฟฟ้า (kWh) และกำลังไฟฟ้าสูงสุด (kW) ต่อเดือน แยกตามช่วง P/OP/H
   โดยหา "ผลต่าง" ของค่าสะสมระหว่างเดือน (สำหรับพลังงาน) และอ่านค่าตรงๆ
   (สำหรับกำลังไฟฟ้าสูงสุด) แล้วคูณด้วยตัวคูณมิเตอร์ (CT ratio x VT ratio)

2. "รายงานข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" (15-minute interval report)
   ข้อมูลละเอียดราย 15 นาที แยกคอลัมน์ RATE A / RATE B / RATE C

⚠️ หมายเหตุสำคัญ: ไฟล์ดิบจาก PEA มีข้อมูลระบุตัวตนลูกค้า (ชื่อบริษัท,
เลขบัญชีผู้ใช้ไฟ, เลขมิเตอร์) — โมดูลนี้อ่านเฉพาะตัวเลขการใช้ไฟฟ้าเพื่อนำไป
คำนวณ "ค่าเฉลี่ย" แบบไม่ระบุตัวตน (anonymized aggregate) เท่านั้น ไม่ควร
commit ไฟล์ดิบเหล่านี้เข้า repository ที่เป็น public
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ต้องติดตั้ง beautifulsoup4 และ lxml ก่อนใช้งาน pea_ingest: "
        "pip install beautifulsoup4 lxml"
    ) from exc

# ช่วงเวลาตามระบบอัตรา TOU ของ PEA:
#   RATE A = ช่วง Peak (P)      -> วันทำการ 09:00-22:00
#   RATE B = ช่วง Off-Peak (OP) -> วันทำการ 22:00-09:00
#   RATE C = ช่วง Holiday (H)   -> วันหยุด/วันเสาร์-อาทิตย์ ตลอดวัน
RATE_TO_PERIOD = {"a": "P", "b": "OP", "c": "H"}


def _read_html(path: Union[str, Path]) -> BeautifulSoup:
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return BeautifulSoup(content, "lxml")


def is_ami_xlsx(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์นี้เป็น Excel (.xlsx) แท้หรือไม่ (ไม่ใช่ HTML แฝงเป็น .xls แบบไฟล์ AMRWEB
    ปกติที่ฟังก์ชันอื่นๆ ในโมดูลนี้อ่าน) — เช็คจาก magic bytes ของไฟล์ (.xlsx เป็น ZIP archive
    เริ่มด้วย "PK") ไม่ใช่เช็คจากนามสกุลไฟล์ เพราะไฟล์ AMRWEB ก็ตั้งชื่อ .xls เหมือนกันแต่เนื้อหา
    จริงเป็น HTML ล้วนๆ — ใช้แยกแยะไฟล์จากระบบ "AMI" ของ PEA (ดู pea_ami_ingest.py)"""

    try:
        with open(path, "rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def _to_float(text: str) -> Optional[float]:
    text = (text or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class MonthlyRegisterReading:
    """แถวดิบ 1 แถวจากตาราง "ประวัติการอ่านหน่วยมิเตอร์ AMR" (ค่าสะสม ยังไม่คูณตัวคูณ)"""

    month: str  # เช่น "08/2026"
    kwh_total_raw: float
    kwh_a_raw: float
    kwh_b_raw: float
    kwh_c_raw: float
    demand_a_raw: float
    demand_b_raw: float
    demand_c_raw: float


@dataclass(frozen=True)
class MonthlyPeriodProfile:
    """โปรไฟล์ P/OP/H ของเดือนหนึ่ง (คูณตัวคูณมิเตอร์แล้ว = ค่าจริง)"""

    month: str
    demand_kw: dict  # {"P": .., "OP": .., "H": ..}
    energy_kwh: dict  # {"P": .., "OP": .., "H": ..}


def parse_register_history(path: Union[str, Path]) -> List[MonthlyRegisterReading]:
    """อ่านตาราง "แบบฟอร์มการอ่านหน่วยมิเตอร์ AMR" (ประวัติหลายเดือน)

    คืนค่าดิบ (ยังไม่คูณตัวคูณมิเตอร์ CT/VT) เรียงตามเดือน
    """

    soup = _read_html(path)
    tables = soup.find_all("table")

    history_table = None
    for t in tables:
        first_row = t.find("tr")
        if first_row is None:
            continue
        header_cells = [c.get_text(strip=True) for c in first_row.find_all(["td", "th"])]
        if header_cells and header_cells[0] == "No.":
            history_table = t
            break

    if history_table is None:
        raise ValueError(
            f"ไม่พบตารางประวัติการอ่านหน่วยมิเตอร์ (header ขึ้นต้นด้วย 'No.') ในไฟล์ {path}"
        )

    rows = history_table.find_all("tr")
    readings: List[MonthlyRegisterReading] = []
    for r in rows[1:]:
        cells = [c.get_text(strip=True) for c in r.find_all("td")]
        if len(cells) < 11 or not cells[1]:
            continue
        # ลำดับคอลัมน์: No., เดือน/ปี, ครั้งที่Reset, วันที่Reset, 111, 010, 020, 030, 050, 060, 070, ...
        month = cells[1]
        kwh_total = _to_float(cells[4])
        kwh_a = _to_float(cells[5])
        kwh_b = _to_float(cells[6])
        kwh_c = _to_float(cells[7])
        demand_a = _to_float(cells[8])
        demand_b = _to_float(cells[9])
        demand_c = _to_float(cells[10])
        if None in (kwh_total, kwh_a, kwh_b, kwh_c, demand_a, demand_b, demand_c):
            continue
        readings.append(
            MonthlyRegisterReading(
                month=month,
                kwh_total_raw=kwh_total,
                kwh_a_raw=kwh_a,
                kwh_b_raw=kwh_b,
                kwh_c_raw=kwh_c,
                demand_a_raw=demand_a,
                demand_b_raw=demand_b,
                demand_c_raw=demand_c,
            )
        )
    return readings


def compute_monthly_profiles(
    readings: List[MonthlyRegisterReading], multiplier: float
) -> List[MonthlyPeriodProfile]:
    """แปลงค่าดิบ (ต่อเนื่อง, สะสม) เป็นโปรไฟล์ P/OP/H รายเดือน (คูณตัวคูณมิเตอร์แล้ว)

    พลังงาน (energy) = ผลต่างของค่าสะสมระหว่างเดือนถัดไปกับเดือนก่อนหน้า x ตัวคูณ
    กำลังไฟฟ้าสูงสุด (demand) = ค่าที่อ่านได้ในเดือนนั้นตรงๆ x ตัวคูณ (เป็นค่าพีคที่เกิดขึ้นในรอบนั้นอยู่แล้ว)

    ต้องมีข้อมูลอย่างน้อย 2 เดือนติดกันจึงจะคำนวณพลังงานของเดือนที่ 2 เป็นต้นไปได้
    (เดือนแรกสุดไม่มีเดือนก่อนหน้าให้หักลบ จึงถูกข้าม)
    """

    profiles: List[MonthlyPeriodProfile] = []
    for prev, curr in zip(readings, readings[1:]):
        energy_kwh = {
            "P": (curr.kwh_a_raw - prev.kwh_a_raw) * multiplier,
            "OP": (curr.kwh_b_raw - prev.kwh_b_raw) * multiplier,
            "H": (curr.kwh_c_raw - prev.kwh_c_raw) * multiplier,
        }
        demand_kw = {
            "P": curr.demand_a_raw * multiplier,
            "OP": curr.demand_b_raw * multiplier,
            "H": curr.demand_c_raw * multiplier,
        }
        profiles.append(MonthlyPeriodProfile(month=curr.month, demand_kw=demand_kw, energy_kwh=energy_kwh))
    return profiles


def average_profiles(profiles: List[MonthlyPeriodProfile]) -> dict:
    """เฉลี่ยโปรไฟล์รายเดือนหลายๆ เดือน เป็นโปรไฟล์ตัวแทน (representative) เดียว

    คืนค่า dict: {"demand_kw": {...}, "energy_kwh": {...}, "n_months": int}
    ใช้ค่าเฉลี่ย (mean) ของกำลังไฟฟ้าสูงสุดและพลังงานไฟฟ้า แยกตาม P/OP/H
    """

    if not profiles:
        raise ValueError("ไม่มีข้อมูลโปรไฟล์รายเดือนให้เฉลี่ย")

    n = len(profiles)
    demand_kw = {
        period: round(sum(p.demand_kw[period] for p in profiles) / n, 2) for period in ("P", "OP", "H")
    }
    energy_kwh = {
        period: round(sum(p.energy_kwh[period] for p in profiles) / n, 2) for period in ("P", "OP", "H")
    }
    return {"demand_kw": demand_kw, "energy_kwh": energy_kwh, "n_months": n}


@dataclass(frozen=True)
class IntervalReading:
    """1 จุดข้อมูลจากรายงาน "กิโลวัตต์ชั่วโมงแบบช่วงเวลา" (เช่น ราย 15 นาที)

    ค่า kwh ในไฟล์นี้เป็นค่าจริงอยู่แล้ว (คูณตัวคูณมิเตอร์มาให้แล้วโดยระบบ PEA)
    ต่างจาก MonthlyRegisterReading ที่เป็นค่าดิบต้องคูณตัวคูณเอง
    """

    timestamp: str  # เช่น "01/08/2026 00.15" (คงรูปแบบดิบไว้ ไม่ parse เป็น datetime)
    period: str  # "P" | "OP" | "H"
    kwh: float


def parse_report_header(path: Union[str, Path]) -> dict:
    """อ่าน "หัวรายงาน" (เลขบัญชี/ชื่อผู้ใช้ไฟ/เลขมิเตอร์/Tariff/CT-VT Ratio) จากไฟล์ export ของ
    PEA — อยู่ในตารางแยกต่างหากก่อนตารางข้อมูลราย 15 นาที รูปแบบเป็นคู่ <td class='detail'>ป้ายชื่อ
    :</td><td>ค่า</td> เรียงกันในแถวเดียวกัน (ยืนยันจากไฟล์จริงที่ผู้ใช้ส่งมา)

    คืน dict คีย์เป็นป้ายชื่อภาษาไทย/อังกฤษตามที่ปรากฏในไฟล์ตรงๆ (เช่น "บัญชีผู้ใช้ไฟ",
    "ชื่อผู้ใช้ไฟ", "หมายเลขมิเตอร์", "Tariff", "CT Ratio", "VT Ratio") — คืน dict ว่างถ้าไฟล์
    ไม่มีตารางหัวรายงานนี้เลย (เช่นไฟล์รูปแบบเก่า/ไฟล์ทดสอบ) ไม่ error

    ถ้าไฟล์เป็น Excel (.xlsx) แท้ (ไม่ใช่ HTML แฝงเป็น .xls แบบปกติ — เช่นไฟล์จากระบบ "AMI"
    ของ PEA) จะส่งต่อให้ pea_ami_ingest.parse_ami_report_header อ่านแทนโดยอัตโนมัติ ถ้าเป็น
    Excel ไบนารีแท้ๆ รูปแบบเก่า (.xls จริง ไม่ใช่ HTML แฝง — เช่นรายงานจากอุปกรณ์วัด/บันทึกข้อมูล
    ที่ไม่ใช่ AMRWEB) จะส่งต่อให้ pea_meter_log_ingest.parse_meter_log_header แทน (import แบบ
    lazy กันปัญหา circular import เพราะทั้งสองโมดูลก็ import จากไฟล์นี้เหมือนกัน)
    """

    if is_ami_xlsx(path):
        from .pea_ami_ingest import parse_ami_report_header

        return parse_ami_report_header(path)

    from .pea_meter_log_ingest import is_meter_log_xls

    if is_meter_log_xls(path):
        from .pea_meter_log_ingest import parse_meter_log_header

        return parse_meter_log_header(path)

    soup = _read_html(path)
    info: dict = {}
    for label_td in soup.find_all("td", class_="detail"):
        label = label_td.get_text(strip=True).rstrip(":").strip()
        if not label:
            continue
        value_td = label_td.find_next_sibling("td")
        info[label] = value_td.get_text(strip=True) if value_td else ""
    return info


def parse_interval_report(path: Union[str, Path]) -> List[IntervalReading]:
    """อ่านตาราง "รายงานข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" (เช่น ราย 15 นาที)

    หาแถวหัวตารางที่มีคอลัมน์ RATE A / RATE B / RATE C (ไม่สนตัวพิมพ์เล็ก-ใหญ่)
    แล้วอ่านทุกแถวที่มีค่า ยกเว้นแถวสรุปผลรวมท้ายตาราง (เช่น "ผลรวมทั้งหมด")

    ถ้าไฟล์เป็น Excel (.xlsx) แท้ (ดู is_ami_xlsx) จะส่งต่อให้
    pea_ami_ingest.parse_ami_interval_report อ่านแทนโดยอัตโนมัติ ถ้าเป็น Excel ไบนารีแท้ๆ
    รูปแบบเก่า (.xls จริง — ดู pea_meter_log_ingest.is_meter_log_xls) จะส่งต่อให้
    pea_meter_log_ingest.parse_meter_log_interval_report แทน (ไฟล์แบบนี้ไม่มีคอลัมน์ Rate
    A/B/C ให้เลย ต้องคำนวณช่วง P/OP/H เองจาก timestamp)
    """

    if is_ami_xlsx(path):
        from .pea_ami_ingest import parse_ami_interval_report

        return parse_ami_interval_report(path)

    from .pea_meter_log_ingest import is_meter_log_xls

    if is_meter_log_xls(path):
        from .pea_meter_log_ingest import parse_meter_log_interval_report

        return parse_meter_log_interval_report(path)

    soup = _read_html(path)
    tables = soup.find_all("table")

    interval_table = None
    for t in tables:
        first_row = t.find("tr")
        if first_row is None:
            continue
        header_cells = [c.get_text(strip=True).upper() for c in first_row.find_all(["td", "th"])]
        if sum(1 for h in header_cells if "RATE" in h) >= 2:
            interval_table = t
            break

    if interval_table is None:
        raise ValueError(
            f"ไม่พบตารางรายงานราย 15 นาที (header ต้องมีคอลัมน์ RATE A/B/C) ในไฟล์ {path}"
        )

    rows = interval_table.find_all("tr")
    readings: List[IntervalReading] = []
    for r in rows[1:]:
        cells = [c.get_text(strip=True) for c in r.find_all("td")]
        if len(cells) < 4:
            continue
        timestamp = cells[0]
        if not timestamp or timestamp.startswith("ผลรวม"):
            continue  # ข้ามแถวสรุปผลรวมท้ายตาราง
        rate_a, rate_b, rate_c = cells[1], cells[2], cells[3]
        for period, raw in (("P", rate_a), ("OP", rate_b), ("H", rate_c)):
            val = _to_float(raw)
            if val is not None:
                readings.append(IntervalReading(timestamp=timestamp, period=period, kwh=val))
    return readings


def aggregate_interval_readings(
    readings: List[IntervalReading], interval_minutes: float = 15, label: str = "interval"
) -> MonthlyPeriodProfile:
    """รวมข้อมูลราย 15 นาที เป็นโปรไฟล์เดียว (พลังงานรวม + กำลังไฟฟ้าสูงสุด แยกตาม P/OP/H)

    พลังงาน (energy) = ผลรวมของทุกช่วงในคาบนั้น (kWh เป็นค่าจริงอยู่แล้วในไฟล์นี้)
    กำลังไฟฟ้าสูงสุด (demand) = ค่าสูงสุดที่พบในคาบนั้น เปลี่ยนหน่วยจาก kWh/ช่วงเวลา
    เป็น kW โดยคูณด้วย (60 / interval_minutes) เช่น ราย 15 นาที คูณด้วย 4
    """

    energy_kwh = {"P": 0.0, "OP": 0.0, "H": 0.0}
    peak_interval_kwh = {"P": 0.0, "OP": 0.0, "H": 0.0}
    for r in readings:
        energy_kwh[r.period] += r.kwh
        if r.kwh > peak_interval_kwh[r.period]:
            peak_interval_kwh[r.period] = r.kwh

    factor = 60.0 / interval_minutes
    demand_kw = {p: round(v * factor, 2) for p, v in peak_interval_kwh.items()}
    energy_kwh = {p: round(v, 2) for p, v in energy_kwh.items()}
    return MonthlyPeriodProfile(month=label, demand_kw=demand_kw, energy_kwh=energy_kwh)


# รหัสวันในสัปดาห์ ตาม datetime.weekday() (0 = จันทร์ ... 6 = อาทิตย์) — ใช้เป็น key ของ
# เส้นโค้งการใช้ไฟฟ้ารายวัน แยกตามวัน (ดู compute_hourly_curve) "all" = เฉลี่ยรวมทุกวัน
DAY_TYPE_CODES = ("all", "mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_TO_CODE = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_interval_timestamp(timestamp: str) -> Optional[_dt.datetime]:
    """แปลง timestamp ดิบจากรายงานราย 15 นาที (เช่น "01/08/2026 09.15") เป็น datetime

    รูปแบบ PEA ใช้ "." คั่นชั่วโมงกับนาที (ไม่ใช่ ":") — คืนค่า None ถ้า parse ไม่ได้
    (กันไฟล์แปลกๆ ไม่ให้ทำให้ทั้งการคำนวณพัง แค่ข้ามจุดข้อมูลนั้นไป)
    """

    try:
        return _dt.datetime.strptime(timestamp.strip(), "%d/%m/%Y %H.%M")
    except (ValueError, AttributeError):
        return None


def compute_hourly_curve(
    readings: List[IntervalReading], interval_minutes: float = 15
) -> Dict[str, List[Optional[float]]]:
    """คำนวณเส้นโค้งกำลังไฟฟ้าเฉลี่ยรายชั่วโมง (kW) จาก interval readings ดิบ แยกตามวันใน
    สัปดาห์ (ใช้ดูว่าช่วงเวลาไหนของวันใช้ไฟเยอะ/น้อย ต่างจาก P/OP/H ที่เป็นแค่ยอดรวม/พีคของ
    ทั้งคาบ) — ค่า kwh แต่ละจุดถูกแปลงเป็นกำลังไฟฟ้าเฉลี่ย (kW) ของช่วงนั้นก่อน (kwh x 60/
    interval_minutes) แล้วนำไปเฉลี่ยรวมกับจุดอื่นๆ ที่ตรงชั่วโมงเดียวกัน (ข้ามหลายวัน/หลายไฟล์)

    คืนค่า dict: {"all": [ชม.0..23], "mon": [...], "tue": [...], ..., "sun": [...]}
    ชั่วโมงที่ไม่มีข้อมูลเลยในกลุ่มนั้นเป็น None (เช่น "mon" ถ้าช่วงที่ดาวน์โหลดไม่มีวันจันทร์เลย)
    """

    factor = 60.0 / interval_minutes
    buckets: Dict[str, List[List[float]]] = {code: [[] for _ in range(24)] for code in DAY_TYPE_CODES}

    for r in readings:
        dt = _parse_interval_timestamp(r.timestamp)
        if dt is None:
            continue
        power_kw = r.kwh * factor
        buckets["all"][dt.hour].append(power_kw)
        buckets[_WEEKDAY_TO_CODE[dt.weekday()]][dt.hour].append(power_kw)

    return {
        code: [round(sum(vals) / len(vals), 2) if vals else None for vals in hours]
        for code, hours in buckets.items()
    }


def compute_meter_multiplier(ct_ratio: str, vt_ratio: str) -> float:
    """คำนวณตัวคูณมิเตอร์จากอัตราส่วน CT/VT เช่น "50:5 A." / "100/5 A." และ
    "22000:110 V." / "115000/115 V." — ระบบ PEA ใช้ตัวคั่นทั้ง ":" (หน้ารายงาน kWh)
    และ "/" (หน้า CustProfile.aspx) แล้วแต่หน้า จึงรองรับทั้งสองแบบ

    ตัวคูณ = (CT primary / CT secondary) x (VT primary / VT secondary)
    """

    import re as _re

    def parse_ratio(text: str) -> float:
        text = text.split()[0]  # ตัดหน่วย (A./V.) ออก
        num, den = _re.split(r"[:/]", text, maxsplit=1)
        return float(num) / float(den)

    return parse_ratio(ct_ratio) * parse_ratio(vt_ratio)
