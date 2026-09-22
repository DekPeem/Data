import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import (
    _IMPORT_LOG_FIELDNAMES,
    append_import_log_local,
    append_pending_amr_local,
    append_site_curve_local,
    load_import_log_local,
    load_pending_amr_local,
    load_reference_data,
    load_site_curves_local,
    remove_import_log_local_entry,
    remove_pending_amr_local,
    save_business_types,
    save_load_curves,
    save_load_profiles,
    upsert_load_curve,
    upsert_load_profile,
)
from amr_mapping.models import BusinessType, LoadCurve, LoadProfile

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


def test_load_profiles_without_has_solar_column_defaults_to_false(tmp_path):
    """ไฟล์ load_profiles.csv แบบเก่า (ไม่มีคอลัมน์ has_solar เลย) ต้องยังโหลดได้ตามปกติ —
    has_solar เป็น False แทน (ไม่ error)"""

    data_dir = _make_data_dir(tmp_path)
    (data_dir / "load_profiles.csv").write_text(
        _LOAD_PROFILES_CSV + "TESTBIZ,50,TOU,10,10,10,100,100,100,1000,3,เก่า\n", encoding="utf-8"
    )

    reference = load_reference_data(data_dir)
    profile = next(p for p in reference.load_profiles if p.business_type_code == "TESTBIZ")
    assert profile.has_solar is False


def test_save_and_load_load_profiles_round_trip_with_has_solar(tmp_path):
    data_dir = _make_data_dir(tmp_path)
    profile = LoadProfile(
        business_type_code="TESTBIZ", rate_code="50", billing_method="TOU",
        demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1},
        has_solar=True,
    )
    save_load_profiles([profile], data_dir / "load_profiles.csv")

    reference = load_reference_data(data_dir)
    loaded = next(p for p in reference.load_profiles if p.business_type_code == "TESTBIZ")
    assert loaded.has_solar is True


def test_load_curves_has_solar_kept_as_separate_curves(tmp_path):
    """โปรไฟล์ธุรกิจ+อัตราเดียวกัน แต่ติด/ไม่ติด Solar ต่างกัน ต้องเก็บเป็นเส้นโค้งคนละเส้น
    ไม่ถูกรวมเป็นเส้นเดียวกันโดยไม่ตั้งใจ (has_solar เป็นส่วนหนึ่งของ key)"""

    data_dir = _make_data_dir(tmp_path)
    non_solar = LoadCurve(business_type_code="TESTBIZ", rate_code="50", hours={"all": [10.0] * 24}, has_solar=False)
    solar = LoadCurve(business_type_code="TESTBIZ", rate_code="50", hours={"all": [4.0] * 24}, has_solar=True)
    save_load_curves([non_solar, solar], data_dir / "load_curves.csv")

    reference = load_reference_data(data_dir)
    assert len(reference.load_curves) == 2
    by_solar = {c.has_solar: c for c in reference.load_curves}
    assert by_solar[False].hours["all"][0] == 10.0
    assert by_solar[True].hours["all"][0] == 4.0


def test_customers_has_solar_tri_state(tmp_path):
    """has_solar ของลูกค้าเป็น tri-state: คอลัมน์ว่าง/ไม่มีคอลัมน์ -> None (ไม่ทราบ) ต่างจาก
    False (ทราบแน่ชัดว่าไม่ติด Solar)"""

    local_csv = (
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar\n"
        "ACC-UNKNOWN,ไม่ทราบสถานะ,TESTBIZ,50,1000,false,\n"
        "ACC-SOLAR,ติด Solar แล้ว,TESTBIZ,50,1000,false,true\n"
        "ACC-NO-SOLAR,ไม่ติด Solar แน่นอน,TESTBIZ,50,1000,false,false\n"
    )
    data_dir = _make_data_dir(tmp_path, customers_local_csv=local_csv)
    reference = load_reference_data(data_dir)
    by_account = {c.account_no: c for c in reference.customers}

    assert by_account["ACC-UNKNOWN"].has_solar is None
    assert by_account["ACC-SOLAR"].has_solar is True
    assert by_account["ACC-NO-SOLAR"].has_solar is False
    # customers.csv เดิม (ไม่มีคอลัมน์ has_solar เลย) ก็ต้องเป็น None เหมือนกัน ไม่ error
    assert by_account["DEMO-001"].has_solar is None


