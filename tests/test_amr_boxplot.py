import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from amr_mapping.amr_boxplot import (
    ParsedInterval,
    append_intervals_local,
    compute_bill_stats_from_intervals,
    extract_customer_info,
    extract_customer_info_from_files,
    load_intervals_local,
    parse_amr_file,
    parse_amr_files,
    remove_interval_rows,
    render_boxplot_png,
    summarize_available,
    summarize_available_by_account,
)


def _make_amr_html(start_date: dt.datetime, n_days: int, account_no: str = "", company_name: str = "") -> str:
    """สร้างไฟล์ HTML จำลองรูปแบบเดียวกับรายงาน "ข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" ของ PEA
    (ts + a1/b1/c1 ตาม P/OP/H) — ใช้ทดสอบ parse_amr_file โดยไม่ต้องมีไฟล์จริง

    ถ้าไม่ส่ง account_no/company_name จะได้ header ทั่วไปแบบเดิม — ส่งมาเพื่อจำลองหัวรายงานจริงของ
    PEA (ดู extract_customer_info)"""

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

    if account_no or company_name:
        header = (
            "<table width='800px' cellpadding='4' cellspacing='4'><tr>"
            "<td colspan='7' class='header'>รายงานข้อมูลกิโลวัตต์แบบช่วงเวลา</td></tr>"
            "<tr><td colspan='7' class='header'>[ระหว่างวันที่ : 01/01/2026 - 03/01/2026]</td></tr>"
            "<tr>"
            f"<td class='detail'>บัญชีผู้ใช้ไฟ : </td><td>{account_no}&nbsp;</td>"
            f"<td class='detail'>ชื่อผู้ใช้ไฟ : </td><td>{company_name}</td>"
            "<td></td><td></td><td></td>"
            "</tr>"
            "<tr>"
            "<td class='detail'>เครื่องวัด : </td><td>METER123&nbsp;</td>"
            "<td class='detail'>Tariff : </td><td>3.2&nbsp;</td>"
            "<td></td><td></td><td></td>"
            "</tr>"
            "<tr>"
            "<td class='detail'>CT Ratio : </td><td>1&nbsp;</td>"
            "<td class='detail'>VT Ratio : </td><td>1&nbsp;</td>"
            "<td></td><td></td><td></td>"
            "</tr>"
            "</table>"
        )
    else:
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


