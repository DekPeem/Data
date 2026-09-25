import sys
from pathlib import Path

import pytest
import xlwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.pea_ingest import IntervalReading, parse_interval_report, parse_report_header
from amr_mapping.pea_meter_log_ingest import (
    is_meter_log_xls,
    parse_meter_log_header,
    parse_meter_log_interval_report,
)


# โครงสร้างจริงจากไฟล์ "รายงานใช้ไฟ - รายเดือน" (ยืนยันจากไฟล์จริงที่ผู้ใช้ส่งมา) — ไม่มีคอลัมน์
# Rate A/B/C เลย มีแค่กำลังไฟฟ้าขณะนั้น (kW) ราย 15 นาที ปีในคอลัมน์เวลาเป็น พ.ศ. เหมือนไฟล์จริง
def _write_synthetic_meter_log_xls(path, meter_no="55051721"):
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet0")
    ws.write(0, 0, "รายงานใช้ไฟ - รายเดือน")
    ws.write(1, 0, f"เครื่องวัดฯ: {meter_no}")
    ws.write(2, 0, "เงื่อนไข: เดือน มกราคม 2569")
    ws.write(4, 0, "วันที่/เวลา")
    ws.write(4, 1, "kW")
    ws.write(4, 2, "kVAR")
    # วันจันทร์ที่ 05/01/2569 (พ.ศ.) = 05/01/2026 (ค.ศ.) เวลา 10:00 -> วันทำการ ช่วง Peak (09-22)
    ws.write(5, 0, "05/01/2569 10:00")
    ws.write(5, 1, 40.0)
    ws.write(5, 2, 0.0)
    # เวลา 23:00 วันเดียวกัน -> วันทำการ ช่วง Off-Peak (22:00-09:00)
    ws.write(6, 0, "05/01/2569 23:00")
    ws.write(6, 1, 20.0)
    ws.write(6, 2, 0.0)
    # วันเสาร์ที่ 03/01/2569 (พ.ศ.) = 03/01/2026 (ค.ศ.) -> ทั้งวันเป็น Holiday แม้เวลากลางวัน
    ws.write(7, 0, "03/01/2569 12:00")
    ws.write(7, 1, 8.0)
    ws.write(7, 2, 0.0)
    wb.save(str(path))


def test_is_meter_log_xls_true_for_real_binary_xls(tmp_path):
    path = tmp_path / "report.xls"
    _write_synthetic_meter_log_xls(path)
    assert is_meter_log_xls(path) is True


def test_is_meter_log_xls_false_for_html_disguised_as_xls(tmp_path):
    path = tmp_path / "report.xls"
    path.write_text("<html><body>ไม่ใช่ Excel ไบนารีจริง</body></html>", encoding="utf-8")
    assert is_meter_log_xls(path) is False


def test_parse_meter_log_header_extracts_meter_number(tmp_path):
    path = tmp_path / "report.xls"
    _write_synthetic_meter_log_xls(path, meter_no="99998888")

    info = parse_meter_log_header(path)

    assert info["หมายเลขมิเตอร์"] == "99998888"
    # ไฟล์นี้ไม่มีเลขบัญชี/ชื่อบริษัทเลย
    assert "บัญชีผู้ใช้ไฟ" not in info
    assert "ชื่อผู้ใช้ไฟ" not in info


def test_parse_meter_log_interval_report_converts_be_year_and_kw_to_kwh(tmp_path):
    path = tmp_path / "report.xls"
    _write_synthetic_meter_log_xls(path)

    readings = parse_meter_log_interval_report(path)

    assert len(readings) == 3
    # kW ที่อ่านได้ต้องถูกแปลงเป็น kWh ของช่วง 15 นาที (x0.25) และปี พ.ศ. 2569 -> ค.ศ. 2026
    assert IntervalReading(timestamp="05/01/2026 10.00", period="P", kwh=10.0) in readings
    assert IntervalReading(timestamp="05/01/2026 23.00", period="OP", kwh=5.0) in readings


def test_parse_meter_log_interval_report_treats_weekend_as_holiday_all_day(tmp_path):
    path = tmp_path / "report.xls"
    _write_synthetic_meter_log_xls(path)

    readings = parse_meter_log_interval_report(path)

    # วันเสาร์เที่ยงวัน (อยู่ในช่วงเวลา Peak ปกติถ้าเป็นวันทำการ) ต้องยังถูกจัดเป็น Holiday
    # เพราะเป็นวันหยุดสุดสัปดาห์ทั้งวัน
    saturday_reading = next(r for r in readings if r.timestamp.startswith("03/01/2026"))
    assert saturday_reading.period == "H"


def test_pea_ingest_dispatches_header_and_interval_to_meter_log_parser(tmp_path):
    """pea_ingest.parse_report_header/parse_interval_report (ที่ amr_import.py เรียกใช้อยู่แล้ว)
    ต้องตรวจจับไฟล์ .xls ไบนารีแท้อัตโนมัติแล้วส่งต่อให้ตัวอ่านเฉพาะ โดยผู้เรียกไม่ต้องรู้ว่าไฟล์
    เป็นรูปแบบไหน"""

    path = tmp_path / "report.xls"
    _write_synthetic_meter_log_xls(path, meter_no="55051721")

    header = parse_report_header(path)
    assert header["หมายเลขมิเตอร์"] == "55051721"

    readings = parse_interval_report(path)
    assert len(readings) == 3
