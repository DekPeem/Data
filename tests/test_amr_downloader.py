import os
import sys
from datetime import datetime
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
    def __init__(self, value=None, text="", **attrs):
        self._value = value
        self.text = text
        self._attrs = attrs
        self.clicked = False

    def get_attribute(self, name):
        if name == "value":
            return self._value
        return self._attrs.get(name)

    def click(self):
        self.clicked = True


class _FakeElement:
    def __init__(self, text=""):
        self.text = text


class _FakeShowPageDriver:
    """ตัวแทน driver สำหรับทดสอบ _try_download_from_show_page (ไม่มี popup เปิดขึ้นเลย
    ในทุกเทสต์นี้ — window_handles คงที่ตลอด)"""

    def __init__(
        self, inputs=None, anchors=None, buttons=None, iframes=None, tables=None, body_text="", script_snippets=None
    ):
        self._inputs = inputs or []
        self._anchors = anchors or []
        self._buttons = buttons or []
        self._iframes = iframes or []
        self._tables = tables or []
        self.window_handles = ["main"]
        self.current_url = "https://www.amr.pea.co.th/AMRWEB/showPeriodProfile.aspx"
        self.title = "AMR::Automatic Meter Reading"
        self._body = _FakeElement(text=body_text)
        self._script_snippets = script_snippets if script_snippets is not None else []

    def execute_script(self, script):
        return self._script_snippets

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


def _install_fake_clock(monkeypatch):
    """แทน time.sleep/time.time ด้วยนาฬิกาจำลอง (เดินเวลาไปตามที่ sleep() เรียก แทนที่จะรอจริง) —
    ใช้กับเทสต์ที่ทำให้โค้ดต้องวนลูปรอจนหมดเวลาก่อน fallback (เช่นรอ popup ที่ไม่มีวันเปิด) ซึ่งถ้า
    mock แค่ time.sleep เฉยๆ ลูปจะ busy-spin จนกว่านาฬิกาจริงจะถึง deadline อยู่ดี (ยังช้าเท่าเดิม)"""
    fake_clock = {"t": 0.0}

    def fake_sleep(seconds):
        fake_clock["t"] += seconds

    monkeypatch.setattr(amr_downloader.time, "sleep", fake_sleep)
    monkeypatch.setattr(amr_downloader.time, "time", lambda: fake_clock["t"])


def test_try_download_from_show_page_clicks_matching_input_button(monkeypatch):
    btn = _FakeClickable(value="Download Excel")
    driver = _FakeShowPageDriver(inputs=[btn])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60, log=None, ignore_existing=None: "/tmp/fake_downloaded.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)  # ข้าม sleep จริงตอนเทสต์
    # ไม่มี popup เปิดในเทสต์นี้เลย (fallback ไปรอดาวน์โหลดตรงๆ) — ต้องใช้นาฬิกาจำลอง ไม่งั้นจะ
    # รอจริง 20 วินาทีเต็มตามลูป popup-wait ใหม่ก่อนจะ fallback (busy-spin จนถึง deadline จริง)
    _install_fake_clock(monkeypatch)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert btn.clicked is True
    assert result == "/tmp/fake_downloaded.xls"


def test_try_download_from_show_page_waits_past_5_seconds_for_slow_popup(monkeypatch):
    """ยืนยันจากผู้ใช้จริง: กดปุ่ม Download แล้ว popup "เลือกเอกสารที่ต้องการ" เปิดช้ากว่า 5
    วินาที (เดิม) ทำให้ log ขึ้น "ไม่มี popup" ทั้งที่จริงๆ เปิดแค่ช้า แล้วไปรอดาวน์โหลดไฟล์
    ตรงๆ ที่ไม่มีวันมาถึง — ต้องรอได้นานกว่า 5 วินาทีเดิม (ตอนนี้ขยายเป็น 20 วินาที)"""

    btn = _FakeClickable(value="Download")
    driver = _FakeShowPageDriver(inputs=[btn])

    sleep_calls = {"n": 0}

    def fake_sleep(seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] == 50:  # เกิน 20 ครั้ง (ขีดจำกัดเดิม) ไปมาก — ต้องยังตรวจจับได้
            driver.window_handles = ["main", "popup"]

    monkeypatch.setattr(amr_downloader.time, "sleep", fake_sleep)
    monkeypatch.setattr(
        amr_downloader, "_handle_popup", lambda driver, main_handle, download_dir, log: "/tmp/fake_slow_popup.xls"
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert btn.clicked is True
    assert result == "/tmp/fake_slow_popup.xls"


def test_try_download_from_show_page_clicks_image_input_button(monkeypatch):
    """ยืนยันจาก diagnostics จริง: หน้าที่หาปุ่มไม่เจอมี input=24 แต่ไม่มีตัวไหน value ตรงเลย
    (button=0, a=1 ก็ไม่ตรง) — น่าจะเป็น <input type="image"> ปุ่มรูปภาพที่ค่าใบ้อยู่ใน
    alt/src แทน value ต้องหาเจอด้วย"""

    img_btn = _FakeClickable(value="", alt="Download", src="images/btnDownload.gif")
    driver = _FakeShowPageDriver(inputs=[img_btn])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60, log=None, ignore_existing=None: "/tmp/fake_image_btn.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)
    _install_fake_clock(monkeypatch)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert img_btn.clicked is True
    assert result == "/tmp/fake_image_btn.xls"


def test_try_download_from_show_page_clicks_matching_anchor_link(monkeypatch):
    link = _FakeClickable(text="ดาวน์โหลดข้อมูล")
    driver = _FakeShowPageDriver(anchors=[link])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60, log=None, ignore_existing=None: "/tmp/fake2.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)
    _install_fake_clock(monkeypatch)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None)

    assert link.clicked is True
    assert result == "/tmp/fake2.xls"


