import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import amr_mapping.dbd_lookup as dbd_lookup
from amr_mapping.dbd_lookup import (
    CompanyBusinessInfo,
    build_search_url,
    find_exact_match,
    search_company_business_type,
)


def test_build_search_url_encodes_thai_keyword():
    url = build_search_url("บริษัท ทดสอบ จำกัด")
    assert url.startswith("https://datawarehouse.dbd.go.th/juristic/searchInfo?keyword=")
    assert " " not in url  # ต้อง URL-encode ช่องว่าง/อักขระไทยแล้ว


def test_tsic_division_code_takes_first_two_digits():
    info = CompanyBusinessInfo(
        registration_no="0105544000157", juristic_name="กฎหมายเอสซีจี จำกัด",
        juristic_type="บริษัทจำกัด", status="ยังดำเนินกิจการอยู่",
        tsic_code="69100", tsic_name_th="กิจกรรมทางกฎหมาย",
    )
    assert info.tsic_division_code == "69"


def test_tsic_division_code_none_when_code_too_short():
    info = CompanyBusinessInfo(
        registration_no="x", juristic_name="x", juristic_type="x", status="x",
        tsic_code="", tsic_name_th="",
    )
    assert info.tsic_division_code is None


def test_find_exact_match_ignores_case_and_whitespace():
    results = [
        CompanyBusinessInfo("1", "  บริษัท ทดสอบ จำกัด  ", "บริษัทจำกัด", "ยังดำเนินกิจการอยู่", "12345", "x"),
        CompanyBusinessInfo("2", "บริษัท อื่น จำกัด", "บริษัทจำกัด", "ยังดำเนินกิจการอยู่", "99999", "y"),
    ]
    match = find_exact_match(results, "บริษัท ทดสอบ จำกัด")
    assert match is not None
    assert match.registration_no == "1"


def test_find_exact_match_returns_none_when_no_exact_hit():
    results = [
        CompanyBusinessInfo("1", "บริษัท ทดสอบ กรุ๊ป จำกัด", "บริษัทจำกัด", "ยังดำเนินกิจการอยู่", "12345", "x"),
    ]
    assert find_exact_match(results, "บริษัท ทดสอบ จำกัด") is None


# ── fake Selenium driver (ไม่ต้องมี Chrome จริง) — เลียนแบบโครงสร้าง DOM จริงที่ยืนยันแล้ว
#    จากหน้า datawarehouse.dbd.go.th/juristic/searchInfo (11 คอลัมน์ต่อแถว) ──


class _FakeCell:
    def __init__(self, text):
        self.text = text


class _FakeRow:
    def __init__(self, cell_texts):
        self._cells = [_FakeCell(t) for t in cell_texts]

    def find_elements(self, by, tag):
        assert tag == "td"
        return self._cells


_SAMPLE_ROW_CELLS = [
    "",  # ปุ่มเปรียบเทียบ (ไอคอน ไม่มีข้อความ)
    "1",  # ลำดับที่
    "0105544000157",  # เลขทะเบียนนิติบุคคล
    "กฎหมายเอสซีจี จำกัด",  # ชื่อนิติบุคคล
    "บริษัทจำกัด",  # ประเภทนิติบุคคล
    "ยังดำเนินกิจการอยู่",  # สถานะ
    "69100",  # รหัสประเภทธุรกิจ (TSIC)
    "กิจกรรมทางกฎหมาย",  # ชื่อประเภทธุรกิจ
    "20,000,000.00",  # ทุนจดทะเบียน
    "269,287,016.00",  # สินทรัพย์รวม
    "48,314,486.00",  # รายได้รวม
]


