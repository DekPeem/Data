import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import amr_mapping.dataforthai_lookup as dataforthai_lookup
from amr_mapping.dataforthai_lookup import (
    CompanySuggestion,
    _extract_business_category,
    lookup_business_category,
    suggest_companies,
)


# ── suggest_companies (HTTP GET จริงต่อ /api/suggest — mock urlopen) ──
# response JSON ตัวอย่างนี้คือรูปแบบจริงที่ยืนยันจาก DevTools Network tab ของผู้ใช้จริง
# (label/value เท่านั้น ไม่มีเลขทะเบียน/ประเภทธุรกิจ)
_SAMPLE_SUGGEST_RESPONSE = json.dumps(
    [
        {"label": "บริษัท ทดสอบ เอ จำกัด", "value": "ทดสอบ เอ"},
        {"label": "บริษัท ทดสอบ บี จำกัด (มหาชน)", "value": "ทดสอบ บี"},
    ]
).encode("utf-8")


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_suggest_companies_parses_real_response_shape(monkeypatch):
    captured_urls = []

    def fake_urlopen(request, timeout=None):
        captured_urls.append(request.full_url)
        return _FakeResponse(_SAMPLE_SUGGEST_RESPONSE)

    monkeypatch.setattr(dataforthai_lookup, "urlopen", fake_urlopen)

    results = suggest_companies("ทดสอบ")

    assert len(captured_urls) == 1
    assert captured_urls[0] == "https://www.dataforthai.com/api/suggest?q=%E0%B8%97%E0%B8%94%E0%B8%AA%E0%B8%AD%E0%B8%9A"
    assert results == [
        CompanySuggestion(label="บริษัท ทดสอบ เอ จำกัด", value="ทดสอบ เอ"),
        CompanySuggestion(label="บริษัท ทดสอบ บี จำกัด (มหาชน)", value="ทดสอบ บี"),
    ]


def test_suggest_companies_returns_empty_list_on_network_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise OSError("จำลอง network error")

    monkeypatch.setattr(dataforthai_lookup, "urlopen", fake_urlopen)

    assert suggest_companies("อะไรก็ได้") == []


