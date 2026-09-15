import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.amr_downloader import build_dashboard_url, extract_dashboard_params, generate_month_ranges

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
