import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import amr_import
from amr_mapping.amr_downloader import DownloadResult
from amr_mapping.loader import load_reference_data

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


def test_import_amr_for_business_cleans_up_download_dir(monkeypatch, data_dir, tmp_path):
    captured_dirs = []

    def spy_download(username, password, accounts, start_date, end_date, download_dir, log, headless=True):
        captured_dirs.append(download_dir)
        return _fake_download_amr_kw_reports(username, password, accounts, start_date, end_date, download_dir, log, headless)

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", spy_download)

    amr_import.import_amr_for_business(
        username="u", password="p", accounts=["123"],
        start_date="2026-07-01", end_date="2026-08-31",
        business_type_code="TESTBIZ", rate_code="50", contract_kva=None,
        source_label="", data_dir=data_dir,
    )

    assert len(captured_dirs) == 1
    assert not os.path.exists(captured_dirs[0]), "ไฟล์ดิบที่ดาวน์โหลดมาต้องถูกลบทิ้งหลังประมวลผลเสร็จ"


def test_import_amr_for_business_raises_when_no_files_downloaded(monkeypatch, data_dir):
    def empty_download(*args, **kwargs):
        return []

    monkeypatch.setattr(amr_import, "download_amr_kw_reports", empty_download)

    with pytest.raises(RuntimeError):
        amr_import.import_amr_for_business(
            username="u", password="p", accounts=["123"],
            start_date="2026-07-01", end_date="2026-08-31",
            business_type_code="TESTBIZ", rate_code="50", contract_kva=None,
            source_label="", data_dir=data_dir,
        )
