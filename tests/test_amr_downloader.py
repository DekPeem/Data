import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import amr_mapping.amr_downloader as amr_downloader
from amr_mapping.amr_downloader import (
    build_dashboard_url,
    build_profile_url,
    extract_dashboard_params,
    generate_month_ranges,
    get_customer_profile,
    parse_business_type,
    parse_ct_vt,
)

# ตัวอย่าง snippet จำลอง (เลขบัญชี/custid/มิเตอร์เป็นค่าสมมติ ไม่ใช่ของลูกค้าจริง) —
# โครงสร้างเดียวกับที่พบจริงใน view-source ของ MainCust.aspx: ค่าฝังอยู่ทั้งในฟังก์ชัน
# JS openUrl() และใน src ของ <iframe id="frmMain">
_SAMPLE_MAINCUST_HTML = """
<script type="text/javascript">
function openUrl(url) {
    var param = "?CustCode=019900000001&Custid=11111";
    document.getElementById("frmMain").src = url + param;
}
</script>
...
<iframe id="frmMain" name="frmMain" src="./CustDashboard.aspx?CustCode=019900000001&Custid=11111&PeaNo=99999999"></iframe>
"""


def test_extract_dashboard_params_from_sample_page():
    params = extract_dashboard_params(_SAMPLE_MAINCUST_HTML)
    assert params == {"custcode": "019900000001", "custid": "11111", "peano": "99999999"}


def test_extract_dashboard_params_missing_values():
    params = extract_dashboard_params("<html>ไม่มีข้อมูลที่ต้องการ</html>")
    assert params == {"custcode": None, "custid": None, "peano": None}


def test_build_dashboard_url_with_peano():
    url = build_dashboard_url("019900000001", "11111", "99999999")
    assert url == (
        "https://www.amr.pea.co.th/AMRWEB/CustDashboard.aspx"
        "?CustCode=019900000001&Custid=11111&PeaNo=99999999"
    )


def test_build_dashboard_url_without_peano():
    url = build_dashboard_url("019900000001", "11111")
    assert url == "https://www.amr.pea.co.th/AMRWEB/CustDashboard.aspx?CustCode=019900000001&Custid=11111"


def test_generate_month_ranges_still_works():
    # regression กันไว้เฉยๆ เพราะแก้ไฟล์เดียวกัน
    assert generate_month_ranges("2026-02-01", "2026-02-28") == [("01/02/2026", "28/02/2026")]


def test_build_profile_url():
    url = build_profile_url("019900000001", "22222")
    assert url == "https://www.amr.pea.co.th/AMRWEB/CustProfile.aspx?CustCode=019900000001&Custid=22222"


def test_parse_business_type_with_colon():
    code, name = parse_business_type("34111 : การผลิตเยื่อกระดาษ กระดาษ และกระดาษแข็งด้วยเครื่อง")
    assert code == "34111"
    assert name == "การผลิตเยื่อกระดาษ กระดาษ และกระดาษแข็งด้วยเครื่อง"


def test_parse_business_type_without_colon():
    assert parse_business_type("63201") == ("63201", "")


def test_parse_business_type_empty():
    assert parse_business_type("") == ("", "")
    assert parse_business_type(None) == ("", "")


def test_parse_ct_vt_valid():
    ct, vt = parse_ct_vt("100/5 A. , 115000/115 V.")
    assert ct == "100/5 A."
    assert vt == "115000/115 V."


def test_parse_ct_vt_invalid():
    assert parse_ct_vt("ไม่ใช่รูปแบบที่คาดไว้") == (None, None)
    assert parse_ct_vt("") == (None, None)


class _FakeElement:
    def __init__(self, text):
        self.text = text


class _FakeDriver:
    """ตัวแทน Selenium WebDriver สำหรับทดสอบ get_customer_profile โดยไม่ต้องมี Chrome จริง"""

    def __init__(self, field_map):
        self.field_map = field_map
        self.get_calls = []

    def get(self, url):
        self.get_calls.append(url)

    def find_element(self, by, value):
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By

        assert by == By.ID
        if value in self.field_map:
            return _FakeElement(self.field_map[value])
        raise NoSuchElementException(value)


