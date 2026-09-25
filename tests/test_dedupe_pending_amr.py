import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from amr_mapping.loader import (
    append_import_log_local,
    append_pending_amr_local,
    compute_file_signature,
    load_pending_amr_local,
    load_reference_data,
)
import dedupe_pending_amr
from dedupe_pending_amr import (
    find_deletable_entries,
    find_name_match_candidates,
    find_resolvable_entries,
    main,
    resolve_entry,
)

# เหมือน _SYNTHETIC_INTERVAL_HTML ใน tests/test_amr_import.py — ไฟล์ AMR export จำลองที่
# parse_interval_report อ่านได้จริง (ใช้ทดสอบ resolve_entry ซึ่งเรียก import_amr_from_files จริง)
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


def _add_pending(data_dir, pending_id, account_no, company_name, file_paths=""):
    append_pending_amr_local(
        {
            "pending_id": pending_id,
            "created_at": f"2026-08-{pending_id[-2:]}T00:00:00+00:00",
            "account_no": account_no,
            "company_name": company_name,
            "meter_no": "",
            "file_paths": file_paths or "/tmp/fake.xls",
            "contract_kva": "",
            "has_solar": "false",
            "source_label": "",
        },
        data_dir / "pending_amr_local.csv",
    )


# ── find_deletable_entries (กลุ่มที่ 1 — ลบได้เลย ไม่มีไฟล์ใหม่ให้เสีย) ──


def test_deletable_empty_when_nothing_overlaps(data_dir):
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")
    _add_pending(data_dir, "pend02", "0199000002", "บริษัท บี")

    assert find_deletable_entries(data_dir) == []


def test_deletable_flags_entry_already_known_in_customer_registry(data_dir):
    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000001,บริษัท เอ,TESTBIZ,50,,false,,\n",
        encoding="utf-8",
    )
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")

    deletable = find_deletable_entries(data_dir)
    assert len(deletable) == 1
    entry, reason = deletable[0]
    assert entry["pending_id"] == "pend01"
    assert "TESTBIZ/50" in reason


def test_deletable_flags_later_duplicate_pending_entry_for_same_account(data_dir):
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ (ครั้งแรก)")
    _add_pending(data_dir, "pend02", "0199000001", "บริษัท เอ (ครั้งที่สอง — ซ้ำซ้อน)")

    deletable = find_deletable_entries(data_dir)
    assert len(deletable) == 1
    entry, reason = deletable[0]
    # เก็บรายการแรกสุดไว้ (ไม่แฟล็ก) รายการที่เข้ามาทีหลังถือว่าซ้ำซ้อน
    assert entry["pending_id"] == "pend02"
    assert "pend01" in reason


def test_deletable_does_not_flag_account_with_only_import_log_history(data_dir):
    """บัญชีที่เคยนำเข้าสำเร็จมาก่อน (มีใน import_log_local.csv) แต่ไม่มีในทะเบียนลูกค้า ต้อง
    "ไม่ถูกจัดเป็นลบได้เลย" (จะไปโผล่ในกลุ่ม resolvable แทน) — เพราะไฟล์ใหม่อาจเป็นเดือนใหม่ที่
    ยังไม่เคยนำเข้า ลบทิ้งเฉยๆ จะเสียข้อมูล"""

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

    assert find_deletable_entries(data_dir) == []


def test_entries_without_account_no_are_never_flagged_deletable(data_dir):
    _add_pending(data_dir, "pend01", "", "โฟลเดอร์ที่อ่านเลขบัญชีไม่ได้")
    assert find_deletable_entries(data_dir) == []


def test_deletable_flags_entry_whose_file_content_matches_previous_import(data_dir):
    """อัปโหลด zip/ไฟล์เดิมซ้ำ: เนื้อหาไฟล์ตรงกับที่เคยนำเข้าไปแล้วเป๊ะ (เทียบด้วย file_signature)
    แม้บัญชีจะไม่มีในทะเบียนลูกค้า (มีแค่ import_log history) ก็ลบได้เลยโดยไม่ต้องนำเข้าซ้ำ"""

    amr_file = data_dir / "report.xls"
    amr_file.write_text(_SYNTHETIC_INTERVAL_HTML, encoding="utf-8")
    file_signature = compute_file_signature([str(amr_file)])
    append_import_log_local(
        {
            "imported_at": "2026-07-01T00:00:00+00:00",
            "business_type_code": "TESTBIZ",
            "rate_code": "50",
            "company_name": "บริษัท เอ",
            "account_no": "0199000001",
            "has_solar": "false",
            "file_signature": file_signature,
        },
        data_dir / "import_log_local.csv",
    )
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ", file_paths=str(amr_file))

    deletable = find_deletable_entries(data_dir)
    assert len(deletable) == 1
    entry, reason = deletable[0]
    assert entry["pending_id"] == "pend01"
    assert "เนื้อหาไฟล์ตรงกับที่เคยนำเข้าไปแล้ว" in reason

    # ต้องไม่โผล่ในกลุ่ม resolvable ซ้ำด้วย (find_deletable_entries จัดการไปแล้ว)
    assert find_resolvable_entries(data_dir) == []


