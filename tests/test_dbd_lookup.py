import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import amr_mapping.dbd_lookup as dbd_lookup
from amr_mapping.dbd_lookup import (
    CompanyBusinessInfo,
    _fallback_search_terms,
    _strip_legal_form,
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


def test_strip_legal_form_removes_prefix_abbreviation():
    assert _strip_legal_form("หจก. ตัวอย่าง เอ แอนด์ บี") == "ตัวอย่าง เอ แอนด์ บี"


def test_strip_legal_form_removes_full_prefix_and_suffix():
    assert _strip_legal_form("บริษัท ทดสอบ จำกัด") == "ทดสอบ"


def test_strip_legal_form_removes_long_prefix_before_short_one():
    """ต้องตัด "ห้างหุ้นส่วนจำกัด" (รูปเต็ม) ไม่ใช่พยายามตัด "หจก." ซึ่งไม่ตรงอยู่แล้วถ้าพิมพ์เต็มมา"""
    assert _strip_legal_form("ห้างหุ้นส่วนจำกัด ตัวอย่าง เอ แอนด์ บี") == "ตัวอย่าง เอ แอนด์ บี"


def test_strip_legal_form_returns_none_when_nothing_to_strip():
    assert _strip_legal_form("ชื่อธรรมดาไม่มีคำนำหน้า") is None


def test_fallback_search_terms_strips_legal_form_first_then_shortens():
    terms = _fallback_search_terms("บริษัท ตัวอย่าง เอ บี ซี จำกัด")
    # ลำดับต้องเป็น: ตัด legal form ก่อน แล้วค่อยตัดคำท้ายทีละคำ จนเหลือคำแรกคำเดียว
    assert terms == ["ตัวอย่าง เอ บี ซี", "ตัวอย่าง เอ บี", "ตัวอย่าง เอ", "ตัวอย่าง"]


def test_fallback_search_terms_skips_candidates_shorter_than_min_length():
    """ตัดจนเหลือคำเดียวที่สั้นกว่า _MIN_FALLBACK_KEYWORD_LEN (เช่น 1 ตัวอักษร) ต้องไม่ถูกเสนอ
    เป็นคำค้นหาสำรอง (กว้างเกินไปจนไม่มีประโยชน์ อาจได้ผลลัพธ์เป็นพันรายการ)"""
    terms = _fallback_search_terms("บริษัท ก บ จำกัด")
    assert "ก" not in terms


def test_fallback_search_terms_empty_for_single_word_name_with_no_legal_form():
    assert _fallback_search_terms("ไม่มีบริษัทนี้แน่นอน") == []


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


class _FakeFallbackDriver(_FakeSearchDriver):
    """จำลองเคส: คำค้นหารอบแรก (เช่น "หจก. ชื่อ") ไม่พบผลลัพธ์เลย แต่คำค้นหารอบสอง (ตัดคำนำหน้า/
    ต่อท้ายประเภทนิติบุคคลออกแล้ว) พบ — เพื่อทดสอบ fallback ใน search_company_business_type"""

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        if len(self.get_calls) < 2:
            raise NoSuchElementException(selector)
        return _FakeRow(self._rows_cells[0])

    def find_elements(self, by, selector):
        if len(self.get_calls) < 2:
            return []
        return [_FakeRow(cells) for cells in self._rows_cells]


def test_search_company_business_type_retries_without_legal_form_when_first_search_empty():
    from urllib.parse import unquote

    driver = _FakeFallbackDriver()
    logs = []

    results = search_company_business_type(driver, "หจก. ตัวอย่าง เอ แอนด์ บี", log=logs.append, timeout=0.5)

    assert len(driver.get_calls) == 2
    assert "หจก." not in unquote(driver.get_calls[1])
    assert len(results) == 1
    assert any("ลองค้นหาอีกครั้ง" in m for m in logs)


def test_search_company_business_type_does_not_retry_when_name_has_no_legal_form():
    """ถ้าชื่อที่พิมพ์ไม่มีคำนำหน้า/ต่อท้ายประเภทนิติบุคคลให้ตัดเลย ไม่ควรค้นหาซ้ำคำเดิมโดยเปล่า
    ประโยชน์ (เสียเวลาเปิดหน้าเว็บซ้ำ)"""

    driver = _FakeSearchDriver(present=False)

    results = search_company_business_type(driver, "ไม่มีบริษัทนี้แน่นอน", timeout=0.5)

    assert results == []
    assert len(driver.get_calls) == 1


class _FakeNthCallSucceedsDriver(_FakeSearchDriver):
    """คืนผลลัพธ์ว่างสำหรับ (succeed_at_call - 1) ครั้งแรก แล้วเจอผลลัพธ์ตั้งแต่ครั้งที่
    succeed_at_call เป็นต้นไป — ใช้ทดสอบว่า fallback ไล่ลองคำค้นหาหลายแบบเรียงลำดับถูกต้องก่อนเจอ
    (ยืนยันจากการทดสอบจริงบนเว็บ DBD ว่าบางครั้งต้องตัดคำท้ายมากกว่า 1 คำถึงจะเจอ)"""

    def __init__(self, succeed_at_call, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._succeed_at_call = succeed_at_call

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        if len(self.get_calls) < self._succeed_at_call:
            raise NoSuchElementException(selector)
        return _FakeRow(self._rows_cells[0])

    def find_elements(self, by, selector):
        if len(self.get_calls) < self._succeed_at_call:
            return []
        return [_FakeRow(cells) for cells in self._rows_cells]


def test_search_company_business_type_progressively_shortens_keyword_until_found():
    from urllib.parse import unquote

    driver = _FakeNthCallSucceedsDriver(succeed_at_call=3)
    logs = []

    results = search_company_business_type(
        driver, "บริษัท ตัวอย่าง เอ บี ซี จำกัด", log=logs.append, timeout=0.5
    )

    calls = [unquote(u.split("keyword=")[1]) for u in driver.get_calls]
    assert calls == ["บริษัท ตัวอย่าง เอ บี ซี จำกัด", "ตัวอย่าง เอ บี ซี", "ตัวอย่าง เอ บี"]
    assert len(results) == 1


def test_search_company_business_type_returns_empty_when_every_fallback_term_fails():
    driver = _FakeSearchDriver(present=False)

    results = search_company_business_type(driver, "บริษัท ตัวอย่าง เอ บี ซี จำกัด", timeout=0.5)

    assert results == []
    # ต้องลองครบทุกคำ: ชื่อเต็ม + 4 คำสำรอง (ตัด legal form + ตัดคำท้ายทีละคำจนเหลือคำเดียว) = 5 ครั้ง
    assert len(driver.get_calls) == 5


