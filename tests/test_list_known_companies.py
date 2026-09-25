import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from amr_mapping.loader import append_import_log_local
from list_known_companies import collect_known_companies


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "reference"
    d.mkdir()
    (d / "business_types.csv").write_text("code,name_th,category,notes\nTESTBIZ,ธุรกิจทดสอบ,test,\n", encoding="utf-8")
    (d / "rate_schedules.csv").write_text("code,billing_method,voltage_level,description\n50,TOU,LV,\n", encoding="utf-8")
    (d / "load_profiles.csv").write_text(
        "business_type_code,rate_code,billing_method,demand_p_kw,demand_op_kw,demand_h_kw,"
        "energy_p_kwh,energy_op_kwh,energy_h_kwh,contract_kva_ref,sample_size,notes\n",
        encoding="utf-8",
    )
    return d


def test_collects_from_import_log_only(data_dir):
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

    rows = collect_known_companies(data_dir)
    assert rows == {"0199000001": {"name": "บริษัท เอ", "business_type_code": "TESTBIZ", "rate_code": "50"}}


def test_customer_registry_wins_over_import_log_for_same_account(data_dir):
    append_import_log_local(
        {
            "imported_at": "2026-07-01T00:00:00+00:00",
            "business_type_code": "OLDBIZ",
            "rate_code": "40",
            "company_name": "บริษัท เอ (ชื่อเก่า)",
            "account_no": "0199000001",
            "has_solar": "false",
        },
        data_dir / "import_log_local.csv",
    )
    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000001,บริษัท เอ,TESTBIZ,50,,false,,\n",
        encoding="utf-8",
    )

    rows = collect_known_companies(data_dir)
    assert rows["0199000001"] == {"name": "บริษัท เอ", "business_type_code": "TESTBIZ", "rate_code": "50"}


def test_merges_accounts_from_both_sources(data_dir):
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
    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000002,บริษัท บี,TESTBIZ,50,,false,,\n",
        encoding="utf-8",
    )

    rows = collect_known_companies(data_dir)
    assert set(rows) == {"0199000001", "0199000002"}


def test_empty_when_nothing_known(data_dir):
    assert collect_known_companies(data_dir) == {}
