import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import load_reference_data, save_business_types, upsert_customer_local
from amr_mapping.models import BusinessType, Customer

_BUSINESS_TYPES_CSV = "code,name_th,category,notes\nTESTBIZ,ธุรกิจทดสอบ,test,\n"
_CUSTOMERS_CSV = (
    "account_no,name,business_type_code,has_amr\n"
    "DEMO-001,ลูกค้าสมมติ (public),TESTBIZ,false\n"
)


def _make_data_dir(tmp_path, customers_local_csv=None):
    d = tmp_path / "reference"
    d.mkdir()
    (d / "business_types.csv").write_text(_BUSINESS_TYPES_CSV, encoding="utf-8")
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
        "account_no,name,business_type_code,has_amr\n"
        "REAL-ACCOUNT-001,บริษัท ตัวอย่างจริง จำกัด,TESTBIZ,false\n"
    )
    data_dir = _make_data_dir(tmp_path, customers_local_csv=local_csv)
    reference = load_reference_data(data_dir)

    accounts = {c.account_no for c in reference.customers}
    assert accounts == {"DEMO-001", "REAL-ACCOUNT-001"}

    real = next(c for c in reference.customers if c.account_no == "REAL-ACCOUNT-001")
    assert real.name == "บริษัท ตัวอย่างจริง จำกัด"
    assert real.business_type_code == "TESTBIZ"


def test_business_types_hierarchy_fields_round_trip(tmp_path):
    """section_code/division_code เป็นคอลัมน์ใหม่ (เพิ่มเข้ามาทีหลัง สำหรับจับคู่แบบผ่อนลงเมื่อไม่มี
    รหัส TSIC ตรงเป๊ะในระบบ — ดู web/app.py:_suggest_business_type_for_division) — ต้อง save/load
    กลับมาได้ครบ"""

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


def test_save_business_types_writes_lf_line_endings_not_crlf(tmp_path):
    """csv.DictWriter เขียน \\r\\n เป็นค่าเริ่มต้นถ้าไม่ตั้ง lineterminator เอง — ทำให้ไฟล์ที่เขียน
    กลับด้วยฟังก์ชันนี้กลายเป็น CRLF ทั้งไฟล์ทั้งที่ไฟล์เดิมในโปรเจกต์ใช้ LF ล้วน สร้าง diff รก
    ทุกครั้งที่บันทึกโดยไม่จำเป็น (เจอจริงตอนเพิ่มแถวใหม่ใน business_types.csv)"""

    data_dir = _make_data_dir(tmp_path)

    bt = BusinessType(code="17011", name_th="ผลิตเยื่อกระดาษ", category="paper", notes="ทดสอบ")
    save_business_types({"17011": bt}, data_dir / "business_types.csv")
    assert b"\r\n" not in (data_dir / "business_types.csv").read_bytes()


def test_business_types_without_hierarchy_columns_still_loads(tmp_path):
    """ไฟล์ business_types.csv แบบเก่า (ไม่มีคอลัมน์ section_code/division_code เลย) ต้องยัง
    โหลดได้ตามปกติ ไม่ error - hierarchy fields เป็น None/ค่าว่างแทน"""

    data_dir = _make_data_dir(tmp_path)  # ใช้ _BUSINESS_TYPES_CSV เดิมที่ไม่มีคอลัมน์ใหม่
    reference = load_reference_data(data_dir)
    bt = reference.business_types["TESTBIZ"]
    assert bt.section_code is None
    assert bt.division_code is None


def test_customers_local_overrides_same_account_no(tmp_path):
    local_csv = (
        "account_no,name,business_type_code,has_amr\n"
        "DEMO-001,ชื่อจริงที่ override ชื่อสมมติ,TESTBIZ,false\n"
    )
    data_dir = _make_data_dir(tmp_path, customers_local_csv=local_csv)
    reference = load_reference_data(data_dir)

    # ต้องมีแค่รายการเดียว (ไม่ใช่ทั้งสองชื่อ) และใช้ข้อมูลจาก local แทน
    matching = [c for c in reference.customers if c.account_no == "DEMO-001"]
    assert len(matching) == 1
    assert matching[0].name == "ชื่อจริงที่ override ชื่อสมมติ"


def test_upsert_customer_local_creates_then_replaces_same_account(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    path = data_dir / "customers_local.csv"

    first = Customer(account_no="ACC-1", name="บริษัท เอ", business_type_code="TESTBIZ")
    upsert_customer_local(path, first)

    updated = Customer(account_no="ACC-1", name="บริษัท เอ (แก้ชื่อ)", business_type_code="TESTBIZ")
    result = upsert_customer_local(path, updated)

    matching = [c for c in result if c.account_no == "ACC-1"]
    assert len(matching) == 1
    assert matching[0].name == "บริษัท เอ (แก้ชื่อ)"
