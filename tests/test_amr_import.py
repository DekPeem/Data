import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import amr_import
from amr_mapping.amr_downloader import DownloadResult
from amr_mapping.loader import load_reference_data

# 01/08/2026 = วันเสาร์, 02/08/2026 = วันอาทิตย์ — ใช้เช็คว่า compute_hourly_curve ทำงานถูกต้อง
# เวลาถูกเรียกผ่าน pipeline เต็ม (import_amr_for_business/import_amr_auto)

_SYNTHETIC_INTERVAL_HTML = """
<html><body>
<table>
  <tr><td></td><td>RATE A</td><td>RATE B</td><td>RATE C</td><td>ผลรวม</td></tr>
  <tr><td>01/08/2026 09.15</td><td>20.00</td><td></td><td></td><td>20.00</td></tr>
  <tr><td>01/08/2026 22.15</td><td></td><td>5.00</td><td></td><td>5.00</td></tr>
  <tr><td>02/08/2026 00.15</td><td></td><td></td><td>10.00</td><td>10.00</td></tr>
  <tr><td>ผลรวมทั้งหมด</td><td>20.00</td><td>5.00</td><td>10.00</td><td>35.00</td></tr>
</table>
</body></html>
"""


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "reference"
    d.mkdir()
    (d / "business_types.csv").write_text(
        "code,name_th,category,notes\nTESTBIZ,ธุรกิจทดสอบ,test,\n", encoding="utf-8"
    )
    (d / "rate_schedules.csv").write_text(
        "code,billing_method,voltage_level,description\n50,TOU,LV,\n", encoding="utf-8"
    )
    (d / "load_profiles.csv").write_text(
        "business_type_code,rate_code,billing_method,demand_p_kw,demand_op_kw,demand_h_kw,"
        "energy_p_kwh,energy_op_kwh,energy_h_kwh,contract_kva_ref,sample_size,notes\n",
        encoding="utf-8",
    )
    return d


def _fake_download_amr_kw_reports(username, password, accounts, start_date, end_date, download_dir, log, headless=True):
    """แทนที่ Selenium จริงด้วยไฟล์ synthetic 2 ไฟล์ (จำลอง 2 เดือน)"""
    results = []
    for i, month_label in enumerate(["2026-07", "2026-08"]):
        path = os.path.join(download_dir, f"amr_{month_label}.xls")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_SYNTHETIC_INTERVAL_HTML)
        results.append(
            DownloadResult(
                account_no=accounts[0], meter_text="M1", date_from=start_date, date_to=end_date,
                file_path=path, success=True,
            )
        )
    return results


def test_import_amr_for_business_updates_load_profiles(monkeypatch, data_dir):
    received = {}

    def spy_fake_download(username, password, *args, **kwargs):
        received["username"] = username
        received["password"] = password
        return _fake_download_amr_kw_reports(username, password, *args, **kwargs)

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", spy_fake_download)

    logs = []
    profile = amr_import.import_amr_for_business(
        username="test-user",
        password="test-pass",
        accounts=["9999999999"],
        start_date="2026-07-01",
        end_date="2026-08-31",
        business_type_code="TESTBIZ",
        rate_code="50",
        contract_kva=1000,
        source_label="unit test",
        data_dir=data_dir,
        download_dir=data_dir.parent / "downloads",
        log=logs.append,
    )

    assert profile.business_type_code == "TESTBIZ"
    assert profile.rate_code == "50"
    assert profile.energy_kwh == {"P": 20.0, "OP": 5.0, "H": 10.0}
    assert profile.demand_kw == {"P": 80.0, "OP": 20.0, "H": 40.0}
    assert profile.sample_size == 2
    assert profile.contract_kva_ref == 1000
    assert received["username"] == "test-user"
    assert received["password"] == "test-pass"

    # ต้องเขียนกลับลงไฟล์จริงด้วย
    reference = load_reference_data(data_dir)
    saved = next(p for p in reference.load_profiles if p.business_type_code == "TESTBIZ")
    assert saved.energy_kwh["P"] == 20.0

    # ต้องไม่มี username/password รั่วไหลออกมาใน log
    joined_logs = " ".join(logs)
    assert "test-pass" not in joined_logs

    # ต้องบันทึกเส้นโค้งรายชั่วโมงลง load_curves.csv ด้วย (ไม่ใช่แค่ load_profiles.csv)
    curve = next(c for c in reference.load_curves if c.key() == ("TESTBIZ", "50"))
    # ข้อมูล synthetic มีจุดเดียวที่ชม.9 (RATE A 20.00 -> 80 kW) ในวันเสาร์ (01/08/2026)
    assert curve.hours["sat"][9] == pytest.approx(80.0)
    assert curve.hours["all"][9] == pytest.approx(80.0)