def test_suggest_companies_returns_empty_list_on_invalid_json(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse(b"not valid json at all")

    monkeypatch.setattr(dataforthai_lookup, "urlopen", fake_urlopen)

    assert suggest_companies("อะไรก็ได้") == []


def test_suggest_companies_skips_malformed_items(monkeypatch):
    response = json.dumps(
        [
            {"label": "บริษัท ดี จำกัด", "value": "ดี"},
            {"label": "", "value": ""},  # แถวว่าง — ต้องข้าม
            {"value": "ไม่มี label"},  # ไม่มี label — ต้องข้าม
            "ไม่ใช่ dict เลย",  # ต้องข้าม
        ]
    ).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        return _FakeResponse(response)

    monkeypatch.setattr(dataforthai_lookup, "urlopen", fake_urlopen)

    results = suggest_companies("ดี")
    assert len(results) == 1
    assert results[0].label == "บริษัท ดี จำกัด"


# ── _extract_business_category (ทดสอบด้วยข้อความจริงจาก screenshot ของผู้ใช้) ──


def test_extract_business_category_from_real_page_text_shape():
    # โครงสร้างข้อความจริงที่เห็นในหน้ารายละเอียดบริษัท (ตัด/ปรับเล็กน้อยให้เป็นตัวอย่างสมมติ
    # แต่รูปแบบ label เดียวกับที่ยืนยันจาก screenshot จริง)
    body_text = (
        "ข้อมูลผู้ประกอบการ\n"
        "บริษัท ทดสอบ จำกัด (มหาชน)\n"
        "TEST PUBLIC COMPANY LIMITED\n"
        "เลขทะเบียน 0107542000011\n"
        "ประกอบธุรกิจ ประกอบกิจการภัตตาคาร ร้านอาหาร\n"
        "หมวดธุรกิจ : การบริการด้านอาหารในภัตตาคาร/ร้านอาหาร\n"
        "ธุรกิจที่ส่งงบการเงินล่าสุด\n"
        "ดำเนินกิจการร้านค้าสะดวกซื้อ\n"
        "สถานะ ยังดำเนินกิจการอยู่\n"
    )

    category = _extract_business_category(body_text)

    assert category == "การบริการด้านอาหารในภัตตาคาร/ร้านอาหาร"


def test_extract_business_category_falls_back_to_prakob_thurakit_label():
    body_text = "ประกอบธุรกิจ: ขายส่งสินค้าอุปโภคบริโภค\nสถานะ ยังดำเนินกิจการอยู่"
    assert _extract_business_category(body_text) == "ขายส่งสินค้าอุปโภคบริโภค"


def test_extract_business_category_returns_none_when_no_label_present():
    assert _extract_business_category("ไม่มีข้อมูลที่เกี่ยวข้องเลยในหน้านี้") is None


# ── lookup_business_category (ควบคุมผ่าน fake driver — ยังไม่เคยยืนยันกับเว็บจริง ดู
#    คำเตือนใน docstring ของ dataforthai_lookup.py — เทสต์นี้แค่ยืนยัน control flow ของโค้ด
#    เราเอง ไม่ได้ยืนยันว่า selector จริงบนเว็บตรงตามที่เขียนไว้) ──


class _FakeElement:
    def __init__(self):
        self.clicked = False
        self.sent_keys = []

    def click(self):
        self.clicked = True

    def send_keys(self, text):
        self.sent_keys.append(text)


class _FakeBody:
    def __init__(self, text):
        self.text = text


class _FakeDataforthaiDriver:
    def __init__(self, input_selector="#search", suggestion_selector=None, body_text="", url_changes_to=None):
        self._input_selector = input_selector
        self._suggestion_selector = suggestion_selector
        self._body_text = body_text
        self.current_url = "https://www.dataforthai.com/business"
        self._url_changes_to = url_changes_to
        self.get_calls = []
        self._script_call_count = 0

    def get(self, url):
        self.get_calls.append(url)

    def execute_script(self, script, *args):
        self._script_call_count += 1
        if "data-dft-search-input" in script:
            return self._input_selector
        if "data-dft-suggestion-match" in script:
            if self._suggestion_selector:
                self.current_url = self._url_changes_to or self.current_url
            return self._suggestion_selector

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By

        if by == By.TAG_NAME and selector == "body":
            return _FakeBody(self._body_text)
        if selector in (self._input_selector, self._suggestion_selector):
            return _FakeElement()
        raise NoSuchElementException(selector)


def test_lookup_business_category_returns_none_when_search_input_not_found():
    driver = _FakeDataforthaiDriver(input_selector=None)
    logs = []

    result = lookup_business_category(driver, "บริษัท ทดสอบ จำกัด", log=logs.append, timeout=0.3)

    assert result is None
    assert any("ไม่พบช่องค้นหา" in m for m in logs)


def test_lookup_business_category_returns_none_when_no_suggestion_matches():
    driver = _FakeDataforthaiDriver(input_selector="#search", suggestion_selector=None, body_text="หน้าเปล่าๆ")
    logs = []

    result = lookup_business_category(driver, "บริษัท ทดสอบ จำกัด", log=logs.append, timeout=0.3)

    assert result is None
    assert any("ไม่เจอรายการแนะนำ" in m for m in logs)


def test_lookup_business_category_extracts_category_after_clicking_suggestion():
    driver = _FakeDataforthaiDriver(
        input_selector="#search",
        suggestion_selector="#suggestion-0",
        body_text="ประกอบธุรกิจ ขายอาหาร\nหมวดธุรกิจ : ร้านอาหาร\nสถานะ ดำเนินกิจการ",
        url_changes_to="https://www.dataforthai.com/company/0107542000011/",
    )
    logs = []

    result = lookup_business_category(driver, "บริษัท ทดสอบ จำกัด", log=logs.append, timeout=0.3)

    assert result == "ร้านอาหาร"
    assert any("พบหมวดธุรกิจ" in m for m in logs)
