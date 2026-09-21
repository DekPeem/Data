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
    curve = next(c for c in reference.load_curves if c.key() == ("TESTBIZ", "50", False))
    # ข้อมูล synthetic มีจุดเดียวที่ชม.9 (RATE A 20.00 -> 80 kW) ในวันเสาร์ (01/08/2026)
    assert curve.hours["sat"][9] == pytest.approx(80.0)
    assert curve.hours["all"][9] == pytest.approx(80.0)


def test_import_amr_for_business_saves_has_solar_flag(monkeypatch, data_dir):
    """has_solar ต้องกรอกเอง (ไม่มีการตรวจจับอัตโนมัติ) — ต้องถูกส่งต่อไปยังทั้ง LoadProfile
    และ LoadCurve ที่บันทึกจริง ไม่ใช่แค่ default False เสมอ"""

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", _fake_download_amr_kw_reports)

    profile = amr_import.import_amr_for_business(
        username="test-user", password="test-pass", accounts=["9999999999"],
        start_date="2026-07-01", end_date="2026-08-31",
        business_type_code="TESTBIZ", rate_code="50", contract_kva=1000,
        source_label="unit test solar", has_solar=True,
        data_dir=data_dir, download_dir=data_dir.parent / "downloads",
    )

    assert profile.has_solar is True

    reference = load_reference_data(data_dir)
    saved = next(p for p in reference.load_profiles if p.business_type_code == "TESTBIZ")
    assert saved.has_solar is True
    curve = next(c for c in reference.load_curves if c.key() == ("TESTBIZ", "50", True))
    assert curve.has_solar is True


def test_import_amr_for_business_logs_import_history_per_account(monkeypatch, data_dir):
    """โหมดนี้ (กรอกประเภทธุรกิจเอง + ดาวน์โหลดจากเว็บ) เดิมไม่เคยบันทึกประวัติการนำเข้าใน
    เครื่องเลย ทำให้หน้า Admin หาชื่อบริษัทที่นำเข้าผ่านโหมดนี้ไม่เจอ — ต้องอ่านชื่อบริษัทจากหัว
    รายงานของแต่ละไฟล์ที่ดาวน์โหลดมาได้ แล้วบันทึกแยกทีละบัญชี (accounts อาจมีมากกว่า 1)"""

    def fake_download(username, password, accounts, start_date, end_date, download_dir, log, headless=True):
        results = []
        for i, account_no in enumerate(accounts):
            path = os.path.join(download_dir, f"amr_{account_no}.xls")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    _SYNTHETIC_HTML_WITH_HEADER_TEMPLATE.format(
                        account_no=account_no, company_name=f"บริษัท ทดสอบ {i} จำกัด",
                        meter_no=f"M{i}", tariff="TOU",
                    )
                )
            results.append(
                DownloadResult(
                    account_no=account_no, meter_text=f"M{i}", date_from=start_date, date_to=end_date,
                    file_path=path, success=True,
                )
            )
        return results

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", fake_download)

    amr_import.import_amr_for_business(
        username="test-user", password="test-pass", accounts=["0199000001", "0199000002"],
        start_date="2026-07-01", end_date="2026-08-31",
        business_type_code="TESTBIZ", rate_code="50", contract_kva=1000,
        source_label="", has_solar=False, data_dir=data_dir,
    )

    from amr_mapping.loader import load_import_log_local

    entries = load_import_log_local(data_dir / "import_log_local.csv")
    assert len(entries) == 2
    accounts_logged = {e["account_no"] for e in entries}
    assert accounts_logged == {"0199000001", "0199000002"}
    names_logged = {e["account_no"]: e["company_name"] for e in entries}
    assert names_logged["0199000001"] == "บริษัท ทดสอบ 0 จำกัด"
    assert names_logged["0199000002"] == "บริษัท ทดสอบ 1 จำกัด"
    assert all(e["business_type_code"] == "TESTBIZ" and e["rate_code"] == "50" for e in entries)


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