def test_import_amr_for_business_keeps_download_dir_for_reuse(monkeypatch, data_dir, tmp_path):
    """เปลี่ยนพฤติกรรมจากเดิม (เคยลบไฟล์ดิบทิ้งเสมอ) — ตอนนี้ต้อง "เก็บไว้" แทน เพื่อให้
    รันซ้ำ/นำเข้าเดือนเพิ่มไม่ต้องดาวน์โหลดของเดิมใหม่ (ตามที่ผู้ใช้ขอ)"""

    captured_dirs = []

    def spy_download(username, password, accounts, start_date, end_date, download_dir, log, headless=True):
        captured_dirs.append(download_dir)
        return _fake_download_amr_kw_reports(username, password, accounts, start_date, end_date, download_dir, log, headless)

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", spy_download)

    download_dir = tmp_path / "downloads"
    amr_import.import_amr_for_business(
        username="u", password="p", accounts=["123"],
        start_date="2026-07-01", end_date="2026-08-31",
        business_type_code="TESTBIZ", rate_code="50", contract_kva=None,
        source_label="", data_dir=data_dir, download_dir=download_dir,
    )

    assert len(captured_dirs) == 1
    assert os.path.exists(captured_dirs[0]), "ไฟล์ดิบที่ดาวน์โหลดมาต้องถูกเก็บไว้ (ไม่ลบทิ้ง) เพื่อใช้ซ้ำได้"
    assert os.listdir(captured_dirs[0]), "โฟลเดอร์ดาวน์โหลดต้องยังมีไฟล์อยู่จริง ไม่ใช่แค่โฟลเดอร์เปล่า"


def test_import_amr_for_business_default_download_dir_is_gitignored_amr_downloads():
    """ค่า default ของ download_dir ต้องชี้ไปที่ amr_downloads/ ที่ root ของ repo (มี
    .gitignore คุ้มครองอยู่แล้ว) ไม่ใช่ temp dir ที่หายไปเมื่อรีบูตเหมือนเดิม"""

    assert amr_import.DEFAULT_DOWNLOAD_DIR.name == "amr_downloads"
    assert amr_import.DEFAULT_DOWNLOAD_DIR.parent == Path(amr_import.__file__).resolve().parents[2]


def test_import_amr_for_business_raises_when_no_files_downloaded(monkeypatch, data_dir):
    def empty_download(*args, **kwargs):
        return []

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", empty_download)

    with pytest.raises(RuntimeError):
        amr_import.import_amr_for_business(
            username="u", password="p", accounts=["123"],
            start_date="2026-07-01", end_date="2026-08-31",
            business_type_code="TESTBIZ", rate_code="50", contract_kva=None,
            source_label="", data_dir=data_dir, download_dir=data_dir.parent / "downloads",
        )


def _fake_download_amr_with_profile(username, password, start_date, end_date, download_dir, log, headless=True):
    """แทนที่ login+scrape+download จริงด้วยค่า profile สมมติ + ไฟล์ synthetic"""
    profile_info = {
        "name": "บริษัท ทดสอบออโต้ จำกัด",
        "account_no": username,
        "rate_code": "40",
        "billing_method": "TOU",
        "business_type_code": "34111",
        "business_type_name": "การผลิตเยื่อกระดาษ (ตัวอย่าง)",
        "kva": "15,000",
        "meter_no": "11111111",
    }
    path = os.path.join(download_dir, "amr_auto.xls")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_SYNTHETIC_INTERVAL_HTML)
    results = [
        DownloadResult(account_no=username, meter_text="M1", date_from=start_date, date_to=end_date, file_path=path, success=True)
    ]
    return profile_info, results


def test_import_amr_auto_detects_and_saves_new_business_type(monkeypatch, data_dir):
    monkeypatch.setattr(amr_import, "download_amr_with_profile", _fake_download_amr_with_profile)

    logs = []
    profile = amr_import.import_amr_auto(
        username="019900000001", password="secret-pass",
        start_date="2026-07-01", end_date="2026-08-31",
        source_label="unit test auto",
        data_dir=data_dir, download_dir=data_dir.parent / "downloads", log=logs.append,
    )

    assert profile.business_type_code == "34111"
    assert profile.rate_code == "40"
    assert profile.contract_kva_ref == 15000.0
    assert profile.billing_method == "TOU"

    # ต้องเพิ่ม business type ใหม่ลง business_types.csv อัตโนมัติ เพราะ 34111 ยังไม่เคยมี
    reference = load_reference_data(data_dir)
    assert "34111" in reference.business_types
    assert reference.business_types["34111"].name_th == "การผลิตเยื่อกระดาษ (ตัวอย่าง)"
    assert reference.business_types["34111"].category == "auto"

    # และต้องยังมี business type เดิม (TESTBIZ) อยู่ครบ ไม่หายไป
    assert "TESTBIZ" in reference.business_types

    saved = next(p for p in reference.load_profiles if p.business_type_code == "34111")
    assert saved.rate_code == "40"

    # ต้องบันทึกประวัติ (ชื่อบริษัทจริง) ลง import_log_local.csv แยกต่างหาก (gitignored)
    from amr_mapping.loader import load_import_log_local

    log_entries = load_import_log_local(data_dir / "import_log_local.csv")
    assert len(log_entries) == 1
    assert log_entries[0]["company_name"] == "บริษัท ทดสอบออโต้ จำกัด"
    assert log_entries[0]["account_no"] == "019900000001"
    assert log_entries[0]["business_type_code"] == "34111"

    assert "secret-pass" not in " ".join(logs)


