import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