def test_resolvable_still_finds_entry_when_file_content_differs_from_history(data_dir):
    """บัญชีเดียวกัน แต่ไฟล์เนื้อหาไม่ตรงกับที่เคยนำเข้า (เช่น เดือนใหม่จริงๆ) ต้องยังอยู่ในกลุ่มที่ 2
    ตามปกติ (ไม่ถูกจัดเป็นลบได้เลยอัตโนมัติ เพราะเนื้อหาไม่ตรงกับที่เทียบได้)"""

    old_file = data_dir / "old_report.xls"
    old_file.write_text(_SYNTHETIC_INTERVAL_HTML, encoding="utf-8")
    append_import_log_local(
        {
            "imported_at": "2026-07-01T00:00:00+00:00",
            "business_type_code": "TESTBIZ",
            "rate_code": "50",
            "company_name": "บริษัท เอ",
            "account_no": "0199000001",
            "has_solar": "false",
            "file_signature": compute_file_signature([str(old_file)]),
        },
        data_dir / "import_log_local.csv",
    )

    new_file = data_dir / "new_report.xls"
    new_file.write_text(_SYNTHETIC_INTERVAL_HTML.replace("20.00", "99.00"), encoding="utf-8")
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ", file_paths=str(new_file))

    assert find_deletable_entries(data_dir) == []
    resolvable = find_resolvable_entries(data_dir)
    assert len(resolvable) == 1
    assert resolvable[0][0]["pending_id"] == "pend01"


# ── find_resolvable_entries (กลุ่มที่ 2 — นำเข้าอัตโนมัติได้ ห้ามลบเฉยๆ) ──


def test_resolvable_finds_account_with_import_log_history(data_dir):
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

    resolvable = find_resolvable_entries(data_dir)
    assert len(resolvable) == 1
    entry, business_type_code, rate_code = resolvable[0]
    assert entry["pending_id"] == "pend01"
    assert business_type_code == "TESTBIZ"
    assert rate_code == "50"


def test_resolvable_uses_latest_import_log_entry_when_account_has_several(data_dir):
    for i, (bt, rate) in enumerate([("OLDBIZ", "40"), ("TESTBIZ", "50")]):
        append_import_log_local(
            {
                "imported_at": f"2026-0{i + 6}-01T00:00:00+00:00",
                "business_type_code": bt,
                "rate_code": rate,
                "company_name": "บริษัท เอ",
                "account_no": "0199000001",
                "has_solar": "false",
            },
            data_dir / "import_log_local.csv",
        )
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")

    resolvable = find_resolvable_entries(data_dir)
    assert resolvable[0][1:] == ("TESTBIZ", "50")


def test_resolvable_empty_when_no_import_log_history(data_dir):
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")
    assert find_resolvable_entries(data_dir) == []


# ── resolve_entry (นำเข้าจริง) ──


def test_resolve_entry_imports_and_removes_from_pending(data_dir):
    amr_file = data_dir / "report.xls"
    amr_file.write_text(_SYNTHETIC_INTERVAL_HTML, encoding="utf-8")
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ", file_paths=str(amr_file))

    entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")
    ok = resolve_entry(entries[0], "TESTBIZ", "50", data_dir, log=lambda m: None)

    assert ok is True
    assert load_pending_amr_local(data_dir / "pending_amr_local.csv") == []

    reference = load_reference_data(data_dir)
    assert any(p.business_type_code == "TESTBIZ" and p.rate_code == "50" for p in reference.load_profiles)


def test_resolve_entry_returns_false_and_keeps_pending_when_files_missing(data_dir):
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ", file_paths="/no/such/file.xls")

    entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")
    ok = resolve_entry(entries[0], "TESTBIZ", "50", data_dir, log=lambda m: None)

    assert ok is False
    # ไม่ถูกลบออกจากคิว เพราะยังนำเข้าไม่สำเร็จ
    assert len(load_pending_amr_local(data_dir / "pending_amr_local.csv")) == 1


# ── find_name_match_candidates (กลุ่มที่ 3 — ชื่อตรงกัน แต่ไม่มีเลขบัญชียืนยัน) ──


def test_name_match_finds_pending_entry_whose_name_matches_existing_customer(data_dir):
    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000001,บริษัท โนเบลเอ็นซี จำกัด,20113,UNKNOWN,,false,,\n",
        encoding="utf-8",
    )
    _add_pending(data_dir, "pend01", "", "บริษัท โนเบลเอ็นซี จำกัด")

    matches = find_name_match_candidates(data_dir)
    assert len(matches) == 1
    entry, customer = matches[0]
    assert entry["pending_id"] == "pend01"
    assert customer.account_no == "0199000001"