class _FakeSearchDriver:
    """ตัวแทน driver ที่มีผลลัพธ์ให้พบ (present=True) หรือหาไม่พบเลย (present=False) —
    เลียนแบบพฤติกรรมที่ WebDriverWait/expected_conditions ต้องการ (find_element ต้อง raise
    NoSuchElementException เมื่อยังไม่เจอ ไม่ใช่คืน None)"""

    def __init__(self, rows_cells=None, present=True):
        self._rows_cells = rows_cells if rows_cells is not None else [_SAMPLE_ROW_CELLS]
        self._present = present
        self.get_calls = []

    def get(self, url):
        self.get_calls.append(url)

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        if not self._present or not self._rows_cells:
            raise NoSuchElementException(selector)
        return _FakeRow(self._rows_cells[0])

    def find_elements(self, by, selector):
        if not self._present:
            return []
        return [_FakeRow(cells) for cells in self._rows_cells]


def test_search_company_business_type_parses_rendered_table():
    driver = _FakeSearchDriver()
    logs = []

    results = search_company_business_type(driver, "SCG", log=logs.append, timeout=1)

    assert driver.get_calls == ["https://datawarehouse.dbd.go.th/juristic/searchInfo?keyword=SCG"]
    assert len(results) == 1
    r = results[0]
    assert r.registration_no == "0105544000157"
    assert r.juristic_name == "กฎหมายเอสซีจี จำกัด"
    assert r.tsic_code == "69100"
    assert r.tsic_name_th == "กิจกรรมทางกฎหมาย"
    assert any(logs)  # มี log อย่างน้อย 1 บรรทัด


def test_search_company_business_type_multiple_rows():
    second_row = list(_SAMPLE_ROW_CELLS)
    second_row[2] = "0963544000247"
    second_row[3] = "จี เอส ซี กรุ๊ป"
    second_row[6] = "41002"
    second_row[7] = "การก่อสร้างอาคารที่ไม่ใช่ที่พักอาศัย"

    driver = _FakeSearchDriver(rows_cells=[_SAMPLE_ROW_CELLS, second_row])
    results = search_company_business_type(driver, "SCG", timeout=1)

    assert len(results) == 2
    assert results[1].tsic_code == "41002"


def test_search_company_business_type_no_results_returns_empty_list():
    driver = _FakeSearchDriver(present=False)
    logs = []

    results = search_company_business_type(driver, "ไม่มีบริษัทนี้แน่นอน", log=logs.append, timeout=0.5)

    assert results == []
    assert any("ไม่พบผลลัพธ์" in m for m in logs)


def test_lookup_business_type_for_company_closes_driver_always(monkeypatch):
    """lookup_business_type_for_company (entry point ที่ web/app.py เรียก) ต้องปิด driver
    เสมอ ไม่ว่าค้นหาสำเร็จหรือ error กลางคัน"""

    closed = {"quit_called": False}

    class _FakeDriver(_FakeSearchDriver):
        def quit(self):
            closed["quit_called"] = True

    fake_driver = _FakeDriver()
    monkeypatch.setattr(dbd_lookup, "setup_driver", lambda headless=True: fake_driver)

    results = dbd_lookup.lookup_business_type_for_company("SCG")

    assert closed["quit_called"] is True
    assert len(results) == 1
    assert results[0].tsic_code == "69100"


def test_lookup_business_type_for_company_closes_driver_even_on_error(monkeypatch):
    class _FakeDriver(_FakeSearchDriver):
        def quit(self):
            closed["quit_called"] = True

        def get(self, url):
            raise RuntimeError("จำลอง error ระหว่างเปิดหน้าเว็บ")

    closed = {"quit_called": False}
    fake_driver = _FakeDriver()
    monkeypatch.setattr(dbd_lookup, "setup_driver", lambda headless=True: fake_driver)

    import pytest

    with pytest.raises(RuntimeError):
        dbd_lookup.lookup_business_type_for_company("SCG")

    assert closed["quit_called"] is True


def test_search_company_business_type_skips_malformed_rows():
    """แถวที่คอลัมน์ไม่ครบ (เช่น แถวข้อความแจ้งเตือนพิเศษของเว็บ) ต้องถูกข้าม ไม่ error"""

    driver = _FakeSearchDriver(rows_cells=[["ข้อความแจ้งเตือนบางอย่าง"], _SAMPLE_ROW_CELLS])
    results = search_company_business_type(driver, "SCG", timeout=1)

    assert len(results) == 1
    assert results[0].tsic_code == "69100"
