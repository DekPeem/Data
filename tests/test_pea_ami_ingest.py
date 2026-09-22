import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.pea_ami_ingest import parse_ami_interval_report, parse_ami_report_header
from amr_mapping.pea_ingest import IntervalReading, is_ami_xlsx, parse_interval_report, parse_report_header


# โครงสร้างจริงจากไฟล์ export ของระบบ "AMI" ของ PEA (ยืนยันจากไฟล์จริงที่ผู้ใช้ส่งมา) — ใช้
# ข้อมูลสมมติแทนของจริงทั้งหมด ปีในคอลัมน์เวลาเป็น พ.ศ. ตามไฟล์จริง (2568 = ค.ศ. 2025)
def _write_synthetic_ami_workbook(path, account_no="0199000000", company_name="บริษัท ทดสอบ จำกัด"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    ws["B3"] = "การไฟฟ้าส่วนภูมิภาค โครงการติดตั้งระบบมิเตอร์อัจฉริยะ (AMI)"
    ws["B6"] = "รายงานข้อมูลกิโลวัตต์รายเดือน"
    ws["B7"] = "ประจำเดือน : กันยายน 2568"
    ws["B9"] = "บัญชีผู้ใช้ไฟฟ้า : "
    ws["C9"] = account_no
    ws["E9"] = "ชื่อผู้ใช้ไฟฟ้า : "
    ws["F9"] = company_name
    ws["B10"] = "หมายเลขมิเตอร์ : "
    ws["C10"] = "1234567"
    ws["E10"] = "Tariff : "
    ws["F10"] = "TOU"
    ws["B11"] = "CT Ratio : "
    ws["C11"] = "150:5 A."
    ws["E11"] = "VT Ratio : "
    ws["F11"] = "115000:115 V."

    ws["A28"] = "เวลา"
    ws["B28"] = "Rate A"
    ws["D28"] = "Rate B"
    ws["F28"] = "Rate C"
    ws["A29"] = "01/09/2568 00.15"
    ws["D29"] = "20.000"
    ws["A30"] = "01/09/2568 09.30"
    ws["B30"] = "30.000"
    ws["A31"] = "01/09/2568 22.15"
    ws["F31"] = "10.000"
    ws["A32"] = "กิโลวัตต์สูงสุด"
    ws["B32"] = "24/09/2568 18.00"
    ws["C32"] = "292.000"
    ws["A34"] = "พิมพ์โดย : ทดสอบ"

    wb.save(path)


def test_is_ami_xlsx_true_for_real_excel_file(tmp_path):
    path = tmp_path / "sample.xlsx"
    _write_synthetic_ami_workbook(path)
    assert is_ami_xlsx(path) is True


def test_is_ami_xlsx_false_for_html_disguised_as_xls(tmp_path):
    path = tmp_path / "sample.xls"
    path.write_text("<html><body>ไม่ใช่ Excel จริง</body></html>", encoding="utf-8")
    assert is_ami_xlsx(path) is False


def test_parse_ami_report_header_extracts_and_aliases_fields(tmp_path):
    path = tmp_path / "ami_report.xlsx"
    _write_synthetic_ami_workbook(path, account_no="0199000000", company_name="บริษัท ทดสอบ จำกัด")

    info = parse_ami_report_header(path)

    # ป้ายในไฟล์ AMI มีคำว่า "ไฟฟ้า" ต่อท้าย (บัญชีผู้ใช้ไฟฟ้า/ชื่อผู้ใช้ไฟฟ้า) ต้องถูกแปลงให้
    # ตรงกับ key มาตรฐานเดียวกับไฟล์ AMRWEB (บัญชีผู้ใช้ไฟ/ชื่อผู้ใช้ไฟ) ไม่งั้นโค้ดฝั่งเรียกใช้
    # (amr_import.py) จะหาไม่เจอ
    assert info["บัญชีผู้ใช้ไฟ"] == "0199000000"
    assert info["ชื่อผู้ใช้ไฟ"] == "บริษัท ทดสอบ จำกัด"
    assert info["หมายเลขมิเตอร์"] == "1234567"
    assert info["Tariff"] == "TOU"
    assert info["CT Ratio"] == "150:5 A."
    assert info["VT Ratio"] == "115000:115 V."


def test_parse_ami_interval_report_reads_rate_columns_and_converts_be_year(tmp_path):
    path = tmp_path / "ami_report.xlsx"
    _write_synthetic_ami_workbook(path)

    readings = parse_ami_interval_report(path)

    # ปี พ.ศ. 2568 ในไฟล์ ต้องถูกแปลงเป็น ค.ศ. 2025 ก่อนคืนค่า (ต่างจากไฟล์ AMRWEB ที่ใช้ ค.ศ.
    # อยู่แล้ว ไม่งั้น pea_ingest._parse_interval_timestamp จะคำนวณวันในสัปดาห์ผิด)
    assert IntervalReading(timestamp="01/09/2025 00.15", period="OP", kwh=20.0) in readings
    assert IntervalReading(timestamp="01/09/2025 09.30", period="P", kwh=30.0) in readings
    assert IntervalReading(timestamp="01/09/2025 22.15", period="H", kwh=10.0) in readings


def test_parse_ami_interval_report_skips_summary_and_footer_rows(tmp_path):
    path = tmp_path / "ami_report.xlsx"
    _write_synthetic_ami_workbook(path)

    readings = parse_ami_interval_report(path)

    # แถว "กิโลวัตต์สูงสุด" และ "พิมพ์โดย" ท้ายตาราง ต้องไม่ถูกอ่านเป็น reading (timestamp
    # ของแถวเหล่านี้ไม่ตรงรูปแบบวันที่ DD/MM/YYYY)
    assert len(readings) == 3
    assert all(r.timestamp.startswith("01/09/2025") for r in readings)


def test_pea_ingest_parse_report_header_dispatches_to_ami_parser_for_xlsx(tmp_path):
    """pea_ingest.parse_report_header (ที่ amr_import.py เรียกใช้อยู่แล้ว) ต้องตรวจจับไฟล์
    .xlsx แท้อัตโนมัติแล้วส่งต่อให้ parse_ami_report_header โดยผู้เรียกไม่ต้องรู้ว่าไฟล์เป็น
    รูปแบบไหน"""

    path = tmp_path / "ami_report.xlsx"
    _write_synthetic_ami_workbook(path, account_no="0288888888", company_name="บริษัท เอมี จำกัด")

    info = parse_report_header(path)

    assert info["บัญชีผู้ใช้ไฟ"] == "0288888888"
    assert info["ชื่อผู้ใช้ไฟ"] == "บริษัท เอมี จำกัด"


def test_pea_ingest_parse_interval_report_dispatches_to_ami_parser_for_xlsx(tmp_path):
    path = tmp_path / "ami_report.xlsx"
    _write_synthetic_ami_workbook(path)

    readings = parse_interval_report(path)

    assert IntervalReading(timestamp="01/09/2025 09.30", period="P", kwh=30.0) in readings