def test_upsert_load_curve_replaces_same_key():
    old = LoadCurve(business_type_code="A", rate_code="1", hours={"all": [1.0] * 24})
    other = LoadCurve(business_type_code="B", rate_code="2", hours={"all": [2.0] * 24})
    new = LoadCurve(business_type_code="A", rate_code="1", hours={"all": [9.0] * 24}, notes="ใหม่")

    result = upsert_load_curve([old, other], new)

    assert len(result) == 2
    updated = next(c for c in result if c.key() == ("A", "1", False))
    assert updated.notes == "ใหม่"
    assert updated.hours["all"][0] == 9.0


def test_upsert_load_curve_merges_weighted_average_when_both_have_sample_size():
    """สองไซต์ share (business_type_code, rate_code, has_solar) เดียวกัน (เช่น รหัสอัตรา UNKNOWN)
    ต้องเฉลี่ยถ่วงน้ำหนักรวมกัน ไม่ใช่เขียนทับของเดิมทิ้งเฉยๆ — sample_size ต้องรวมกันด้วย"""

    old = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [10.0] * 24}, sample_size=6)
    new = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [20.0] * 24}, sample_size=6)

    result = upsert_load_curve([old], new)

    assert len(result) == 1
    merged = result[0]
    assert merged.sample_size == 12
    assert merged.hours["all"][0] == 15.0  # ถ่วงน้ำหนักเท่ากัน (6 กับ 6) -> ตรงกลางพอดี


def test_upsert_load_curve_merge_respects_unequal_weights():
    old = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [0.0] * 24}, sample_size=1)
    new = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [40.0] * 24}, sample_size=3)

    result = upsert_load_curve([old], new)

    merged = result[0]
    assert merged.sample_size == 4
    assert merged.hours["all"][0] == 30.0  # (0*1 + 40*3) / 4 = 30


def test_upsert_load_curve_merge_uses_available_side_when_hour_missing_on_one_side():
    old = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [None, 10.0] + [1.0] * 22}, sample_size=2)
    new = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [5.0, None] + [1.0] * 22}, sample_size=2)

    result = upsert_load_curve([old], new)

    merged = result[0]
    assert merged.hours["all"][0] == 5.0  # มีแค่ฝั่ง new เท่านั้น
    assert merged.hours["all"][1] == 10.0  # มีแค่ฝั่ง old เท่านั้น


def test_upsert_load_curve_merge_keeps_day_type_present_only_on_one_side():
    old = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [1.0] * 24, "mon": [2.0] * 24}, sample_size=2)
    new = LoadCurve(business_type_code="A", rate_code="UNKNOWN", hours={"all": [3.0] * 24}, sample_size=2)

    result = upsert_load_curve([old], new)

    merged = result[0]
    assert merged.hours["mon"][0] == 2.0  # มีแค่ใน old — ต้องยังอยู่ ไม่หายไปเฉยๆ
    assert merged.hours["all"][0] == 2.0  # (1*2 + 3*2) / 4


def test_upsert_load_curve_falls_back_to_replace_when_no_sample_size_info():
    """ทั้งคู่ sample_size=0 (ค่า default) — ไม่มีน้ำหนักให้ถ่วง ต้องแค่ใช้ของใหม่แทนของเก่าไปเลย
    (พฤติกรรมเดิมก่อนมีการเฉลี่ยรวม)"""
    old = LoadCurve(business_type_code="A", rate_code="1", hours={"all": [1.0] * 24})
    new = LoadCurve(business_type_code="A", rate_code="1", hours={"all": [9.0] * 24})

    result = upsert_load_curve([old], new)

    assert result[0].hours["all"][0] == 9.0
    assert result[0].sample_size == 0


def test_upsert_load_profile_merges_weighted_average_when_both_have_sample_size():
    old = LoadProfile(
        business_type_code="A", rate_code="UNKNOWN", billing_method="TOU",
        demand_kw={"P": 100.0, "OP": 50.0, "H": 60.0}, energy_kwh={"P": 1000.0, "OP": 500.0, "H": 600.0},
        contract_kva_ref=1000.0, sample_size=6,
    )
    new = LoadProfile(
        business_type_code="A", rate_code="UNKNOWN", billing_method="TOU",
        demand_kw={"P": 200.0, "OP": 150.0, "H": 160.0}, energy_kwh={"P": 2000.0, "OP": 1500.0, "H": 1600.0},
        contract_kva_ref=2000.0, sample_size=6,
    )

    result = upsert_load_profile([old], new)

    assert len(result) == 1
    merged = result[0]
    assert merged.sample_size == 12
    assert merged.demand_kw["P"] == 150.0
    assert merged.demand_kw["OP"] == 100.0
    assert merged.energy_kwh["P"] == 1500.0
    assert merged.contract_kva_ref == 1500.0