def _make_amr_xlsx(tmp_path, start_date: dt.datetime, n_days: int, account_no: str = "", company_name: str = "") -> Path:
    """สร้างไฟล์ .xlsx จริง (Excel 2007+ binary) จำลองรูปแบบไฟล์ AMR จริงแบบที่ 2 ที่ผู้ใช้เจอ
    (นอกจาก HTML-in-.xls แบบเดิม) — 3 ชีต (header/ข้อมูลจริง/ท้ายรายงาน) พร้อมแถวขยะ "0,1,2,...,6"
    บนสุดของทุกชีตที่เจอในไฟล์ตัวอย่างจริง (ดู _strip_leading_index_row ใน amr_boxplot.py)"""

    from openpyxl import Workbook

    wb = Workbook()
    junk_row = list(range(7))

    header_ws = wb.active
    header_ws.title = "Sheet1"
    header_ws.append(junk_row)
    header_ws.append(["รายงานข้อมูลกิโลวัตต์แบบช่วงเวลา"] * 7)
    header_ws.append(["[ระหว่างวันที่ : 01/01/2026 - 03/01/2026]"] * 7)
    header_ws.append(["บัญชีผู้ใช้ไฟ :", account_no, "ชื่อผู้ใช้ไฟ :", company_name, None, None, None])
    header_ws.append(["หมายเลขมิเตอร์ :", "METER123", "Tariff :", "TOU", None, None, None])
    header_ws.append(["CT Ratio :", "100:5 A.", "VT Ratio :", "115000:115 V.", None, None, None])

    data_ws = wb.create_sheet("Sheet2")
    data_ws.append(junk_row)
    data_ws.append([None, "RATE A", "RATE A", "RATE B", "RATE B", "RATE C", "RATE C"])
    d = start_date
    for _ in range(n_days):
        for interval_i in range(96):
            minutes = interval_i * 15
            t = d + dt.timedelta(minutes=minutes) + dt.timedelta(minutes=15)
            hour = (minutes // 60) % 24
            row = [t.strftime("%d/%m/%Y %H.%M"), None, None, None, None, None, None]
            if d.weekday() >= 5:
                row[5] = row[6] = "100.000"
            elif 9 <= hour < 22:
                row[1] = row[2] = "400.000"
            else:
                row[3] = row[4] = "150.000"
            data_ws.append(row)
        d += dt.timedelta(days=1)

    footer_ws = wb.create_sheet("Sheet3")
    footer_ws.append(junk_row)
    footer_ws.append(["***หมายเหตุ***"] * 7)

    path = tmp_path / "report.xlsx"
    wb.save(path)
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


def test_remove_interval_rows_deletes_only_matching_tsic_and_account(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)  # 5*96 = 480 intervals

    append_intervals_local("55101", intervals[:100], storage, account_no="A1")
    append_intervals_local("55101", intervals[100:200], storage, account_no="A2")
    append_intervals_local("55101", intervals[200:250], storage)  # ไม่ระบุบัญชี
    append_intervals_local("86101", intervals[250:300], storage, account_no="A1")  # คนละ TSIC เลขบัญชีชนกัน

    removed = remove_interval_rows(storage, "55101", "A1")
    assert removed == 100

    rows = {(r["business_type_code"], r["account_no"]): r for r in summarize_available_by_account(storage)}
    assert ("55101", "A1") not in rows  # ลบไปแล้ว
    assert rows[("55101", "A2")]["intervals"] == 100  # บัญชีอื่นของ TSIC เดียวกันไม่โดนลบ
    assert rows[("55101", "")]["intervals"] == 50  # กลุ่มไม่ระบุบัญชีไม่โดนลบ
    assert rows[("86101", "A1")]["intervals"] == 50  # คนละ TSIC ไม่โดนลบแม้เลขบัญชีจะชนกัน


def test_remove_interval_rows_empty_account_no_deletes_unspecified_group_only(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    intervals = parse_amr_file(amr_report_file)

    append_intervals_local("55101", intervals[:100], storage, account_no="A1")
    append_intervals_local("55101", intervals[100:150], storage)  # ไม่ระบุบัญชี

    removed = remove_interval_rows(storage, "55101", "")
    assert removed == 50

    rows = {(r["business_type_code"], r["account_no"]): r for r in summarize_available_by_account(storage)}
    assert ("55101", "") not in rows
    assert rows[("55101", "A1")]["intervals"] == 100


def test_remove_interval_rows_no_match_returns_zero(amr_report_file, tmp_path):
    storage = tmp_path / "storage.csv"
    append_intervals_local("55101", parse_amr_file(amr_report_file), storage, account_no="A1")
    assert remove_interval_rows(storage, "86101", "A1") == 0


def test_remove_interval_rows_missing_file_returns_zero(tmp_path):
    assert remove_interval_rows(tmp_path / "nope.csv", "55101", "") == 0


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


def test_extract_customer_info_reads_account_and_company_from_header(tmp_path):
    html = _make_amr_html(
        dt.datetime(2026, 1, 1), n_days=1, account_no="0199000001", company_name="บริษัท ทดสอบ จำกัด"
    )
    path = tmp_path / "report.xls"
    path.write_text(html, encoding="utf-8")

    account_no, company_name = extract_customer_info(path)
    assert account_no == "0199000001"
    assert company_name == "บริษัท ทดสอบ จำกัด"


def test_extract_customer_info_returns_empty_when_not_found(amr_report_file):
    # amr_report_file ใช้ header ทั่วไป ไม่มี "บัญชีผู้ใช้ไฟ"/"ชื่อผู้ใช้ไฟ" ให้อ่าน
    account_no, company_name = extract_customer_info(amr_report_file)
    assert account_no == ""
    assert company_name == ""


def test_extract_customer_info_missing_file_returns_empty(tmp_path):
    account_no, company_name = extract_customer_info(tmp_path / "nope.xls")
    assert account_no == ""
    assert company_name == ""


def test_extract_customer_info_from_files_uses_first_match(tmp_path):
    empty_html = _make_amr_html(dt.datetime(2026, 1, 1), n_days=1)
    matched_html = _make_amr_html(
        dt.datetime(2026, 1, 1), n_days=1, account_no="0199000002", company_name="บริษัท สอง จำกัด"
    )
    path1 = tmp_path / "report1.xls"
    path1.write_text(empty_html, encoding="utf-8")
    path2 = tmp_path / "report2.xls"
    path2.write_text(matched_html, encoding="utf-8")

    account_no, company_name = extract_customer_info_from_files([path1, path2])
    assert account_no == "0199000002"
    assert company_name == "บริษัท สอง จำกัด"


def test_extract_customer_info_from_files_all_empty_returns_empty(amr_report_file):
    account_no, company_name = extract_customer_info_from_files([amr_report_file])
    assert account_no == ""
    assert company_name == ""


def test_parse_amr_file_supports_real_xlsx_binary_format(tmp_path):
    """ไฟล์ .xlsx จริง (Excel 2007+ binary) รูปแบบที่ 2 นอกจาก HTML-in-.xls เดิม — เจอจากไฟล์
    ตัวอย่างจริงของผู้ใช้ที่อัปโหลดไม่ได้ก่อนหน้านี้"""

    path = _make_amr_xlsx(tmp_path, dt.datetime(2026, 1, 1), n_days=5)
    intervals = parse_amr_file(path)
    assert len(intervals) == 5 * 96
    assert {i.rate for i in intervals} == {"P", "OP", "H"}


def test_extract_customer_info_supports_real_xlsx_binary_format(tmp_path):
    path = _make_amr_xlsx(
        tmp_path, dt.datetime(2026, 1, 1), n_days=1, account_no="0199000003", company_name="บริษัท สาม จำกัด"
    )
    account_no, company_name = extract_customer_info(path)
    assert account_no == "0199000003"
    assert company_name == "บริษัท สาม จำกัด"
