import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import load_reference_data

_BUSINESS_TYPES_CSV = "code,name_th,category,notes\nTESTBIZ,ธุรกิจทดสอบ,test,\n"
_RATE_SCHEDULES_CSV = "code,billing_method,voltage_level,description\n50,TOU,LV,\n"
_LOAD_PROFILES_CSV = (
    "business_type_code,rate_code,billing_method,demand_p_kw,demand_op_kw,demand_h_kw,"
    "energy_p_kwh,energy_op_kwh,energy_h_kwh,contract_kva_ref,sample_size,notes\n"
)
_CUSTOMERS_CSV = (
    "account_no,name,business_type_code,rate_code,contract_kva,has_amr\n"
    "DEMO-001,ลูกค้าสมมติ (public),TESTBIZ,50,1000,false\n"
)


def _make_data_dir(tmp_path, customers_local_csv=None):
    d = tmp_path / "reference"
    d.mkdir()
    (d / "business_types.csv").write_text(_BUSINESS_TYPES_CSV, encoding="utf-8")
    (d / "rate_schedules.csv").write_text(_RATE_SCHEDULES_CSV, encoding="utf-8")
    (d / "load_profiles.csv").write_text(_LOAD_PROFILES_CSV, encoding="utf-8")
    (d / "customers.csv").write_text(_CUSTOMERS_CSV, encoding="utf-8")
    if customers_local_csv is not None:
        (d / "customers_local.csv").write_text(customers_local_csv, encoding="utf-8")
    return d


def test_load_reference_data_without_local_file(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    reference = load_reference_data(data_dir)

    accounts = {c.account_no for c in reference.customers}
    assert accounts == {"DEMO-001"}


def test_load_reference_data_merges_customers_local(tmp_path):
    local_csv = (
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr\n"
        "REAL-ACCOUNT-001,บริษัท ตัวอย่างจริง จำกัด,TESTBIZ,50,2000,false\n"
    )
    data_dir = _make_data_dir(tmp_path, customers_local_csv=local_csv)
    reference = load_reference_data(data_dir)

    accounts = {c.account_no for c in reference.customers}
    assert accounts == {"DEMO-001", "REAL-ACCOUNT-001"}

    real = next(c for c in reference.customers if c.account_no == "REAL-ACCOUNT-001")
    assert real.name == "บริษัท ตัวอย่างจริง จำกัด"
    assert real.contract_kva == 2000.0


def test_customers_local_overrides_same_account_no(tmp_path):
    local_csv = (
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr\n"
        "DEMO-001,ชื่อจริงที่ override ชื่อสมมติ,TESTBIZ,50,9999,false\n"
    )
    data_dir = _make_data_dir(tmp_path, customers_local_csv=local_csv)
    reference = load_reference_data(data_dir)

    # ต้องมีแค่รายการเดียว (ไม่ใช่ทั้งสองชื่อ) และใช้ข้อมูลจาก local แทน
    matching = [c for c in reference.customers if c.account_no == "DEMO-001"]
    assert len(matching) == 1
    assert matching[0].name == "ชื่อจริงที่ override ชื่อสมมติ"
    assert matching[0].contract_kva == 9999.0