def test_import_amr_auto_does_not_overwrite_existing_business_type(monkeypatch, data_dir):
    def fake_download(username, password, start_date, end_date, download_dir, log, headless=True):
        profile_info = {
            "rate_code": "50", "billing_method": "TOU",
            "business_type_code": "TESTBIZ",  # ชนกับที่มีอยู่แล้วใน fixture
            "business_type_name": "ชื่อใหม่ที่ไม่ควรถูกใช้ทับ",
            "kva": "500",
        }
        path = os.path.join(download_dir, "amr_auto.xls")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_SYNTHETIC_INTERVAL_HTML)
        results = [DownloadResult(account_no=username, meter_text="M1", date_from=start_date, date_to=end_date, file_path=path, success=True)]
        return profile_info, results

    monkeypatch.setattr(amr_import, "download_amr_with_profile", fake_download)

    amr_import.import_amr_auto(
        username="TESTBIZ-ACC", password="p",
        start_date="2026-07-01", end_date="2026-08-31",
        data_dir=data_dir, download_dir=data_dir.parent / "downloads",
    )

    reference = load_reference_data(data_dir)
    # ชื่อเดิม ("ธุรกิจทดสอบ" จาก fixture) ต้องไม่ถูกเขียนทับด้วยชื่อที่ scrape มาใหม่
    assert reference.business_types["TESTBIZ"].name_th == "ธุรกิจทดสอบ"


def test_import_amr_auto_calls_on_profile_callback_with_raw_scraped_data(monkeypatch, data_dir):
    """on_profile ต้องถูกเรียกพร้อม dict ดิบที่ scrape มาได้ (รวมชื่อจริง) ก่อนเริ่มประมวลผล
    ไฟล์ — ใช้โดย web/app.py เพื่อแสดงชื่อบริษัทจริงในหน้า Admin (ไม่เขียนลงไฟล์ที่ไหน)"""

    def fake_download(username, password, start_date, end_date, download_dir, log, headless=True):
        profile_info = {
            "name": "บริษัท ทดสอบ ออโต้ จำกัด",
            "account_no": username,
            "meter_no": "22222222",
            "rate_code": "40",
            "billing_method": "TOU",
            "business_type_code": "34111",
            "business_type_name": "การผลิตเยื่อกระดาษ (ตัวอย่าง)",
            "kva": "15,000",
        }
        path = os.path.join(download_dir, "amr_auto.xls")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_SYNTHETIC_INTERVAL_HTML)
        results = [DownloadResult(account_no=username, meter_text="M1", date_from=start_date, date_to=end_date, file_path=path, success=True)]
        return profile_info, results

    monkeypatch.setattr(amr_import, "download_amr_with_profile", fake_download)

    received_profiles = []
    amr_import.import_amr_auto(
        username="019900000099", password="p",
        start_date="2026-07-01", end_date="2026-08-31",
        data_dir=data_dir, download_dir=data_dir.parent / "downloads",
        on_profile=received_profiles.append,
    )

    assert len(received_profiles) == 1
    assert received_profiles[0]["name"] == "บริษัท ทดสอบ ออโต้ จำกัด"
    assert received_profiles[0]["account_no"] == "019900000099"


def test_import_amr_auto_raises_when_detection_incomplete(monkeypatch, data_dir):
    def fake_download(username, password, start_date, end_date, download_dir, log, headless=True):
        profile_info = {"rate_code": "", "business_type_code": "", "kva": ""}  # ตรวจจับไม่ได้เลย
        path = os.path.join(download_dir, "amr_auto.xls")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_SYNTHETIC_INTERVAL_HTML)
        results = [DownloadResult(account_no=username, meter_text="M1", date_from=start_date, date_to=end_date, file_path=path, success=True)]
        return profile_info, results

    monkeypatch.setattr(amr_import, "download_amr_with_profile", fake_download)

    with pytest.raises(RuntimeError):
        amr_import.import_amr_auto(
            username="u", password="p", start_date="2026-07-01", end_date="2026-08-31",
            data_dir=data_dir, download_dir=data_dir.parent / "downloads",
        )