def test_upsert_load_profile_merge_uses_present_kva_when_only_one_side_has_it():
    old = LoadProfile(
        business_type_code="A", rate_code="UNKNOWN", billing_method="TOU",
        demand_kw={"P": 1.0, "OP": 1.0, "H": 1.0}, energy_kwh={"P": 1.0, "OP": 1.0, "H": 1.0},
        contract_kva_ref=None, sample_size=1,
    )
    new = LoadProfile(
        business_type_code="A", rate_code="UNKNOWN", billing_method="TOU",
        demand_kw={"P": 1.0, "OP": 1.0, "H": 1.0}, energy_kwh={"P": 1.0, "OP": 1.0, "H": 1.0},
        contract_kva_ref=500.0, sample_size=1,
    )

    result = upsert_load_profile([old], new)

    assert result[0].contract_kva_ref == 500.0


def test_upsert_load_profile_adds_new_entry_when_key_not_seen_before():
    existing = LoadProfile(
        business_type_code="A", rate_code="1", billing_method="TOU",
        demand_kw={"P": 1.0, "OP": 1.0, "H": 1.0}, energy_kwh={"P": 1.0, "OP": 1.0, "H": 1.0}, sample_size=1,
    )
    new = LoadProfile(
        business_type_code="B", rate_code="2", billing_method="TOU",
        demand_kw={"P": 2.0, "OP": 2.0, "H": 2.0}, energy_kwh={"P": 2.0, "OP": 2.0, "H": 2.0}, sample_size=1,
    )

    result = upsert_load_profile([existing], new)

    assert len(result) == 2
    assert any(p.key() == ("B", "2", False) for p in result)


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


def test_load_import_log_local_returns_empty_when_file_missing(tmp_path):
    assert load_import_log_local(tmp_path / "no_such_file.csv") == []


def test_append_import_log_local_creates_file_with_header_then_appends(tmp_path):
    path = tmp_path / "import_log_local.csv"

    append_import_log_local(
        {"imported_at": "2026-09-15T10:00:00+00:00", "business_type_code": "34111", "rate_code": "40",
         "company_name": "บริษัท ทดสอบ จำกัด", "account_no": "019900000001"},
        path,
    )
    append_import_log_local(
        {"imported_at": "2026-09-15T11:00:00+00:00", "business_type_code": "34120", "rate_code": "30",
         "company_name": "บริษัท ทดสอบสอง จำกัด", "account_no": "019900000002"},
        path,
    )

    entries = load_import_log_local(path)
    assert len(entries) == 2
    assert entries[0]["company_name"] == "บริษัท ทดสอบ จำกัด"
    assert entries[1]["business_type_code"] == "34120"


def test_append_import_log_local_migrates_old_header_before_appending(tmp_path):
    # ไฟล์เก่าที่เขียนไว้ก่อนเพิ่มคอลัมน์ has_solar (header มีแค่ 5 คอลัมน์)
    path = tmp_path / "import_log_local.csv"
    path.write_text(
        "imported_at,business_type_code,rate_code,company_name,account_no\r\n"
        "2026-09-15T09:14:05+00:00,31212,30,บริษัท เก่า จำกัด,019900000001\r\n",
        encoding="utf-8",
    )

    append_import_log_local(
        {"imported_at": "2026-09-16T02:41:34+00:00", "business_type_code": "34111", "rate_code": "40",
         "company_name": "บริษัท ใหม่ จำกัด", "account_no": "019900000002", "has_solar": "false"},
        path,
    )

    entries = load_import_log_local(path)
    assert len(entries) == 2
    # แถวเก่าถูกย้าย header แล้วเติม has_solar ว่างให้ (ไม่ใช่ ragged row อีกต่อไป)
    assert entries[0]["has_solar"] == ""
    assert entries[0]["company_name"] == "บริษัท เก่า จำกัด"
    assert entries[1]["has_solar"] == "false"
    assert set(entries[0].keys()) == set(_IMPORT_LOG_FIELDNAMES)
    assert set(entries[1].keys()) == set(_IMPORT_LOG_FIELDNAMES)


def test_append_import_log_local_leaves_current_header_untouched(tmp_path):
    path = tmp_path / "import_log_local.csv"
    append_import_log_local(
        {"imported_at": "2026-09-15T10:00:00+00:00", "business_type_code": "34111", "rate_code": "40",
         "company_name": "บริษัท ทดสอบ จำกัด", "account_no": "019900000001", "has_solar": "true"},
        path,
    )
    before = path.read_text(encoding="utf-8")

    append_import_log_local(
        {"imported_at": "2026-09-15T11:00:00+00:00", "business_type_code": "34120", "rate_code": "30",
         "company_name": "บริษัท ทดสอบสอง จำกัด", "account_no": "019900000002", "has_solar": "false"},
        path,
    )

    # แถวแรกที่เขียนไว้ก่อนหน้าไม่ถูกแก้ไข/เขียนซ้ำโดยไม่จำเป็น
    assert path.read_text(encoding="utf-8").startswith(before)
    entries = load_import_log_local(path)
    assert len(entries) == 2
    assert entries[0]["has_solar"] == "true"
    assert entries[1]["has_solar"] == "false"


