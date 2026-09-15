import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import load_reference_data, save_business_types, save_load_curves, upsert_load_curve
from amr_mapping.models import BusinessType, LoadCurve

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


def test_business_types_hierarchy_fields_round_trip(tmp_path):
    """section_code/division_code เป็นคอลัมน์ใหม่ (เพิ่มเข้ามาทีหลัง สำหรับ DIVISION_ONLY
    fallback ใน mapping.find_load_profile) — ต้อง save/load กลับมาได้ครบ"""

    data_dir = _make_data_dir(tmp_path)
    bt = BusinessType(
        code="17011", name_th="ผลิตเยื่อกระดาษ", category="paper", notes="ทดสอบ",
        section_code="C", section_name_th="การผลิต", division_code="17", division_name_th="การผลิตกระดาษ",
    )
    save_business_types({"17011": bt}, data_dir / "business_types.csv")

    reference = load_reference_data(data_dir)
    loaded = reference.business_types["17011"]
    assert loaded.section_code == "C"
    assert loaded.division_code == "17"
    assert loaded.division_name_th == "การผลิตกระดาษ"


def test_business_types_without_hierarchy_columns_still_loads(tmp_path):
    """ไฟล์ business_types.csv แบบเก่า (ไม่มีคอลัมน์ section_code/division_code เลย) ต้องยัง
    โหลดได้ตามปกติ ไม่ error - hierarchy fields เป็น None/ค่าว่างแทน"""

    data_dir = _make_data_dir(tmp_path)  # ใช้ _BUSINESS_TYPES_CSV เดิมที่ไม่มีคอลัมน์ใหม่
    reference = load_reference_data(data_dir)
    bt = reference.business_types["TESTBIZ"]
    assert bt.section_code is None
    assert bt.division_code is None


def test_load_reference_data_without_load_curves_file_is_empty_not_error(tmp_path):
    """load_curves.csv เป็นฟีเจอร์เสริมที่เพิ่มเข้ามาทีหลัง — data dir เก่าที่ยังไม่มีไฟล์นี้
    ต้องโหลดได้ตามปกติ (load_curves เป็น list ว่าง) ไม่ error"""

    data_dir = _make_data_dir(tmp_path)
    reference = load_reference_data(data_dir)
    assert reference.load_curves == []


def test_save_and_load_load_curves_round_trip(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    curve = LoadCurve(
        business_type_code="TESTBIZ",
        rate_code="50",
        hours={
            "all": [1.0 if h == 9 else None for h in range(24)],
            "mon": [2.5 if h == 9 else None for h in range(24)],
        },
        contract_kva_ref=1000.0,
        sample_size=2,
        notes="ทดสอบ round trip",
    )
    save_load_curves([curve], data_dir / "load_curves.csv")

    reference = load_reference_data(data_dir)
    assert len(reference.load_curves) == 1
    loaded = reference.load_curves[0]
    assert loaded.business_type_code == "TESTBIZ"
    assert loaded.rate_code == "50"
    assert loaded.contract_kva_ref == 1000.0
    assert loaded.sample_size == 2
    assert loaded.hours["all"][9] == 1.0
    assert loaded.hours["mon"][9] == 2.5
    assert loaded.hours["all"][0] is None
    # day_type ที่ไม่ได้เขียนไว้เลย (เช่น "tue") ต้องไม่อยู่ใน hours
    assert "tue" not in loaded.hours


def test_upsert_load_curve_replaces_same_key():
    old = LoadCurve(business_type_code="A", rate_code="1", hours={"all": [1.0] * 24})
    other = LoadCurve(business_type_code="B", rate_code="2", hours={"all": [2.0] * 24})
    new = LoadCurve(business_type_code="A", rate_code="1", hours={"all": [9.0] * 24}, notes="ใหม่")

    result = upsert_load_curve([old, other], new)

    assert len(result) == 2
    updated = next(c for c in result if c.key() == ("A", "1"))
    assert updated.notes == "ใหม่"
    assert updated.hours["all"][0] == 9.0


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