def test_try_download_from_show_page_clicks_matching_button_element(monkeypatch):
    """ยืนยันจากผู้ใช้จริง: หน้ารายงานบางหน้ามีปุ่ม "Download" ที่เป็น <button> แยกต่างหาก
    (ไม่ใช่ <input>/<a> แบบที่เคยรองรับ) ต้องสแกนเจอและกดได้เหมือนกัน"""

    btn = _FakeClickable(text="Download")
    driver = _FakeShowPageDriver(buttons=[btn])

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60, log=None, ignore_existing=None: "/tmp/fake3.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)
    _install_fake_clock(monkeypatch)

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
    """ช่วงวันที่สั้น (ต่ำกว่า _MIN_SPLIT_RANGE_DAYS) แบ่งครึ่งต่อไม่ได้แล้ว — ต้องยอมแพ้จริงๆ
    หลังลองครบ _MAX_MONTH_ATTEMPTS ไม่ใช่พยายามแบ่งต่อไปเรื่อยๆ"""

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

    month_ranges = [("01/07/2026", "05/07/2026")]  # 5 วัน < _MIN_SPLIT_RANGE_DAYS (6) — แบ่งต่อไม่ได้
    results = amr_downloader._download_reports_for_account(None, "ACC1", month_ranges, download_dir, log=lambda m: None)

    assert call_count["n"] == amr_downloader._MAX_MONTH_ATTEMPTS
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].file_path is None


