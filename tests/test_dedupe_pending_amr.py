import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from amr_mapping.loader import append_import_log_local, append_pending_amr_local, load_pending_amr_local
from dedupe_pending_amr import find_redundant_pending_entries


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


def _add_pending(data_dir, pending_id, account_no, company_name):
    append_pending_amr_local(
        {
            "pending_id": pending_id,
            "created_at": f"2026-08-{pending_id[-2:]}T00:00:00+00:00",
            "account_no": account_no,
            "company_name": company_name,
            "meter_no": "",
            "file_paths": "/tmp/fake.xls",
            "contract_kva": "",
            "has_solar": "false",
            "source_label": "",
        },
        data_dir / "pending_amr_local.csv",
    )


def test_no_redundant_entries_when_nothing_overlaps(data_dir):
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")
    _add_pending(data_dir, "pend02", "0199000002", "บริษัท บี")

    redundant = find_redundant_pending_entries(data_dir)
    assert redundant == []


def test_flags_entry_already_known_in_customer_registry(data_dir):
    (d := data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000001,บริษัท เอ,TESTBIZ,50,,false,,\n",
        encoding="utf-8",
    )
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")

    redundant = find_redundant_pending_entries(data_dir)
    assert len(redundant) == 1
    entry, reason = redundant[0]
    assert entry["pending_id"] == "pend01"
    assert "TESTBIZ/50" in reason


def test_flags_entry_already_in_import_log(data_dir):
    append_import_log_local(
        {
            "imported_at": "2026-07-01T00:00:00+00:00",
            "business_type_code": "TESTBIZ",
            "rate_code": "50",
            "company_name": "บริษัท เอ",
            "account_no": "0199000001",
            "has_solar": "false",
        },
        data_dir / "import_log_local.csv",
    )
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")

    redundant = find_redundant_pending_entries(data_dir)
    assert len(redundant) == 1
    assert "import_log_local.csv" in redundant[0][1]


def test_flags_later_duplicate_pending_entry_for_same_account(data_dir):
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ (ครั้งแรก)")
    _add_pending(data_dir, "pend02", "0199000001", "บริษัท เอ (ครั้งที่สอง — ซ้ำซ้อน)")

    redundant = find_redundant_pending_entries(data_dir)
    assert len(redundant) == 1
    entry, reason = redundant[0]
    # เก็บรายการแรกสุดไว้ (ไม่แฟล็ก) รายการที่เข้ามาทีหลังถือว่าซ้ำซ้อน
    assert entry["pending_id"] == "pend02"
    assert "pend01" in reason


def test_entries_without_account_no_are_never_flagged(data_dir):
    _add_pending(data_dir, "pend01", "", "โฟลเดอร์ที่อ่านเลขบัญชีไม่ได้")
    _add_pending(data_dir, "pend02", "", "อีกโฟลเดอร์ที่อ่านเลขบัญชีไม่ได้")

    redundant = find_redundant_pending_entries(data_dir)
    assert redundant == []


def test_pending_amr_local_missing_file_returns_empty(data_dir):
    assert find_redundant_pending_entries(data_dir) == []
