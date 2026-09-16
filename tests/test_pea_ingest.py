import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.pea_ingest import (
    IntervalReading,
    MonthlyRegisterReading,
    aggregate_interval_readings,
    average_profiles,
    compute_hourly_curve,
    compute_meter_multiplier,
    compute_monthly_profiles,
    parse_interval_report,
    parse_report_header,
)


def test_compute_meter_multiplier():
    # CT 50:5 -> 10, VT 22000:110 -> 200, รวม = 2000 (ตรงกับตัวอย่างมิเตอร์จริง)
    assert compute_meter_multiplier("50:5 A.", "22000:110 V.") == pytest.approx(2000.0)


def test_compute_meter_multiplier_slash_separator():
    # หน้า CustProfile.aspx ใช้ตัวคั่น "/" แทน ":" (เช่น "100/5 A." , "115000/115 V.")
    # CT 100/5 -> 20, VT 115000/115 -> 1000, รวม = 20000
    assert compute_meter_multiplier("100/5 A.", "115000/115 V.") == pytest.approx(20000.0)


def test_compute_monthly_profiles_diff_and_scale():
    readings = [
        MonthlyRegisterReading(
            month="07/2026",
            kwh_total_raw=100.0,
            kwh_a_raw=10.0,
            kwh_b_raw=20.0,
            kwh_c_raw=30.0,
            demand_a_raw=0.300,
            demand_b_raw=0.280,
            demand_c_raw=0.290,
        ),
        MonthlyRegisterReading(
            month="08/2026",
            kwh_total_raw=150.0,
            kwh_a_raw=15.0,  # +5
            kwh_b_raw=28.0,  # +8
            kwh_c_raw=45.0,  # +15
            demand_a_raw=0.320,
            demand_b_raw=0.300,
            demand_c_raw=0.328,
        ),
    ]

    profiles = compute_monthly_profiles(readings, multiplier=2000)
    assert len(profiles) == 1  # เดือนแรกไม่มีเดือนก่อนหน้าให้หักลบ จึงถูกข้าม

    p = profiles[0]
    assert p.month == "08/2026"
    assert p.energy_kwh == {"P": 10000.0, "OP": 16000.0, "H": 30000.0}
    assert p.demand_kw == {"P": 640.0, "OP": 600.0, "H": 656.0}


def test_average_profiles():
    readings = [
        MonthlyRegisterReading("06/2026", 0, 0, 0, 0, 0.30, 0.30, 0.30),
        MonthlyRegisterReading("07/2026", 0, 10, 10, 10, 0.30, 0.30, 0.30),
        MonthlyRegisterReading("08/2026", 0, 20, 30, 40, 0.40, 0.20, 0.10),
    ]
    profiles = compute_monthly_profiles(readings, multiplier=1)
    agg = average_profiles(profiles)
    assert agg["n_months"] == 2
    # เดือน 07: energy P=10 OP=10 H=10 ; เดือน 08: energy P=10 OP=20 H=30 -> เฉลี่ย
    assert agg["energy_kwh"] == {"P": 10.0, "OP": 15.0, "H": 20.0}
    # demand เป็นค่าที่อ่านได้ตรงๆ ของแต่ละเดือน (ไม่ใช่ผลต่าง) -> เฉลี่ยของ 0.30/0.40 และ 0.30/0.20 และ 0.30/0.10
    assert agg["demand_kw"] == pytest.approx({"P": 0.35, "OP": 0.25, "H": 0.20})


def test_average_profiles_empty_raises():
    with pytest.raises(ValueError):
        average_profiles([])


_SYNTHETIC_INTERVAL_HTML = """
<html><body>
<table>
  <tr><td>รายงานข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา (ตัวอย่างสมมติ ไม่ใช่ข้อมูลลูกค้าจริง)</td></tr>
</table>
<table>
  <tr><td></td><td>RATE A</td><td>RATE B</td><td>RATE C</td><td>ผลรวม</td></tr>
  <tr><td>01/08/2026 00.15</td><td></td><td></td><td>10.00</td><td>10.00</td></tr>
  <tr><td>01/08/2026 09.15</td><td>20.00</td><td></td><td></td><td>20.00</td></tr>
  <tr><td>01/08/2026 09.30</td><td>30.00</td><td></td><td></td><td>30.00</td></tr>
  <tr><td>01/08/2026 22.15</td><td></td><td>5.00</td><td></td><td>5.00</td></tr>
  <tr><td>ผลรวมทั้งหมด</td><td>50.00</td><td>5.00</td><td>10.00</td><td>65.00</td></tr>
</table>
</body></html>
"""


def test_parse_interval_report(tmp_path):
    path = tmp_path / "synthetic_interval.xls"
    path.write_text(_SYNTHETIC_INTERVAL_HTML, encoding="utf-8")

    readings = parse_interval_report(path)

    # แถวสรุป "ผลรวมทั้งหมด" ต้องถูกข้าม ไม่นับเป็น reading
    assert all(r.timestamp != "ผลรวมทั้งหมด" for r in readings)
    assert IntervalReading(timestamp="01/08/2026 09.30", period="P", kwh=30.0) in readings
    assert IntervalReading(timestamp="01/08/2026 22.15", period="OP", kwh=5.0) in readings
    assert IntervalReading(timestamp="01/08/2026 00.15", period="H", kwh=10.0) in readings


