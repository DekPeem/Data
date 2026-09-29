import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from amr_mapping.amr_boxplot import (
    append_intervals_local,
    load_intervals_local,
    parse_amr_file,
    parse_amr_files,
    render_boxplot_png,
    summarize_available,
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


def test_load_intervals_local_missing_file_returns_empty(tmp_path):
    df = load_intervals_local(tmp_path / "nope.csv")
    assert df.empty


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