def test_download_reports_for_account_splits_large_range_after_max_attempts(monkeypatch, tmp_path):
    """ยืนยันจากผู้ใช้จริง: บัญชี/เดือนที่มีข้อมูลเต็มเดือน (~30 วัน) ดาวน์โหลดไฟล์ export ค้างที่
    .crdownload ขนาดเท่าเดิมเป๊ะซ้ำทุกรอบแม้ลองใหม่ทั้งหน้าครบ _MAX_MONTH_ATTEMPTS ครั้งแล้ว —
    ต่างจากปัญหาโหลดช้าแบบสุ่มที่เคยเจอ (แก้ด้วยขยาย timeout ไปแล้ว) ค่าคงที่ซ้ำเป๊ะแบบนี้ชี้ว่า
    เซิร์ฟเวอร์สร้างไฟล์ไม่ครบสำหรับ request ขนาดใหญ่ขนาดนี้โดยเฉพาะ — ต้องลองแบ่งครึ่งช่วงวันที่
    แทนที่จะยอมแพ้ไปเลย หรือลองซ้ำด้วยขนาดเดิมไปเรื่อยๆ"""

    download_dir = str(tmp_path)
    monkeypatch.setattr(
        amr_downloader, "get_meter_options",
        lambda driver, account, log=lambda m: None: [{"value": "M1", "text": "มิเตอร์ 1"}],
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    calls = []

    def always_fails(driver, cust_code, meter_point, meter_text, date_from, date_to, dl_dir, log):
        calls.append((date_from, date_to))
        return None

    monkeypatch.setattr(amr_downloader, "download_month", always_fails)

    month_ranges = [("01/07/2026", "31/07/2026")]  # 31 วัน — แบ่งครึ่งได้เรื่อยๆ จนถึง _MIN_SPLIT_RANGE_DAYS
    logs = []
    results = amr_downloader._download_reports_for_account(
        None, "ACC1", month_ranges, download_dir, log=logs.append
    )

    # ทุกผลลัพธ์ต้องไม่สำเร็จ (เพราะ always_fails) แต่ต้องมีมากกว่า 1 รายการ (ถูกแบ่งช่วงแล้ว)
    # และรวมกันครอบคลุมทั้งเดือนไม่มีวันตกหล่น/ซ้อนทับ
    assert len(results) > 1
    assert all(r.success is False for r in results)
    covered_days = sorted(
        d for f, t in ((r.date_from, r.date_to) for r in results)
        for d in [datetime.strptime(f, "%d/%m/%Y"), datetime.strptime(t, "%d/%m/%Y")]
    )
    assert covered_days[0] == datetime.strptime("01/07/2026", "%d/%m/%Y")
    assert covered_days[-1] == datetime.strptime("31/07/2026", "%d/%m/%Y")
    assert any("ลองแบ่งครึ่ง" in m for m in logs)


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


def test_try_download_from_show_page_logs_js_found_snippets_when_not_found(monkeypatch):
    """เพิ่มจากเทสต์ก่อนหน้า — ยืนยันว่าตอนหาปุ่มไม่เจอ ต้องสแกนด้วย JS หา element ที่น่าจะ
    เกี่ยวกับดาวน์โหลด (เช่น <input type="image"> ที่ Selenium ไม่ได้แมตช์เพราะเหตุผลอื่น) แล้ว
    log HTML ดิบออกมาด้วย ไม่ต้องให้ผู้ใช้เปิด DevTools เองอีกต่อไป"""

    driver = _FakeShowPageDriver(
        script_snippets=['<input type="image" id="imgBtn" src="Images/dl_icon.gif">']
    )
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)

    logs = []
    amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=logs.append, timeout=0)

    joined = "\n".join(logs)
    assert "imgBtn" in joined
    assert "dl_icon.gif" in joined


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

    monkeypatch.setattr(amr_downloader, "_wait_for_download", lambda download_dir, timeout=60, log=None, ignore_existing=None: "/tmp/fake4.xls")
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)
    _install_fake_clock(monkeypatch)  # กันไม่ให้ popup-wait loop รอจริง 20 วินาที (ไม่มี popup เปิดในเทสต์นี้)

    result = amr_downloader._try_download_from_show_page(driver, "main", "/tmp/dl", log=lambda m: None, timeout=5)

    assert btn.clicked is True
    assert result == "/tmp/fake4.xls"


def test_try_download_from_show_page_default_timeout_is_60_seconds():
    """ยืนยันจากผู้ใช้จริงอีกครั้ง: บัญชี/เดือนที่มีข้อมูลเต็มเดือน (~30 วัน) render หน้า
    showPeriodProfile.aspx ช้ากว่า 30 วินาทีเดิม (diagnostics เจอปุ่มทันทีหลัง scan หมดเวลา
    เหมือนรอบก่อนที่เพิ่มจาก 15->30 แต่คราวนี้ margin กว้างกว่าเดิมมาก) — เพิ่มเป็น 60 วินาที"""

    import inspect

    default_timeout = inspect.signature(amr_downloader._try_download_from_show_page).parameters["timeout"].default
    assert default_timeout == 60.0


def test_try_download_from_show_page_logs_heartbeat_while_waiting(monkeypatch):
    """ระหว่างรอปุ่มปรากฏนาน ๆ (สูงสุด 60 วินาที) ต้อง log heartbeat เป็นระยะ (ทุก 10 วินาที)
    กันดูเหมือน job ค้างเฉยๆ ไม่มีอะไรเกิดขึ้นเลยเป็นนาที"""

    driver = _FakeShowPageDriver()  # ไม่มีปุ่มปรากฏเลยตลอดการทดสอบ
    monkeypatch.setattr(amr_downloader, "random_delay", lambda a, b: None)
    _install_fake_clock(monkeypatch)

    logs = []
    result = amr_downloader._try_download_from_show_page(
        driver, "main", "/tmp/dl", log=logs.append, timeout=25
    )

    assert result is None
    heartbeat_lines = [m for m in logs if "รอต่อ" in m]
    assert len(heartbeat_lines) >= 2, f"ต้องมี heartbeat log อย่างน้อย 2 บรรทัดในเวลา 25 วินาที: {logs}"


def test_wait_for_download_returns_none_when_nothing_appears(monkeypatch, tmp_path):
    _install_fake_clock(monkeypatch)
    result = amr_downloader._wait_for_download(str(tmp_path), timeout=5, log=lambda m: None)
    assert result is None


