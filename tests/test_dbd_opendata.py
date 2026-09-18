import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import amr_mapping.dbd_opendata as dbd_opendata
from amr_mapping.dbd_opendata import (
    build_url,
    fetch_all,
    fetch_csv_text,
    init_db,
    is_db_available,
    load_csv_into_db,
    month_range,
    normalize_row,
    search_juristic_person,
)


def test_month_range_single_year():
    assert list(month_range(2024, 1, 2024, 3)) == [(2024, 1), (2024, 2), (2024, 3)]


def test_month_range_crosses_year_boundary():
    assert list(month_range(2023, 11, 2024, 2)) == [
        (2023, 11), (2023, 12), (2024, 1), (2024, 2),
    ]


def test_month_range_single_month():
    assert list(month_range(2024, 6, 2024, 6)) == [(2024, 6)]


def test_build_url_registration():
    url = build_url("registration", 2024, 3)
    assert url == "https://openapi.dbd.go.th/juristic_person/registration/99_202403_1.csv"


def test_build_url_dissolution():
    url = build_url("dissolution", 2024, 12)
    assert url == "https://openapi.dbd.go.th/juristic_person/dissolution/99_202412_2.csv"


def test_build_url_rejects_unknown_kind():
    import pytest

    with pytest.raises(ValueError):
        build_url("something_else", 2024, 1)


# ── normalize_row (จำลองรูปแบบคอลัมน์จริงที่คาดว่า DBD ใช้ — ดูคำเตือนใน docstring หัวไฟล์
#    ว่ายังไม่เคยยืนยันกับไฟล์จริง) ──


def test_normalize_row_maps_known_columns():
    row = {
        "เลขทะเบียนนิติบุคคล": "0105544000157",
        "ชื่อนิติบุคคล (ไทย)": "บริษัท ทดสอบ จำกัด",
        "วันที่จดทะเบียนจัดตั้ง": "01/01/2567",
        "ทุนจดทะเบียน": "1000000",
        "รหัสวัตถุประสงค์": "47190",
        "วัตถุประสงค์": "ขายปลีกสินค้าทั่วไป",
        "ที่ตั้งสำนักงานใหญ่": "123 ถนนทดสอบ",
        "ตำบล": "ในเมือง",
        "อำเภอ": "เมือง",
        "จังหวัด": "ขอนแก่น",
        "รหัสไปรษณีย์": "40000",
    }

    result = normalize_row(row, status="registration", source_month="2024-01")

    assert result == (
        "0105544000157", "บริษัท ทดสอบ จำกัด", "01/01/2567", "1000000",
        "47190", "ขายปลีกสินค้าทั่วไป", "123 ถนนทดสอบ", "ในเมือง", "เมือง",
        "ขอนแก่น", "40000", "registration", "2024-01",
    )


def test_normalize_row_falls_back_to_alternate_column_names():
    # ไฟล์บางรุ่นใช้ "เลขทะเบียน"/"ชื่อนิติบุคคล" แทน (ไม่มี "(ไทย)"/"นิติบุคคล" ต่อท้าย)
    row = {"เลขทะเบียน": "999", "ชื่อนิติบุคคล": "บริษัท บี จำกัด", "วันที่จดทะเบียนเลิก": "01/02/2567"}
    result = normalize_row(row, status="dissolution", source_month="2024-02")
    assert result[0] == "999"
    assert result[1] == "บริษัท บี จำกัด"
    assert result[2] == "01/02/2567"


def test_normalize_row_missing_columns_become_empty_strings():
    result = normalize_row({}, status="registration", source_month="2024-01")
    assert result == ("", "", "", "", "", "", "", "", "", "", "", "registration", "2024-01")


# ── init_db / load_csv_into_db / search_juristic_person (SQLite จริงใน tmp_path) ──


