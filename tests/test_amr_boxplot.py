import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from amr_mapping.amr_boxplot import (
    ParsedInterval,
    append_intervals_local,
    compute_bill_stats_from_intervals,
    load_intervals_local,
    parse_amr_file,
    parse_amr_files,
    render_boxplot_png,
    summarize_available,
    summarize_available_by_account,
)


def _make_amr_html(start_date: dt.datetime, n_days: int) -> str:
    """สร้างไฟล์ HTML จำลองรูปแบบเดียวกับรายงาน "ข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" ของ PEA
    (ts + a1/b1/c1 ตาม P/OP/H) — ใช้ทดสอบ parse_amr_file โดยไม่ต้องมีไฟล์จริง"""

    rows = []
    d = start_date
    for _ in range(n_days):
        for interval_i in range(96):  # 96 x 15 นาที = 24 ชม.
            minutes = interval_i * 15
            t = d + dt.timedelta(minutes=minutes) + dt.timedelta(minutes=15)
            hour = (minutes // 60) % 24
            is_weekend = d.weekday() >= 5
            if is_weekend:
                col, kw = "c1", 100.0
            elif 9 <= hour < 22:
                col, kw = "a1", 400.0
            else:
                col, kw = "b1", 150.0
            row = {"ts": t.strftime("%d/%m/%Y %H.%M"), "a1": "", "a2": "", "b1": "", "b2": "", "c1": "", "c2": ""}
            row[col] = f"{kw:.2f}"
            rows.append(row)
        d += dt.timedelta(days=1)

    header = "<table><tr><td>Header info</td></tr></table>"
    data_rows = "".join(
        "<tr>" + "".join(f"<td>{r[c]}</td>" for c in ["ts", "a1", "a2", "b1", "b2", "c1", "c2"]) + "</tr>"
        for r in rows
    )
    # ใช้ <td> (ไม่ใช่ <th>) สำหรับแถวหัวตารางในตารางข้อมูล — pandas.read_html จะไม่ดึงแถวนี้ไปตั้ง
    # เป็นชื่อคอลัมน์อัตโนมัติ (เหมือนไฟล์ PEA จริงที่ table[1] มีแถวข้อความหัวข้อปนอยู่เป็นแถวแรก
    # ของข้อมูลจริงๆ ไม่ใช่ <th> — ตรงกับที่ _read_one ต้อง .iloc[1:] ตัดแถวนั้นทิ้งเอง)
    data_table = (
        "<table><tr><td>ts</td><td>a1</td><td>a2</td><td>b1</td><td>b2</td><td>c1</td><td>c2</td></tr>"
        + data_rows
        + "</table>"
    )
    footer = "<table><tr><td>Footer info</td></tr></table>"
    return header + data_table + footer


@pytest.fixture()
def amr_report_file(tmp_path):
    html = _make_amr_html(dt.datetime(2026, 1, 1), n_days=5)  # 1 ม.ค. 2569 เป็นวันพฤหัส
    path = tmp_path / "report.xls"
    path.write_text(html, encoding="utf-8")
    return path


def test_parse_amr_file_extracts_all_intervals(amr_report_file):
    intervals = parse_amr_file(amr_report_file)
    assert len(intervals) == 5 * 96  # 5 วัน x 96 จุดต่อวัน ไม่มีจุดไหนถูกทิ้ง


def test_parse_amr_file_classifies_rate_correctly(amr_report_file):
    intervals = parse_amr_file(amr_report_file)
    rates = {i.rate for i in intervals}
    assert rates == {"P", "OP", "H"}


def test_parse_amr_file_unreadable_returns_empty_list(tmp_path):
    bad_file = tmp_path / "not_amr.xls"
    bad_file.write_text("<html><body>not a real report</body></html>", encoding="utf-8")
    assert parse_amr_file(bad_file) == []


def test_parse_amr_files_dedupes_identical_files(amr_report_file):
    """อัปโหลดไฟล์เดิมซ้ำ 2 รอบ ต้องนับแค่ครั้งเดียว ไม่ใช่ x2 (เดิมเคยมีบั๊ก dedup ผิดระดับที่ทำให้
    เหลือแค่ 1 จุดต่อชั่วโมงแทนที่จะเป็น 4 จุด — เทสต์นี้ครอบคลุมทั้งสองแบบ)"""

    once = parse_amr_files([amr_report_file])
    twice = parse_amr_files([amr_report_file, amr_report_file])
    assert len(once) == len(twice)
    assert len(once) == 5 * 96


def test_append_and_load_intervals_local_round_trip(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)
    added = append_intervals_local("55101", intervals, storage)
    assert added == len(intervals)

    df = load_intervals_local(storage, "55101")
    assert len(df) == len(intervals)

    # ประเภทธุรกิจอื่นต้องไม่เห็นข้อมูลนี้
    other = load_intervals_local(storage, "86101")
    assert other.empty


def test_compute_bill_stats_from_intervals_matches_fixture(amr_report_file):
    """amr_report_file = 5 วันเริ่มพฤหัส (พฤ/ศุกร์/เสาร์/อาทิตย์/จันทร์) → 3 วันทำการ (P peak=400kW,
    OP peak=150kW) + 2 วันหยุด (H peak=100kW) — เช็คว่าคำนวณ peak/หน่วยไฟ/จำนวนวันตรงเป๊ะ"""

    stats = compute_bill_stats_from_intervals(parse_amr_file(amr_report_file))

    assert stats["P"] == {"peak": 400.0, "energy_kwh": 15600.0, "days": 3}
    assert stats["OP"] == {"peak": 150.0, "energy_kwh": 4950.0, "days": 3}
    assert stats["H"] == {"peak": 100.0, "energy_kwh": 4800.0, "days": 2}


def test_compute_bill_stats_from_intervals_empty_input_returns_empty_dict():
    assert compute_bill_stats_from_intervals([]) == {}


def test_load_intervals_local_missing_file_returns_empty(tmp_path):
    df = load_intervals_local(tmp_path / "nope.csv")
    assert df.empty


def test_append_intervals_local_stores_account_and_company_name(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)
    append_intervals_local(
        "55101", intervals, storage,
        account_no="0199000001", company_name="บริษัท ทดสอบ จำกัด", registration_no="0105544000157",
    )

    df = load_intervals_local(storage, "55101")
    assert (df["account_no"] == "0199000001").all()
    assert (df["company_name"] == "บริษัท ทดสอบ จำกัด").all()
    assert (df["registration_no"] == "0105544000157").all()


def test_append_intervals_local_defaults_account_fields_to_blank(amr_report_file, tmp_path):
    """ไม่ระบุ account_no/company_name เลย (เหมือนโหมดแนบไฟล์เองแบบเดิม) ต้องยังใช้งานได้ปกติ
    ไม่ error เว้นว่างไว้เฉยๆ"""

    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)
    append_intervals_local("55101", intervals, storage)

    df = load_intervals_local(storage, "55101")
    assert (df["account_no"] == "").all()
    assert (df["company_name"] == "").all()