def test_wait_for_download_ignores_stale_crdownload_from_unrelated_job(monkeypatch, tmp_path):
    """ยืนยันจากผู้ใช้จริง: download_dir เป็นโฟลเดอร์เดียวที่ใช้ร่วมกันทุก job/ทุกบัญชี (ไม่ได้
    แยกโฟลเดอร์ย่อยต่อ job) — เจอ .crdownload ค้างจาก job เก่าที่ไม่เกี่ยวข้องกันเลย (คนละบัญชี)
    บล็อกไม่ให้ job ใหม่มองว่าดาวน์โหลดเสร็จได้เลย ทั้งที่ไฟล์ของ job ใหม่ดาวน์โหลดเสร็จจริงแล้ว
    — ต้องสนใจเฉพาะไฟล์ที่ "เพิ่งปรากฏใหม่" หลัง snapshot เท่านั้น ไม่ถูกไฟล์ค้างเก่าบล็อก"""

    download_dir = str(tmp_path)
    # ไฟล์ .crdownload ค้างจาก job เก่า (บัญชีอื่น) ที่มีอยู่ก่อนแล้วตั้งแต่ก่อนเริ่ม snapshot
    stale_crdownload = tmp_path / "kW_OLD_UNRELATED_ACCOUNT.xls.crdownload"
    stale_crdownload.write_text("ค้างจาก job เก่า", encoding="utf-8")

    existing_before = frozenset(os.listdir(download_dir))
    assert "kW_OLD_UNRELATED_ACCOUNT.xls.crdownload" in existing_before

    # ไฟล์ใหม่ของ job นี้ดาวน์โหลดเสร็จสมบูรณ์แล้ว (ไม่มี .crdownload ใหม่ค้างเลย)
    new_file = tmp_path / "kW_NEW_ACCOUNT.xls"
    new_file.write_text("ไฟล์ใหม่ที่เสร็จแล้ว", encoding="utf-8")

    _install_fake_clock(monkeypatch)
    result = amr_downloader._wait_for_download(
        download_dir, timeout=5, log=lambda m: None, ignore_existing=existing_before
    )

    assert result == str(new_file)


def test_wait_for_download_extends_grace_period_when_crdownload_present_at_deadline(monkeypatch, tmp_path):
    """ยืนยันจากผู้ใช้จริง: บัญชี/เดือนที่มีข้อมูลเต็มเดือน (~30 วัน) ฝั่งเซิร์ฟเวอร์ใช้เวลาสร้าง
    ไฟล์ export นานไม่คงที่ เหมือนที่เคยเจอตอนหน้า showPeriodProfile.aspx render ช้า — ถ้าไฟล์
    เริ่มดาวน์โหลดแล้วจริง (มี .crdownload) ตอนครบเวลาที่ตั้งไว้พอดี ต้องต่อเวลาให้ ไม่ใช่ตัดทิ้ง
    กลางคันทั้งที่ใกล้เสร็จแล้ว"""

    download_dir = str(tmp_path)
    crdownload_path = tmp_path / "report.xls.crdownload"
    final_path = tmp_path / "report.xls"
    fake_clock = {"t": 0.0}

    def fake_sleep(seconds):
        fake_clock["t"] += seconds
        t = fake_clock["t"]
        if t >= 2 and not crdownload_path.exists() and not final_path.exists():
            crdownload_path.write_text("partial", encoding="utf-8")
        # ไฟล์ต้องโตขึ้นจริงอย่างน้อยครั้งเดียวก่อนครบเวลา (t=5) ไม่งั้นตอนนี้ถือว่าค้างนิ่งตาย
        # จะไม่ต่อเวลาให้ (ดู _wait_for_download: size_has_grown)
        if t >= 3 and crdownload_path.exists() and crdownload_path.read_text(encoding="utf-8") == "partial":
            crdownload_path.write_text("partial-more-data", encoding="utf-8")
        if t >= 8 and crdownload_path.exists():
            crdownload_path.unlink()
            final_path.write_text("done", encoding="utf-8")

    monkeypatch.setattr(amr_downloader.time, "sleep", fake_sleep)
    monkeypatch.setattr(amr_downloader.time, "time", lambda: fake_clock["t"])

    logs = []
    result = amr_downloader._wait_for_download(download_dir, timeout=5, log=logs.append)

    assert result == str(final_path)
    assert any("ต่อเวลาให้อีก" in m for m in logs), f"ต้อง log ว่าต่อเวลาให้: {logs}"