def test_load_import_log_local_drops_ragged_extra_columns(tmp_path):
    # แถวที่มีค่ามากกว่าคอลัมน์ที่ header ประกาศไว้ (เช่นไฟล์เก่าที่ยังไม่ได้ migrate) ต้องไม่
    # ทำให้อ่านพัง และไม่ควรมีคีย์ None (restkey) หลุดออกมา เพราะ jsonify() จะ sort คีย์แบบผสม
    # ชนิดไม่ได้ (None เทียบกับ str ไม่ได้) แล้วพังตอน serialize
    path = tmp_path / "import_log_local.csv"
    path.write_text(
        "imported_at,business_type_code,rate_code,company_name,account_no\r\n"
        "2026-09-16T02:41:34+00:00,34111,40,บริษัท ทดสอบสาม จำกัด,019900000001,false\r\n",
        encoding="utf-8",
    )

    entries = load_import_log_local(path)
    assert len(entries) == 1
    assert None not in entries[0]
    assert entries[0]["account_no"] == "019900000001"


def test_remove_import_log_local_entry_removes_matching_row_only(tmp_path):
    path = tmp_path / "import_log_local.csv"
    append_import_log_local(
        {
            "imported_at": "2026-09-16T02:41:34+00:00",
            "business_type_code": "34111",
            "rate_code": "40",
            "company_name": "บริษัท ทดสอบสาม จำกัด",
            "account_no": "019900000001",
            "has_solar": "false",
        },
        path,
    )
    append_import_log_local(
        {
            "imported_at": "2026-09-17T02:41:34+00:00",
            "business_type_code": "63201",
            "rate_code": "50",
            "company_name": "บริษัท ทดสอบสี่ จำกัด",
            "account_no": "019900000002",
            "has_solar": "false",
        },
        path,
    )

    removed = remove_import_log_local_entry("2026-09-16T02:41:34+00:00", "019900000001", path)

    assert removed is True
    entries = load_import_log_local(path)
    assert len(entries) == 1
    assert entries[0]["account_no"] == "019900000002"


def test_remove_import_log_local_entry_returns_false_when_not_found(tmp_path):
    path = tmp_path / "import_log_local.csv"
    append_import_log_local(
        {
            "imported_at": "2026-09-16T02:41:34+00:00",
            "business_type_code": "34111",
            "rate_code": "40",
            "company_name": "บริษัท ทดสอบสาม จำกัด",
            "account_no": "019900000001",
            "has_solar": "false",
        },
        path,
    )

    assert remove_import_log_local_entry("not-a-real-timestamp", "019900000001", path) is False
    assert len(load_import_log_local(path)) == 1


def test_remove_import_log_local_entry_returns_false_when_file_missing(tmp_path):
    assert remove_import_log_local_entry("2026-09-16T02:41:34+00:00", "019900000001", tmp_path / "no_such_file.csv") is False


def test_load_site_curves_local_returns_empty_when_file_missing(tmp_path):
    assert load_site_curves_local(tmp_path / "no_such_file.csv") == []