# ค่าจำลอง (ไม่ใช่ของลูกค้าจริง) โครงสร้างเดียวกับ element id จริงที่พบในหน้า
# CustProfile.aspx จริง — เว้นบางฟิลด์ว่างไว้เหมือนสถานการณ์จริง (เบอร์โทร/แฟกซ์/อีเมล
# มักว่างเปล่า) เพื่อทดสอบ fallback เป็นสตริงว่าง
_SAMPLE_PROFILE_FIELDS = {
    "lblSitename": "กฟส.ทดสอบ",
    "lblCustomerAcct": "019900000001",
    "lblCustomerName": "บริษัท ทดสอบ จำกัด",
    "lblCustomerAdd": "อ.ทดสอบ จ.ทดสอบ",
    "lblCustomerBussType": "40",
    "lblCustomerAcctT": "TOU",
    "lblCustomerTypeBuss": "34111 : การผลิตทดสอบ",
    "lblCustomerRateType": "กิจการขนาดใหญ่",
    "lblCustomerMeterNo": "11111111",
    "lblCustomerCTVT": "100/5 A. , 115000/115 V.",
    "lblCustomerKVA": "15000",
    "lblCustomerReset": "วันที่ 1",
}


def test_get_customer_profile_maps_fields_and_splits_business_type():
    driver = _FakeDriver(_SAMPLE_PROFILE_FIELDS)
    logs = []

    profile = get_customer_profile(driver, "019900000001", "22222", log=logs.append)

    assert driver.get_calls == [
        "https://www.amr.pea.co.th/AMRWEB/CustProfile.aspx?CustCode=019900000001&Custid=22222"
    ]
    assert profile["rate_code"] == "40"
    assert profile["business_type_code"] == "34111"
    assert profile["business_type_name"] == "การผลิตทดสอบ"
    assert profile["kva"] == "15000"
    assert profile["meter_no"] == "11111111"
    assert profile["ct_vt"] == "100/5 A. , 115000/115 V."
    # ฟิลด์ที่ไม่มีอยู่ใน field_map (เบอร์โทร ฯลฯ) ต้อง fallback เป็นสตริงว่าง ไม่ error
    assert profile["phone"] == ""
    assert profile["email"] == ""
    assert any(logs)  # มี log อย่างน้อย 1 บรรทัด


class _FakeClickable:
    def __init__(self, value=None, text=""):
        self._value = value
        self.text = text
        self.clicked = False

    def get_attribute(self, name):
        return self._value if name == "value" else None

    def click(self):
        self.clicked = True


class _FakeElement:
    def __init__(self, text=""):
        self.text = text


class _FakeShowPageDriver:
    """ตัวแทน driver สำหรับทดสอบ _try_download_from_show_page (ไม่มี popup เปิดขึ้นเลย
    ในทุกเทสต์นี้ — window_handles คงที่ตลอด)"""

    def __init__(self, inputs=None, anchors=None, buttons=None, iframes=None, tables=None, body_text=""):
        self._inputs = inputs or []
        self._anchors = anchors or []
        self._buttons = buttons or []
        self._iframes = iframes or []
        self._tables = tables or []
        self.window_handles = ["main"]
        self.current_url = "https://www.amr.pea.co.th/AMRWEB/showPeriodProfile.aspx"
        self.title = "AMR::Automatic Meter Reading"
        self._body = _FakeElement(text=body_text)

    def find_elements(self, by, tag):
        if tag == "input":
            return self._inputs
        if tag == "a":
            return self._anchors
        if tag == "button":
            return self._buttons
        if tag == "iframe":
            return self._iframes
        if tag == "table":
            return self._tables
        return []

    def find_element(self, by, tag):
        if tag == "body":
            return self._body
        raise ValueError(f"unexpected tag: {tag}")


def test_try_download_from_show_page_clicks_matching_input_button(monkeypatch):
    btn = _FakeClickable(value="Download Excel")
    driver = _FakeShowPageDriver(inputs=[btn])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60: "/tmp/fake_downloaded.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)  # ข้าม sleep จริงตอนเทสต์

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert btn.clicked is True
    assert result == "/tmp/fake_downloaded.xls"


def test_try_download_from_show_page_clicks_matching_anchor_link(monkeypatch):
    link = _FakeClickable(text="ดาวน์โหลดข้อมูล")
    driver = _FakeShowPageDriver(anchors=[link])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60: "/tmp/fake2.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert link.clicked is True
    assert result == "/tmp/fake2.xls"


def test_try_download_from_show_page_clicks_matching_button_element(monkeypatch):
    """ยืนยันจากผู้ใช้จริง: หน้ารายงานบางหน้ามีปุ่ม "Download" ที่เป็น <button> แยกต่างหาก
    (ไม่ใช่ <input>/<a> แบบที่เคยรองรับ) ต้องสแกนเจอและกดได้เหมือนกัน"""

    btn = _FakeClickable(text="Download")
    driver = _FakeShowPageDriver(buttons=[btn])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60: "/tmp/fake3.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert btn.clicked is True
    assert result == "/tmp/fake3.xls"