def test_wait_for_download_warns_when_crdownload_size_never_grows(monkeypatch, tmp_path):
    """ยืนยันจากผู้ใช้จริง (ลองหลายรอบ คนละ session กัน บัญชี/เดือนเดิม): มี .crdownload ขนาด
    "เท่าเดิมเป๊ะ" ตั้งแต่ heartbeat แรกจนครบเวลา แม้จะเคยต่อเวลาให้ไปแล้วก่อนหน้านี้ก็ยังค้างที่
    ขนาดเดิม — ต้อง log ขนาดไฟล์ทุก heartbeat เพื่อแยกให้ออกว่า "กำลังโหลดจริง (ขนาดโตขึ้นเรื่อยๆ)"
    หรือ "ค้างนิ่งตาย" (ขนาดไม่ขยับเลย) และต้อง "ไม่ต่อเวลาให้" กรณีค้างนิ่งตายแบบนี้ (ต่อเวลาให้ก็
    ไม่มีประโยชน์ รอนานแค่ไหนก็ยังจะค้างที่ขนาดเดิม) เพื่อให้ผู้เรียก (เช่น _handle_popup) ไปลอง
    submit ใหม่ได้เร็วขึ้นแทนที่จะเสียเวลารอเปล่าๆ อีก 60 วินาที"""

    download_dir = str(tmp_path)
    crdownload_path = tmp_path / "stuck.xls.crdownload"
    crdownload_path.write_text("x" * 100, encoding="utf-8")  # ขนาดคงที่ตลอดทั้งเทสต์ — ไม่เคยโตขึ้นเลย
    fake_clock = {"t": 0.0}

    monkeypatch.setattr(amr_downloader.time, "sleep", lambda s: fake_clock.__setitem__("t", fake_clock["t"] + s))
    monkeypatch.setattr(amr_downloader.time, "time", lambda: fake_clock["t"])

    logs = []
    result = amr_downloader._wait_for_download(download_dir, timeout=10, log=logs.append)

    assert result is None
    assert fake_clock["t"] < 15, f"ไฟล์ค้างนิ่งตายต้องไม่ได้รับการต่อเวลา (60s) ต้องคืนค่าทันทีที่ครบเวลาเดิม: t={fake_clock['t']}"
    assert not any("ต่อเวลาให้อีก" in m for m in logs), f"ไฟล์ที่ไม่เคยโตขึ้นเลยต้องไม่ได้รับการต่อเวลา: {logs}"
    assert any("ยอมแพ้" in m for m in logs), f"ต้อง log สรุปตอนยอมแพ้พร้อมขนาดไฟล์ล่าสุด: {logs}"
    assert any("ไม่เคยขยับเลย" in m for m in logs), f"ต้องระบุในข้อความยอมแพ้ด้วยว่าไม่เคยขยับเลย: {logs}"


def test_wait_for_download_heartbeat_warns_when_size_unchanged_since_last_check(monkeypatch, tmp_path):
    """ระหว่างรอ (ยังไม่ครบเวลา) ถ้ามี heartbeat เกิดขึ้นและขนาดไฟล์ไม่ขยับจากรอบก่อนหน้า ต้อง
    เตือนไว้ใน log ทันที ไม่ต้องรอให้ครบเวลาก่อนถึงจะรู้ว่าค้างนิ่ง"""

    download_dir = str(tmp_path)
    crdownload_path = tmp_path / "stuck.xls.crdownload"
    crdownload_path.write_text("x" * 100, encoding="utf-8")
    fake_clock = {"t": 0.0}

    monkeypatch.setattr(amr_downloader.time, "sleep", lambda s: fake_clock.__setitem__("t", fake_clock["t"] + s))
    monkeypatch.setattr(amr_downloader.time, "time", lambda: fake_clock["t"])

    logs = []
    # timeout ยาวพอให้ heartbeat (ทุก 15 วิ) เกิดขึ้น 2 ครั้งก่อนครบเวลา (ครั้งแรกแค่บันทึกขนาดไว้
    # เทียบ ยังไม่มีอะไรให้เทียบ — ครั้งที่สองถึงจะรู้ว่าขนาดไม่ขยับจากรอบก่อน)
    result = amr_downloader._wait_for_download(download_dir, timeout=35, log=logs.append)

    assert result is None
    assert any("ขนาดไฟล์ไม่ขยับเลยตั้งแต่รอบก่อน" in m for m in logs), f"ต้องเตือนตั้งแต่ heartbeat ระหว่างรอ: {logs}"