def test_append_and_load_site_curve_local_round_trip(tmp_path):
    path = tmp_path / "site_curves_local.csv"
    curve = LoadCurve(
        business_type_code="34111", rate_code="40",
        hours={"all": [1.0 if h == 9 else None for h in range(24)]},
        sample_size=12, has_solar=True,
    )

    append_site_curve_local("บริษัท ทดสอบ จำกัด", "019900000001", curve, path)

    entries = load_site_curves_local(path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["company_name"] == "บริษัท ทดสอบ จำกัด"
    assert entry["account_no"] == "019900000001"
    assert entry["business_type_code"] == "34111"
    assert entry["rate_code"] == "40"
    assert entry["has_solar"] is True
    assert entry["sample_size"] == 12
    assert entry["hours"]["all"][9] == 1.0
    assert entry["hours"]["all"][0] is None


def test_load_site_curves_local_keeps_latest_reimport(tmp_path):
    """เลขบัญชีเดียวกันถูกนำเข้าซ้ำ (append รอบสอง) — ต้องได้ข้อมูลจากรอบล่าสุดเสมอ ไม่ใช่
    รอบแรกหรือค่าผสมกัน"""

    path = tmp_path / "site_curves_local.csv"
    old_curve = LoadCurve(business_type_code="34111", rate_code="40", hours={"all": [1.0] * 24}, sample_size=6)
    new_curve = LoadCurve(business_type_code="34111", rate_code="40", hours={"all": [9.0] * 24}, sample_size=12)

    append_site_curve_local("บริษัท ทดสอบ จำกัด", "019900000001", old_curve, path)
    append_site_curve_local("บริษัท ทดสอบ จำกัด", "019900000001", new_curve, path)

    entries = load_site_curves_local(path)
    assert len(entries) == 1
    assert entries[0]["sample_size"] == 12
    assert entries[0]["hours"]["all"][0] == 9.0


def test_load_site_curves_local_keeps_separate_accounts_distinct(tmp_path):
    """บริษัทเดียวกันแต่คนละเลขบัญชี (คนละไซต์) ต้องแยกกันคนละรายการ ไม่ถูกรวมกัน"""

    path = tmp_path / "site_curves_local.csv"
    curve_a = LoadCurve(business_type_code="34111", rate_code="40", hours={"all": [1.0] * 24}, sample_size=6)
    curve_b = LoadCurve(business_type_code="34111", rate_code="40", hours={"all": [2.0] * 24}, sample_size=6)

    append_site_curve_local("บริษัท เดียวกัน จำกัด", "SITE-A", curve_a, path)
    append_site_curve_local("บริษัท เดียวกัน จำกัด", "SITE-B", curve_b, path)

    entries = {e["account_no"]: e for e in load_site_curves_local(path)}
    assert len(entries) == 2
    assert entries["SITE-A"]["hours"]["all"][0] == 1.0
    assert entries["SITE-B"]["hours"]["all"][0] == 2.0


def test_load_pending_amr_local_returns_empty_when_file_missing(tmp_path):
    assert load_pending_amr_local(tmp_path / "no_such_file.csv") == []


def test_append_pending_amr_local_creates_file_with_header_then_appends(tmp_path):
    path = tmp_path / "pending_amr_local.csv"
    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000001",
            "company_name": "บริษัท ทดสอบ จำกัด",
            "meter_no": "MT-1",
            "file_paths": "/tmp/a.xls|/tmp/b.xls",
            "contract_kva": "1000",
            "has_solar": "false",
            "source_label": "",
        },
        path,
    )
    append_pending_amr_local(
        {
            "pending_id": "def456",
            "created_at": "2026-01-02T00:00:00+00:00",
            "account_no": "019900000002",
            "company_name": "บริษัท สอง จำกัด",
            "meter_no": "",
            "file_paths": "/tmp/c.xls",
            "contract_kva": "",
            "has_solar": "true",
            "source_label": "",
        },
        path,
    )

    entries = load_pending_amr_local(path)
    assert len(entries) == 2
    assert entries[0]["pending_id"] == "abc123"
    assert entries[0]["file_paths"] == "/tmp/a.xls|/tmp/b.xls"
    assert entries[1]["pending_id"] == "def456"
    assert entries[1]["has_solar"] == "true"


def test_remove_pending_amr_local_removes_matching_row_only(tmp_path):
    path = tmp_path / "pending_amr_local.csv"
    for pending_id in ("abc123", "def456"):
        append_pending_amr_local(
            {
                "pending_id": pending_id,
                "created_at": "2026-01-01T00:00:00+00:00",
                "account_no": pending_id,
                "company_name": "",
                "meter_no": "",
                "file_paths": "/tmp/x.xls",
                "contract_kva": "",
                "has_solar": "false",
                "source_label": "",
            },
            path,
        )

    removed = remove_pending_amr_local("abc123", path)

    assert removed is True
    entries = load_pending_amr_local(path)
    assert len(entries) == 1
    assert entries[0]["pending_id"] == "def456"


def test_remove_pending_amr_local_returns_false_when_id_not_found(tmp_path):
    path = tmp_path / "pending_amr_local.csv"
    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "abc123",
            "company_name": "",
            "meter_no": "",
            "file_paths": "/tmp/x.xls",
            "contract_kva": "",
            "has_solar": "false",
            "source_label": "",
        },
        path,
    )

    assert remove_pending_amr_local("not-found", path) is False
    assert len(load_pending_amr_local(path)) == 1


def test_remove_pending_amr_local_returns_false_when_file_missing(tmp_path):
    assert remove_pending_amr_local("abc123", tmp_path / "no_such_file.csv") is False