def test_load_csv_into_db_and_search_roundtrip(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    csv_text = (
        "เลขทะเบียนนิติบุคคล,ชื่อนิติบุคคล (ไทย),วันที่จดทะเบียนจัดตั้ง\n"
        "0105544000157,บริษัท ทดสอบ เอบีซี จำกัด,01/01/2567\n"
        "0105544000158,บริษัท อื่น จำกัด,02/01/2567\n"
    )
    n = load_csv_into_db(conn, csv_text, status="registration", source_month="2024-01")
    conn.close()

    assert n == 2

    results = search_juristic_person("ทดสอบ", db_path=db_path)
    assert len(results) == 1
    assert results[0]["name"] == "บริษัท ทดสอบ เอบีซี จำกัด"
    assert results[0]["reg_id"] == "0105544000157"
    assert results[0]["status"] == "registration"


def test_load_csv_into_db_ignores_duplicates_on_rerun(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    csv_text = "เลขทะเบียนนิติบุคคล,ชื่อนิติบุคคล (ไทย)\n0105544000157,บริษัท ทดสอบ จำกัด\n"
    load_csv_into_db(conn, csv_text, status="registration", source_month="2024-01")
    load_csv_into_db(conn, csv_text, status="registration", source_month="2024-01")  # รันซ้ำ

    count = conn.execute("SELECT COUNT(*) FROM juristic_person").fetchone()[0]
    conn.close()

    assert count == 1  # UNIQUE(reg_id, status, source_month) กันซ้ำ


def test_load_csv_into_db_returns_zero_for_empty_csv(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    n = load_csv_into_db(conn, "เลขทะเบียนนิติบุคคล,ชื่อนิติบุคคล (ไทย)\n", status="registration", source_month="2024-01")
    conn.close()
    assert n == 0


def test_search_juristic_person_returns_empty_when_db_missing(tmp_path):
    assert search_juristic_person("อะไรก็ได้", db_path=tmp_path / "no_such_file.db") == []


def test_is_db_available_false_when_file_missing(tmp_path):
    assert is_db_available(tmp_path / "no_such_file.db") is False


def test_is_db_available_false_when_db_empty(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.close()
    assert is_db_available(db_path) is False


def test_is_db_available_true_when_has_data(tmp_path):
    db_path = tmp_path / "has_data.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    load_csv_into_db(
        conn, "เลขทะเบียนนิติบุคคล,ชื่อนิติบุคคล (ไทย)\n123,บริษัท ก จำกัด\n",
        status="registration", source_month="2024-01",
    )
    conn.close()
    assert is_db_available(db_path) is True


# ── fetch_csv_text (mock urlopen) ──


class _FakeCsvResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_csv_text_decodes_utf8(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeCsvResponse("เลขทะเบียน,ชื่อ\n123,ทดสอบ\n".encode("utf-8"))

    monkeypatch.setattr(dbd_opendata, "urlopen", fake_urlopen)

    text = fetch_csv_text("https://example.com/test.csv")
    assert "ทดสอบ" in text


def test_fetch_csv_text_decodes_cp874_fallback(monkeypatch):
    original = "เลขทะเบียน,ชื่อ\n123,ทดสอบ\n"

    def fake_urlopen(request, timeout=None):
        return _FakeCsvResponse(original.encode("cp874"))

    monkeypatch.setattr(dbd_opendata, "urlopen", fake_urlopen)

    text = fetch_csv_text("https://example.com/test.csv")
    assert text == original


def test_fetch_csv_text_returns_none_on_404(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen(request, timeout=None):
        raise HTTPError("https://example.com/test.csv", 404, "Not Found", {}, None)

    monkeypatch.setattr(dbd_opendata, "urlopen", fake_urlopen)

    assert fetch_csv_text("https://example.com/test.csv") is None


def test_fetch_csv_text_retries_on_url_error_then_gives_up(monkeypatch):
    import time as real_time
    from urllib.error import URLError

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        raise URLError("จำลอง network error")

    monkeypatch.setattr(dbd_opendata, "urlopen", fake_urlopen)
    monkeypatch.setattr(real_time, "sleep", lambda s: None)

    logs = []
    result = fetch_csv_text("https://example.com/test.csv", log=logs.append, retries=3)

    assert result is None
    assert calls["n"] == 3
    assert any("URLError" in m for m in logs)


# ── fetch_all (mock fetch_csv_text ทั้งฟังก์ชัน — ทดสอบ orchestration/DB writing เท่านั้น) ──


def test_fetch_all_writes_to_db_and_returns_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "fetch_all.db"

    def fake_fetch(url, log=lambda m: None, retries=3, timeout=30.0):
        if "202401" in url and "registration" in url:
            return "เลขทะเบียนนิติบุคคล,ชื่อนิติบุคคล (ไทย)\n111,บริษัท ก จำกัด\n"
        return None  # เดือน/ประเภทอื่นไม่มีไฟล์

    monkeypatch.setattr(dbd_opendata, "fetch_csv_text", fake_fetch)

    summary = fetch_all(
        start_year=2024, start_month=1, end_date=(2024, 1), db_path=db_path, log=lambda m: None
    )

    assert summary["total_rows"] == 1
    assert summary["months_with_data"] == 1
    assert summary["months_tried"] == 2  # registration + dissolution สำหรับเดือนเดียว
    assert is_db_available(db_path) is True

    results = search_juristic_person("บริษัท ก", db_path=db_path)
    assert len(results) == 1