# โครงสร้างจริงจากไฟล์ export ของ PEA (ยืนยันจากไฟล์จริงที่ผู้ใช้ส่งมา — ตารางหัวรายงานแยก
# ต่างหากจากตารางข้อมูลราย 15 นาที อยู่ก่อนหน้ากัน) ใช้ข้อมูลสมมติแทนของจริงทั้งหมด
_SYNTHETIC_HEADER_HTML = """
<meta http-equiv='Content-Type' content='text/html; charset=UTF-8'/>
<table width='800px' cellpadding='4' cellspacing='4'><tr>
<td colspan='7' class='header'>รายงานข้อมูลกิโลวัตต์แบบช่วงเวลา</td></tr>
<tr>
<td colspan='7' class='header'>[ระหว่างวันที่ : 01 มิถุนายน 2569 - 30 มิถุนายน 2569]</td></tr>
<tr>
<td class='detail'>บัญชีผู้ใช้ไฟ : </td><td>0199000000&nbsp;</td><td class='detail'>ชื่อผู้ใช้ไฟ : </td><td>บริษัท ทดสอบ จำกัด</td><td></td>
<td></td>
<td></td>
</tr>
<tr>
<td class='detail'>หมายเลขมิเตอร์ : </td><td>1234567&nbsp;</td><td class='detail'>Tariff : </td>
<td>TOU</td><td></td>
<td></td>
<td></td>
</tr>
<tr>
<td class='detail'>CT Ratio : </td>
<td>150:5 A. </td><td class='detail'>VT Ratio : </td>
<td>115000:115 V. </td><td></td>
<td></td>
<td></td>
</tr>
</table>
<table width='100%' cellpadding='4' cellspacing='4'><tr><td width='20%'></td><td width='27%' class='repheader' colspan='2'>RATE A</td><td width='27%' class='repheader' colspan='2'>RATE B</td><td width='28%' class='repheader' colspan='2'>RATE C</td></tr>
<tr><td class='leftcenter'>&nbsp;01/06/2026 00.15</td><td class='rightdetail' colspan='2'></td><td class='rightdetail' colspan='2'>540.000</td><td class='rightdetail' colspan='2'></td></tr>
</table>
"""


def test_parse_report_header_extracts_account_company_meter_tariff_ratios(tmp_path):
    path = tmp_path / "synthetic_with_header.xls"
    path.write_text(_SYNTHETIC_HEADER_HTML, encoding="utf-8")

    info = parse_report_header(path)

    assert info["บัญชีผู้ใช้ไฟ"] == "0199000000"
    assert info["ชื่อผู้ใช้ไฟ"] == "บริษัท ทดสอบ จำกัด"
    assert info["หมายเลขมิเตอร์"] == "1234567"
    assert info["Tariff"] == "TOU"
    assert info["CT Ratio"] == "150:5 A."
    assert info["VT Ratio"] == "115000:115 V."


def test_parse_report_header_returns_empty_dict_when_no_header_table(tmp_path):
    """ไฟล์รูปแบบเก่า/ไฟล์ทดสอบที่ไม่มีตารางหัวรายงานเลย ต้องคืน dict ว่าง ไม่ error"""
    path = tmp_path / "synthetic_interval.xls"
    path.write_text(_SYNTHETIC_INTERVAL_HTML, encoding="utf-8")

    assert parse_report_header(path) == {}


def test_compute_hourly_curve_buckets_by_hour_and_weekday():
    # 01/08/2026 = วันเสาร์ (sat), 03/08/2026 = วันจันทร์ (mon)
    readings = [
        IntervalReading("01/08/2026 09.15", "H", 10.0),  # เสาร์ ชม.9 -> 40 kW
        IntervalReading("01/08/2026 09.30", "H", 20.0),  # เสาร์ ชม.9 -> 80 kW
        IntervalReading("03/08/2026 09.15", "P", 5.0),  # จันทร์ ชม.9 -> 20 kW
    ]

    curve = compute_hourly_curve(readings, interval_minutes=15)

    # "all" ต้องเฉลี่ยรวมทุกวัน: (40+80+20)/3 = 46.666... -> ปัด 2 ตำแหน่ง
    assert curve["all"][9] == pytest.approx(46.67)
    # "sat" เฉลี่ยเฉพาะของวันเสาร์: (40+80)/2 = 60
    assert curve["sat"][9] == pytest.approx(60.0)
    # "mon" มีแค่จุดเดียว = 20
    assert curve["mon"][9] == pytest.approx(20.0)
    # ชั่วโมงอื่นที่ไม่มีข้อมูลเลยต้องเป็น None ไม่ใช่ 0
    assert curve["all"][0] is None
    assert curve["tue"][9] is None
    # โครงสร้างต้องมีครบทุก day_type ที่นิยามไว้ (8 กลุ่ม x 24 ชม.)
    assert set(curve.keys()) == {"all", "mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    assert all(len(hours) == 24 for hours in curve.values())


def test_compute_hourly_curve_skips_unparseable_timestamps():
    readings = [IntervalReading("ไม่ใช่วันที่", "P", 100.0)]
    curve = compute_hourly_curve(readings)
    assert all(v is None for v in curve["all"])


def test_aggregate_interval_readings():
    readings = [
        IntervalReading("01/08/2026 09.15", "P", 20.0),
        IntervalReading("01/08/2026 09.30", "P", 30.0),
        IntervalReading("01/08/2026 22.15", "OP", 5.0),
        IntervalReading("01/08/2026 00.15", "H", 10.0),
    ]
    profile = aggregate_interval_readings(readings, interval_minutes=15, label="2026-08")

    assert profile.month == "2026-08"
    assert profile.energy_kwh == {"P": 50.0, "OP": 5.0, "H": 10.0}
    # demand = ค่าสูงสุดต่อช่วง x (60/15) = x4
    assert profile.demand_kw == {"P": 120.0, "OP": 20.0, "H": 40.0}