def _write_synthetic_files(tmp_path, n=2):
    """เขียนไฟล์ synthetic n ไฟล์ (จำลองไฟล์ AMR ที่ผู้ใช้แนบมาเอง ไม่ใช่ดาวน์โหลดจากเว็บ)"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        path = tmp_path / f"attached_{i}.xls"
        path.write_text(_SYNTHETIC_INTERVAL_HTML, encoding="utf-8")
        paths.append(str(path))
    return paths


# โครงสร้างเดียวกับ _SYNTHETIC_INTERVAL_HTML แต่มีตารางหัวรายงาน (บัญชี/ชื่อ/Tariff) นำหน้าด้วย —
# ยืนยันจากไฟล์จริงที่ผู้ใช้ส่งมาว่าไฟล์ export ของ PEA มีตารางนี้อยู่เสมอ (ดู pea_ingest.py)
_SYNTHETIC_HTML_WITH_HEADER_TEMPLATE = """
<table width='800px'><tr>
<td class='detail'>บัญชีผู้ใช้ไฟ : </td><td>{account_no}&nbsp;</td><td class='detail'>ชื่อผู้ใช้ไฟ : </td><td>{company_name}</td>
</tr>
<tr>
<td class='detail'>หมายเลขมิเตอร์ : </td><td>{meter_no}&nbsp;</td><td class='detail'>Tariff : </td><td>{tariff}</td>
</tr>
</table>
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


