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
    suggest_companies_with_fallback,
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


def test_suggest_companies_leaves_parentheses_unescaped_like_browser(monkeypatch):
    """ยืนยันจาก URL จริงที่ผู้ใช้ capture จาก DevTools Network tab: เบราว์เซอร์ (encodeURIComponent
    ของ JS) ไม่เข้ารหัสวงเล็บ "(" ")" เป็น %28/%29 — โค้ดฝั่งเราต้องส่ง URL แบบเดียวกัน เผื่อ
    ฝั่งเซิร์ฟเวอร์สนใจความต่างของการเข้ารหัสนี้"""

    captured_urls = []

    def fake_urlopen(request, timeout=None):
        captured_urls.append(request.full_url)
        return _FakeResponse(b"[]")

    monkeypatch.setattr(dataforthai_lookup, "urlopen", fake_urlopen)

    suggest_companies("บริษัท ซีพี ออลล์ จำกัด (มหาชน)")

    assert "(" in captured_urls[0] and ")" in captured_urls[0]
    assert "%28" not in captured_urls[0] and "%29" not in captured_urls[0]


# ── suggest_companies_with_fallback (ลองคำค้นหากว้างขึ้นเรื่อยๆ ถ้าชื่อเต็มไม่เจอ) ──


def test_suggest_companies_with_fallback_returns_first_successful_result(monkeypatch):
    """ยืนยันจากผู้ใช้จริง: ค้นด้วยชื่อเต็มพร้อมคำนำหน้า/ต่อท้ายนิติบุคคล (เช่น "บริษัท ซีพี ออลล์
    จำกัด (มหาชน)") ไม่เจอผลลัพธ์เลย ทั้งที่บริษัทนี้มีอยู่จริงแน่ๆ — ต้องลองคำค้นหาที่กว้างขึ้น
    เรื่อยๆ (ตัดคำนำหน้า/ต่อท้ายออกก่อน) จนกว่าจะเจอ ไม่ใช่ยอมแพ้ตั้งแต่ครั้งแรก"""

    calls = []

    def fake_suggest(query, timeout=10.0):
        calls.append(query)
        if query == "ซีพี ออลล์":
            return [CompanySuggestion(label="บริษัท ซีพี ออลล์ จำกัด (มหาชน)", value="ซีพี ออลล์")]
        return []

    monkeypatch.setattr(dataforthai_lookup, "suggest_companies", fake_suggest)

    logs = []
    results = suggest_companies_with_fallback("บริษัท ซีพี ออลล์ จำกัด (มหาชน)", log=logs.append)

    assert len(results) == 1
    assert results[0].value == "ซีพี ออลล์"
    assert calls[0] == "บริษัท ซีพี ออลล์ จำกัด (มหาชน)"  # ต้องลองชื่อเต็มก่อนเสมอ
    assert "ซีพี ออลล์" in calls  # แล้วค่อยลองแบบตัดคำนำหน้า/ต่อท้ายออก
    assert any("ลองค้นหาอีกครั้งด้วยคำค้นหาที่กว้างขึ้น" in m for m in logs)


def test_suggest_companies_with_fallback_returns_empty_when_all_terms_fail(monkeypatch):
    monkeypatch.setattr(dataforthai_lookup, "suggest_companies", lambda query, timeout=10.0: [])

    results = suggest_companies_with_fallback("บริษัท ตัวอย่างที่ไม่มีอยู่จริง จำกัด")

    assert results == []


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
        if "querySelectorAll('input')" in script:
            return []  # dump diagnostics — ไม่มี input เลยในเทสต์นี้

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By

        if by == By.TAG_NAME and selector == "body":
            return _FakeBody(self._body_text)
        if selector in (self._input_selector, self._suggestion_selector):
            return _FakeElement()
        raise NoSuchElementException(selector)


def _install_fake_clock(monkeypatch):
    """แทน time.sleep/time.time ด้วยนาฬิกาจำลอง — กันไม่ให้เทสต์ที่ทำให้โค้ดต้องวนลูปรอ
    (เช่นรอช่องค้นหาที่ไม่มีวันปรากฏ ~10 วินาที) ต้องรอเวลาจริง"""

    fake_clock = {"t": 0.0}

    def fake_sleep(seconds):
        fake_clock["t"] += seconds

    monkeypatch.setattr(dataforthai_lookup.time, "sleep", fake_sleep)
    monkeypatch.setattr(dataforthai_lookup.time, "time", lambda: fake_clock["t"])


def test_lookup_business_category_returns_none_when_search_input_not_found(monkeypatch):
    driver = _FakeDataforthaiDriver(input_selector=None)
    logs = []
    _install_fake_clock(monkeypatch)

    result = lookup_business_category(driver, "บริษัท ทดสอบ จำกัด", log=logs.append, timeout=0.3)

    assert result is None
    assert any("ไม่พบช่องค้นหา" in m for m in logs)
    assert any("ไม่มี <input> เลยสักตัว" in m for m in logs)


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