def test_cache_key_is_deterministic_and_filesystem_safe():
    key = amr_downloader._cache_key("019900000001", "M/1", "01/07/2026", "31/07/2026")
    assert key == "019900000001_M-1_01-07-2026_31-07-2026"
    # เรียกซ้ำด้วยอินพุตเดิมต้องได้ผลเหมือนเดิมเป๊ะ (deterministic) — จุดสำคัญของการทำ cache
    assert amr_downloader._cache_key("019900000001", "M/1", "01/07/2026", "31/07/2026") == key


def test_find_cached_file_returns_none_when_missing(tmp_path):
    assert amr_downloader._find_cached_file(str(tmp_path), "no-such-key") is None


def test_find_cached_file_finds_existing_file_ignoring_extension(tmp_path):
    (tmp_path / "some-key.xls").write_text("data", encoding="utf-8")
    found = amr_downloader._find_cached_file(str(tmp_path), "some-key")
    assert found == str(tmp_path / "some-key.xls")


def test_download_reports_for_account_skips_redownload_on_cache_hit(monkeypatch, tmp_path):
    """ดาวน์โหลดบัญชี+มิเตอร์+ช่วงวันที่เดิมซ้ำสองรอบ — รอบสองต้องไม่เรียก download_month
    อีกเลย (ใช้ไฟล์ที่แคชไว้จากรอบแรกแทน) ตามที่ผู้ใช้ขอ (ไม่ต้องดาวน์โหลดซ้ำ)"""

    download_dir = str(tmp_path)
    monkeypatch.setattr(
        amr_downloader, "get_meter_options",
        lambda driver, account, log=lambda m: None: [{"value": "M1", "text": "มิเตอร์ 1"}],
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    call_count = {"n": 0}

    def fake_download_month(driver, cust_code, meter_point, meter_text, date_from, date_to, dl_dir, log):
        call_count["n"] += 1
        path = os.path.join(dl_dir, f"raw_download_{call_count['n']}.xls")
        with open(path, "w", encoding="utf-8") as f:
            f.write("ข้อมูลดิบจำลอง")
        return path

    monkeypatch.setattr(amr_downloader, "download_month", fake_download_month)

    month_ranges = [("01/07/2026", "31/07/2026")]

    results1 = amr_downloader._download_reports_for_account(None, "ACC1", month_ranges, download_dir, log=lambda m: None)
    assert call_count["n"] == 1
    assert results1[0].success
    assert results1[0].file_path is not None

    results2 = amr_downloader._download_reports_for_account(None, "ACC1", month_ranges, download_dir, log=lambda m: None)
    assert call_count["n"] == 1, "รอบสองต้องไม่ดาวน์โหลดซ้ำ ต้องใช้ไฟล์แคชจากรอบแรกแทน"
    assert results2[0].success
    assert results2[0].file_path == results1[0].file_path


def test_download_reports_for_account_retries_whole_month_after_transient_failure(monkeypatch, tmp_path):
    """ยืนยันจากผู้ใช้จริง: บัญชี/เดือนเดียวกัน บางรอบดาวน์โหลดไม่สำเร็จ บางรอบสำเร็จ ทั้งที่ไม่ได้
    เปลี่ยนอะไรเลย — ต้องลองใหม่ทั้งเดือน (โหลดหน้าใหม่) ก่อนจะยอมแพ้ ไม่ใช่เจอไม่สำเร็จครั้งเดียว
    แล้วเลิกเลย"""

    download_dir = str(tmp_path)
    monkeypatch.setattr(
        amr_downloader, "get_meter_options",
        lambda driver, account, log=lambda m: None: [{"value": "M1", "text": "มิเตอร์ 1"}],
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    call_count = {"n": 0}

    def flaky_download_month(driver, cust_code, meter_point, meter_text, date_from, date_to, dl_dir, log):
        call_count["n"] += 1
        if call_count["n"] < 2:  # รอบแรกไม่สำเร็จ (จำลองหาปุ่มไม่เจอ/หน้าโหลดไม่ทัน)
            return None
        path = os.path.join(dl_dir, "raw_download.xls")
        with open(path, "w", encoding="utf-8") as f:
            f.write("ข้อมูลดิบจำลอง")
        return path

    monkeypatch.setattr(amr_downloader, "download_month", flaky_download_month)

    month_ranges = [("01/07/2026", "31/07/2026")]
    results = amr_downloader._download_reports_for_account(None, "ACC1", month_ranges, download_dir, log=lambda m: None)

    assert call_count["n"] == 2, "ต้องลองใหม่ทั้งเดือนหลังรอบแรกไม่สำเร็จ"
    assert results[0].success is True
    assert results[0].file_path is not None


def test_download_reports_for_account_gives_up_after_max_attempts(monkeypatch, tmp_path):
    download_dir = str(tmp_path)
    monkeypatch.setattr(
        amr_downloader, "get_meter_options",
        lambda driver, account, log=lambda m: None: [{"value": "M1", "text": "มิเตอร์ 1"}],
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    call_count = {"n": 0}

    def always_fails(driver, cust_code, meter_point, meter_text, date_from, date_to, dl_dir, log):
        call_count["n"] += 1
        return None

    monkeypatch.setattr(amr_downloader, "download_month", always_fails)

    month_ranges = [("01/07/2026", "31/07/2026")]
    results = amr_downloader._download_reports_for_account(None, "ACC1", month_ranges, download_dir, log=lambda m: None)

    assert call_count["n"] == amr_downloader._MAX_MONTH_ATTEMPTS
    assert results[0].success is False
    assert results[0].file_path is None


def test_try_download_from_show_page_no_matching_element_returns_none(monkeypatch):
    unrelated = _FakeClickable(value="Cancel")
    driver = _FakeShowPageDriver(inputs=[unrelated])

    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    # timeout=0 กันไม่ให้เทสต์นี้ต้องรอจริงตามค่า default (15 วินาที) ของ retry loop
    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None, timeout=0)

    assert unrelated.clicked is False
    assert result is None


def test_try_download_from_show_page_logs_diagnostics_when_not_found(monkeypatch):
    """ยืนยันจากผู้ใช้จริง: บางครั้งหน้าเว็บมีข้อมูล+ปุ่ม Download อยู่จริง (เช็คด้วยตาเองแล้ว)
    แต่ _find_download_element ยังหาไม่เจอ ยังไม่ทราบสาเหตุแน่ชัด — เก็บรายละเอียดหน้า (url/
    title/จำนวน element ต่างๆ/ข้อความในหน้า) ไว้ใน log ตอนหาไม่เจอ เพื่อวินิจฉัยจากของจริงได้
    ในครั้งต่อไป แทนที่จะรู้แค่ว่า "ไม่เจอ" เฉยๆ"""

    driver = _FakeShowPageDriver(
        iframes=[object()], tables=[object(), object()], body_text="เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่"
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    logs = []
    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=logs.append, timeout=0)

    assert result is None
    joined = "\n".join(logs)
    assert "iframe=1" in joined
    assert "table=2" in joined
    assert driver.current_url in joined
    assert "เซสชันหมดอายุ" in joined


def test_try_download_from_show_page_retries_until_element_appears(monkeypatch):
    """ยืนยันจากผู้ใช้จริง: บัญชี/เดือนเดียวกัน บางรอบหาปุ่มเจอ บางรอบไม่เจอ ทั้งที่หน้าเว็บมี
    ปุ่มอยู่จริงเหมือนกันทุกครั้ง (โหลดหน้าช้าไม่คงที่) — ต้องรอ+ลองสแกนใหม่ได้ ไม่ใช่ scan
    ครั้งเดียวแล้วยอมแพ้เลย"""

    btn = _FakeClickable(text="Download")
    driver = _FakeShowPageDriver()  # ยังไม่มีปุ่มปรากฏเลยตอนเริ่ม (จำลองหน้าโหลดช้า)

    button_scan_count = {"n": 0}
    real_find_elements = driver.find_elements

    def delayed_find_elements(by, tag):
        if tag == "button":
            button_scan_count["n"] += 1
            if button_scan_count["n"] >= 2:  # ปุ่มปรากฏตั้งแต่รอบสแกนที่ 2 เป็นต้นไป (รอบแรกยังไม่เจอ)
                driver._buttons = [btn]
        return real_find_elements(by, tag)

    driver.find_elements = delayed_find_elements

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60: "/tmp/fake4.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)
    monkeypatch.setattr(amr_downloader.time, "sleep", lambda s: None)  # ข้าม sleep จริงระหว่าง retry

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None, timeout=5)

    assert btn.clicked is True
    assert result == "/tmp/fake4.xls"