def test_name_match_ignores_leading_folder_index_prefix(data_dir):
    """ไฟล์ export บางไฟล์อ่านเลขบัญชีจากหัวรายงานไม่ได้เลย ระบบเลยใช้ชื่อโฟลเดอร์ Google Drive
    ทั้งดุ้นแทน (เช่น "15_บริษัท โนเบลเอ็นซี จำกัด" — "15_" คือเลขลำดับโฟลเดอร์ ไม่ใช่ส่วนหนึ่งของ
    ชื่อบริษัท) ต้องตัด prefix แบบนี้ทิ้งก่อนเทียบชื่อ ไม่งั้นจะพลาดจับคู่กับลูกค้าเดิมในทะเบียน"""

    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "020006578327,บริษัท โนเบลเอ็นซี จำกัด,20113,UNKNOWN,,false,,\n",
        encoding="utf-8",
    )
    _add_pending(data_dir, "pend01", "", "15_บริษัท โนเบลเอ็นซี จำกัด")

    matches = find_name_match_candidates(data_dir)
    assert len(matches) == 1
    entry, customer = matches[0]
    assert entry["pending_id"] == "pend01"
    assert customer.account_no == "020006578327"


def test_name_match_finds_company_known_only_through_import_log_history(data_dir):
    """เจอในการใช้งานจริง: บัญชีที่เคยนำเข้าสำเร็จผ่านโหมด "ดึงจากเว็บ PEA" ไม่เคยผูกกับทะเบียน
    ลูกค้าเลย (มีแค่ import_log_local.csv ไม่มีใน customers_local.csv) — ต้องยังจับคู่ชื่อได้ ไม่ใช่
    แค่เทียบกับทะเบียนลูกค้าอย่างเดียว ไม่งั้นรายการซ้ำแบบนี้จะไม่มีวันถูกจับได้เลย"""

    append_import_log_local(
        {
            "imported_at": "2026-07-01T00:00:00+00:00",
            "business_type_code": "20113",
            "rate_code": "UNKNOWN",
            "company_name": "บริษัท โนเบลเอ็นซี จำกัด",
            "account_no": "020006578327",
            "has_solar": "false",
        },
        data_dir / "import_log_local.csv",
    )
    _add_pending(data_dir, "pend01", "", "15_บริษัท โนเบลเอ็นซี จำกัด")

    matches = find_name_match_candidates(data_dir)
    assert len(matches) == 1
    entry, customer = matches[0]
    assert entry["pending_id"] == "pend01"
    assert customer.account_no == "020006578327"
    assert customer.business_type_code == "20113"


def test_name_match_ignores_case_and_extra_whitespace(data_dir):
    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000001,Some Company Ltd,20113,UNKNOWN,,false,,\n",
        encoding="utf-8",
    )
    _add_pending(data_dir, "pend01", "", "  some   company ltd  ")

    matches = find_name_match_candidates(data_dir)
    assert len(matches) == 1


def test_name_match_skips_entries_that_already_have_an_account_no(data_dir):
    """มีเลขบัญชีอยู่แล้ว ให้กลุ่มที่ 1/2 (แม่นกว่า) จัดการแทน ไม่ต้องมาซ้ำในกลุ่มที่ 3"""
    (data_dir / "customers_local.csv").write_text(
        "account_no,name,business_type_code,rate_code,contract_kva,has_amr,has_solar,business_type_code_raw\n"
        "0199000001,บริษัท เอ,20113,UNKNOWN,,false,,\n",
        encoding="utf-8",
    )
    _add_pending(data_dir, "pend01", "0199000001", "บริษัท เอ")

    assert find_name_match_candidates(data_dir) == []


def test_name_match_empty_when_no_name_overlaps(data_dir):
    _add_pending(data_dir, "pend01", "", "บริษัท ที่ไม่มีใครรู้จัก")
    assert find_name_match_candidates(data_dir) == []


# ── --delete-duplicates (กลุ่มที่ 2 แต่ยืนยันแล้วว่าซ้ำของเดิม ไม่ต้องนำเข้าซ้ำ) ──


def test_delete_duplicates_removes_resolvable_entries_without_reimporting(data_dir, monkeypatch):
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

    monkeypatch.setattr(dedupe_pending_amr, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(sys, "argv", ["dedupe_pending_amr.py", "--delete-duplicates"])
    main()

    # ลบออกจากคิวรอแล้ว แต่ไม่มีการนำเข้าซ้ำ (load_profiles.csv ต้องยังว่างเหมือนเดิม)
    assert load_pending_amr_local(data_dir / "pending_amr_local.csv") == []
    reference = load_reference_data(data_dir)
    assert reference.load_profiles == []


def test_auto_resolve_and_delete_duplicates_together_is_rejected(data_dir, monkeypatch):
    monkeypatch.setattr(dedupe_pending_amr, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(sys, "argv", ["dedupe_pending_amr.py", "--auto-resolve", "--delete-duplicates"])
    with pytest.raises(SystemExit):
        main()