def _write_synthetic_files_with_header(
    tmp_path, account_no="0199000000", company_name="บริษัท ทดสอบ จำกัด", meter_no="1234567", tariff="TOU", n=1
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        path = tmp_path / f"attached_{i}.xls"
        path.write_text(
            _SYNTHETIC_HTML_WITH_HEADER_TEMPLATE.format(
                account_no=account_no, company_name=company_name, meter_no=meter_no, tariff=tariff
            ),
            encoding="utf-8",
        )
        paths.append(str(path))
    return paths


def test_import_amr_from_files_updates_load_profiles(data_dir, tmp_path):
    file_paths = _write_synthetic_files(tmp_path / "attached")

    logs = []
    profile = amr_import.import_amr_from_files(
        file_paths=file_paths,
        business_type_code="TESTBIZ",
        rate_code="50",
        contract_kva=1000,
        source_label="unit test file upload",
        data_dir=data_dir,
        log=logs.append,
    )

    assert profile.business_type_code == "TESTBIZ"
    assert profile.rate_code == "50"
    assert profile.energy_kwh == {"P": 20.0, "OP": 5.0, "H": 10.0}
    assert profile.demand_kw == {"P": 80.0, "OP": 20.0, "H": 40.0}
    assert profile.sample_size == 2
    assert profile.contract_kva_ref == 1000
    assert "แนบเอง" in profile.notes
    assert "unit test file upload" in profile.notes

    reference = load_reference_data(data_dir)
    saved = next(p for p in reference.load_profiles if p.business_type_code == "TESTBIZ")
    assert saved.energy_kwh["P"] == 20.0

    curve = next(c for c in reference.load_curves if c.key() == ("TESTBIZ", "50", False))
    assert curve.hours["sat"][9] == pytest.approx(80.0)


def test_import_amr_from_files_saves_has_solar_flag(data_dir, tmp_path):
    file_paths = _write_synthetic_files(tmp_path / "attached")

    profile = amr_import.import_amr_from_files(
        file_paths=file_paths,
        business_type_code="TESTBIZ",
        rate_code="50",
        contract_kva=1000,
        source_label="",
        has_solar=True,
        data_dir=data_dir,
    )

    assert profile.has_solar is True
    reference = load_reference_data(data_dir)
    curve = next(c for c in reference.load_curves if c.key() == ("TESTBIZ", "50", True))
    assert curve.has_solar is True


def test_import_amr_from_files_raises_when_no_readable_files(data_dir, tmp_path):
    bad_file = tmp_path / "not_amr_data.xls"
    bad_file.write_text("<html><body>ไม่มีตารางข้อมูลอยู่เลย</body></html>", encoding="utf-8")

    with pytest.raises(RuntimeError):
        amr_import.import_amr_from_files(
            file_paths=[str(bad_file)],
            business_type_code="TESTBIZ",
            rate_code="50",
            contract_kva=None,
            source_label="",
            data_dir=data_dir,
        )


def _write_registered_customer(data_dir, account_no="0199000000", business_type_code="TESTBIZ", rate_code="50", contract_kva=2000.0):
    (data_dir / "customers.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr\n"
        f"{account_no},ลูกค้าทดสอบ,{business_type_code},{rate_code},{contract_kva},false\n",
        encoding="utf-8",
    )


def test_import_amr_from_files_resolves_fields_from_customer_registry(data_dir, tmp_path):
    """ไม่ระบุ business_type_code/rate_code/contract_kva มาเลย — ต้องอ่านเลขบัญชีจากไฟล์แล้ว
    เทียบกับทะเบียนลูกค้าให้อัตโนมัติ (ตามที่ผู้ใช้ขอ: แนบแค่ไฟล์ ไม่ต้องกรอกอะไรเลย)"""

    _write_registered_customer(data_dir, account_no="0199000000", business_type_code="TESTBIZ", rate_code="50", contract_kva=2500.0)
    file_paths = _write_synthetic_files_with_header(tmp_path / "attached", account_no="0199000000")

    logs = []
    profile = amr_import.import_amr_from_files(file_paths=file_paths, data_dir=data_dir, log=logs.append)

    assert profile.business_type_code == "TESTBIZ"
    assert profile.rate_code == "50"
    assert profile.contract_kva_ref == 2500.0
    assert any("ทะเบียนลูกค้า" in line for line in logs)


def test_import_amr_from_files_explicit_args_take_priority_over_registry(data_dir, tmp_path):
    """ถ้าผู้ใช้กรอกประเภทธุรกิจ/อัตราเองมาด้วย ต้องใช้ค่าที่กรอกมา ไม่ใช่ค่าจากทะเบียน"""

    _write_registered_customer(data_dir, account_no="0199000000", business_type_code="FROM-REGISTRY", rate_code="99")
    file_paths = _write_synthetic_files_with_header(tmp_path / "attached", account_no="0199000000")

    profile = amr_import.import_amr_from_files(
        file_paths=file_paths, business_type_code="TESTBIZ", rate_code="50", data_dir=data_dir,
    )

    assert profile.business_type_code == "TESTBIZ"
    assert profile.rate_code == "50"


def test_import_amr_from_files_raises_helpful_message_when_account_not_registered(data_dir, tmp_path):
    file_paths = _write_synthetic_files_with_header(
        tmp_path / "attached", account_no="0199009999", company_name="บริษัท ไม่มีทะเบียน จำกัด"
    )

    with pytest.raises(RuntimeError) as exc_info:
        amr_import.import_amr_from_files(file_paths=file_paths, data_dir=data_dir)

    message = str(exc_info.value)
    assert "0199009999" in message
    assert "บริษัท ไม่มีทะเบียน จำกัด" in message


def test_import_amr_from_files_raises_generic_message_when_no_account_info_at_all(data_dir, tmp_path):
    """ไฟล์ไม่มีตารางหัวรายงานเลย (หาเลขบัญชีไม่ได้) และไม่ได้กรอกประเภทธุรกิจ/อัตรามาด้วย —
    ต้อง raise เหมือนเดิม แค่ไม่มี hint เลขบัญชีแนบมาด้วย (เพราะไม่รู้จริงๆ)"""

    file_paths = _write_synthetic_files(tmp_path / "attached", n=1)

    with pytest.raises(RuntimeError):
        amr_import.import_amr_from_files(file_paths=file_paths, data_dir=data_dir)


def test_import_amr_from_files_logs_import_history_when_account_known(data_dir, tmp_path):
    _write_registered_customer(data_dir, account_no="0199000000")
    file_paths = _write_synthetic_files_with_header(
        tmp_path / "attached", account_no="0199000000", company_name="บริษัท ทดสอบ จำกัด"
    )

    amr_import.import_amr_from_files(file_paths=file_paths, data_dir=data_dir)

    from amr_mapping.loader import load_import_log_local

    entries = load_import_log_local(data_dir / "import_log_local.csv")
    assert len(entries) == 1
    assert entries[0]["account_no"] == "0199000000"
    assert entries[0]["company_name"] == "บริษัท ทดสอบ จำกัด"
    assert entries[0]["business_type_code"] == "TESTBIZ"


def test_import_amr_from_files_calls_on_profile_callback(data_dir, tmp_path):
    _write_registered_customer(data_dir, account_no="0199000000")
    file_paths = _write_synthetic_files_with_header(
        tmp_path / "attached", account_no="0199000000", company_name="บริษัท ทดสอบ จำกัด", meter_no="7654321"
    )

    received = {}
    amr_import.import_amr_from_files(file_paths=file_paths, data_dir=data_dir, on_profile=received.update)

    assert received["name"] == "บริษัท ทดสอบ จำกัด"
    assert received["account_no"] == "0199000000"
    assert received["meter_no"] == "7654321"


def test_import_amr_from_files_appends_site_label_to_company_name(data_dir, tmp_path):
    """site_label (ไม่บังคับ) ใช้แยกกรณีบริษัทเดียวกันมีหลายมิเตอร์/หลายไซต์ที่ใช้ชื่อผู้ใช้ไฟ
    เดียวกันในไฟล์ export ทุกไฟล์ — ต้องต่อท้ายชื่อบริษัทเป็น "ชื่อบริษัท (site_label)" ทั้งใน
    on_profile callback และ import_log_local.csv"""
    _write_registered_customer(data_dir, account_no="0199000000")
    file_paths = _write_synthetic_files_with_header(
        tmp_path / "attached", account_no="0199000000", company_name="บริษัท ทดสอบ จำกัด"
    )

    received = {}
    amr_import.import_amr_from_files(
        file_paths=file_paths, data_dir=data_dir, on_profile=received.update, site_label="YMLC4"
    )

    assert received["name"] == "บริษัท ทดสอบ จำกัด (YMLC4)"

    from amr_mapping.loader import load_import_log_local

    entries = load_import_log_local(data_dir / "import_log_local.csv")
    assert entries[0]["company_name"] == "บริษัท ทดสอบ จำกัด (YMLC4)"


def test_import_amr_from_files_ignores_site_label_when_company_name_unknown(data_dir, tmp_path):
    """ไม่มีชื่อบริษัทให้ต่อท้ายเลย (อ่านจากไฟล์ไม่ได้) — site_label ต้องไม่ทำให้ได้ค่าประหลาดๆ
    แบบ " (YMLC4)" ลอยๆ ไม่มีอะไรนำหน้า"""
    _write_registered_customer(data_dir, account_no="0199000000")
    file_paths = _write_synthetic_files_with_header(tmp_path / "attached", account_no="0199000000", company_name="")

    received = {}
    amr_import.import_amr_from_files(
        file_paths=file_paths, data_dir=data_dir, on_profile=received.update, site_label="YMLC4"
    )

    assert received["name"] == ""


def test_import_amr_from_files_uses_tariff_from_file_as_billing_method(data_dir, tmp_path):
    _write_registered_customer(data_dir, account_no="0199000000")
    file_paths = _write_synthetic_files_with_header(tmp_path / "attached", account_no="0199000000", tariff="NORMAL")

    profile = amr_import.import_amr_from_files(file_paths=file_paths, data_dir=data_dir)

    assert profile.billing_method == "NORMAL"


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


def test_import_amr_auto_saves_has_solar_and_logs_it(monkeypatch, data_dir):
    monkeypatch.setattr(amr_import, "download_amr_with_profile", _fake_download_amr_with_profile)

    profile = amr_import.import_amr_auto(
        username="019900000001", password="secret-pass",
        start_date="2026-07-01", end_date="2026-08-31",
        has_solar=True,
        data_dir=data_dir, download_dir=data_dir.parent / "downloads",
    )
    assert profile.has_solar is True

    from amr_mapping.loader import load_import_log_local

    log_entries = load_import_log_local(data_dir / "import_log_local.csv")
    assert log_entries[0]["has_solar"] == "true"


def test_import_amr_auto_saves_site_curve_local(monkeypatch, data_dir):
    """โหมด auto ต้องบันทึกกราฟแยกของไซต์นี้ไว้ที่ site_curves_local.csv ด้วย (แยกจาก
    load_curves.csv ซึ่งเป็นค่าเฉลี่ยรวม anonymized) เพราะมีชื่อบริษัท/เลขบัญชีจริงจาก scrape"""

    monkeypatch.setattr(amr_import, "download_amr_with_profile", _fake_download_amr_with_profile)

    amr_import.import_amr_auto(
        username="019900000001", password="secret-pass",
        start_date="2026-07-01", end_date="2026-08-31",
        data_dir=data_dir, download_dir=data_dir.parent / "downloads",
    )

    from amr_mapping.loader import load_site_curves_local

    site_curves = load_site_curves_local(data_dir / "site_curves_local.csv")
    assert len(site_curves) == 1
    assert site_curves[0]["company_name"] == "บริษัท ทดสอบออโต้ จำกัด"
    assert site_curves[0]["account_no"] == "019900000001"
    assert site_curves[0]["business_type_code"] == "34111"
    # ข้อมูล synthetic มีจุดเดียวที่ชม.9 (RATE A 20.00 -> 80 kW) ในวันเสาร์ (01/08/2026)
    assert site_curves[0]["hours"]["sat"][9] == pytest.approx(80.0)


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