def test_append_intervals_local_migrates_old_header_format(tmp_path):
    """ไฟล์เก่าก่อนเพิ่มคอลัมน์ account_no/company_name (header มีแค่ 5 คอลัมน์เดิม) ต้อง migrate
    อัตโนมัติตอน append แถวใหม่ — แถวเก่ายังอยู่ครบ (account_no/company_name เว้นว่างไว้เพราะย้อน
    กลับไปหาไม่ได้) แถวใหม่มีค่าที่ใส่มาถูกต้อง"""

    storage = tmp_path / "storage.csv"
    storage.write_text(
        "business_type_code,date,hour,rate,kw\n55101,2026-01-01,9,P,123.4\n", encoding="utf-8"
    )

    new_intervals = [ParsedInterval(date="2026-01-02", hour=10, minute=0, rate="P", kw=200.0)]
    append_intervals_local("55101", new_intervals, storage, account_no="0199000002", company_name="บริษัท ใหม่ จำกัด")

    df = load_intervals_local(storage, "55101")
    assert len(df) == 2
    old_row = df[df["date"] == "2026-01-01"].iloc[0]
    assert old_row["account_no"] == ""
    assert old_row["company_name"] == ""
    new_row = df[df["date"] == "2026-01-02"].iloc[0]
    assert new_row["account_no"] == "0199000002"
    assert new_row["company_name"] == "บริษัท ใหม่ จำกัด"


def test_summarize_available_by_account_groups_per_tsic_and_account(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)  # 5*96 = 480 intervals

    # บัญชีเดียวกัน อัปโหลด 2 รอบ (คนละไฟล์/คนละเดือน) ต้องรวมเป็นกลุ่มเดียวกัน
    append_intervals_local("55101", intervals[:100], storage, account_no="A1", company_name="บริษัท เอ", registration_no="0105544000157")
    append_intervals_local("55101", intervals[100:], storage, account_no="A1", company_name="บริษัท เอ")
    # อีกบัญชีของ TSIC เดียวกัน
    append_intervals_local("55101", intervals[:50], storage, account_no="A2", company_name="บริษัท บี")
    # ไม่ระบุบัญชีเลย (โหมดแนบไฟล์เองแบบเก่า) — ต้องรวมเป็น 1 กลุ่ม "ไม่ระบุบัญชี" แยกจาก A1/A2
    append_intervals_local("55101", intervals[:20], storage)

    rows = summarize_available_by_account(storage)
    by_account = {(r["business_type_code"], r["account_no"]): r for r in rows}

    assert by_account[("55101", "A1")]["intervals"] == 480
    assert by_account[("55101", "A1")]["company_name"] == "บริษัท เอ"
    assert by_account[("55101", "A1")]["registration_no"] == "0105544000157"  # เจอในรอบแรกพอ
    assert by_account[("55101", "A2")]["intervals"] == 50
    assert by_account[("55101", "A2")]["company_name"] == "บริษัท บี"
    assert by_account[("55101", "")]["intervals"] == 20
    assert by_account[("55101", "")]["company_name"] == ""

    # เรียงจากจุดข้อมูลเยอะไปน้อย
    assert [r["intervals"] for r in rows] == sorted((r["intervals"] for r in rows), reverse=True)


def test_summarize_available_by_account_missing_file_returns_empty_list(tmp_path):
    assert summarize_available_by_account(tmp_path / "nope.csv") == []


def test_summarize_available_reports_per_business_type(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)
    append_intervals_local("55101", intervals, storage)

    summary = summarize_available(storage)
    assert summary["55101"]["intervals"] == len(intervals)
    assert summary["55101"]["days"] == 5


def test_render_boxplot_png_returns_valid_png(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)
    append_intervals_local("55101", intervals, storage)
    df = load_intervals_local(storage, "55101")

    png = render_boxplot_png(df, business_type_code="55101", business_type_name="โรงแรม")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_boxplot_png_empty_dataframe_raises(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    df = load_intervals_local(storage, "55101")  # ไม่มีไฟล์เลย -> DataFrame ว่าง
    with pytest.raises(ValueError):
        render_boxplot_png(df, business_type_code="55101")
