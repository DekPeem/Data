import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import load_tsic_code_mapping
from amr_mapping.tsic_normalize import normalize_tsic_code, normalize_tsic_code_with_audit

_MAPPING = {"93311": "86101", "70102": "68104", "38439": "29301"}


def test_normalize_converts_known_old_code():
    assert normalize_tsic_code("93311", _MAPPING) == "86101"


def test_normalize_fallback_returns_unknown_code_unchanged():
    """รหัสที่ไม่อยู่ใน mapping (เป็นรหัสใหม่อยู่แล้ว หรือยังไม่รู้จัก) ต้องใช้ค่าเดิมได้เลย ไม่ error"""

    assert normalize_tsic_code("86101", _MAPPING) == "86101"
    assert normalize_tsic_code("99999", _MAPPING) == "99999"


def test_normalize_strips_whitespace():
    assert normalize_tsic_code("  93311  ", _MAPPING) == "86101"


def test_normalize_none_and_empty_pass_through():
    assert normalize_tsic_code(None, _MAPPING) is None
    assert normalize_tsic_code("", _MAPPING) == ""


def test_normalize_with_audit_returns_new_code_and_raw_code():
    normalized, raw = normalize_tsic_code_with_audit("93311", _MAPPING)
    assert normalized == "86101"
    assert raw == "93311"


def test_normalize_with_audit_still_returns_raw_when_code_already_canonical():
    """แม้รหัสที่รับเข้ามาเป็นรหัสใหม่อยู่แล้ว (ไม่ถูกแปลง) ก็ต้องยังคืนค่า raw กลับมา (audit
    trail ต้องสอดคล้องกันเสมอ ไม่ใช่แค่ตอนมีการแปลงจริงเท่านั้น)"""

    normalized, raw = normalize_tsic_code_with_audit("86101", _MAPPING)
    assert normalized == "86101"
    assert raw == "86101"


def test_normalize_with_audit_raw_is_none_when_input_empty():
    normalized, raw = normalize_tsic_code_with_audit(None, _MAPPING)
    assert normalized is None
    assert raw is None

    normalized, raw = normalize_tsic_code_with_audit("", _MAPPING)
    assert normalized == ""
    assert raw is None


def test_load_tsic_code_mapping_reads_real_committed_table():
    """ตรวจว่า Core Mapping Dictionary ที่ commit เข้า repo จริง (data/reference/
    tsic_code_mapping.csv) มีคู่รหัสที่ต้องมีครบตามที่กำหนด"""

    mapping = load_tsic_code_mapping()
    assert mapping["93311"] == "86101"
    assert mapping["70102"] == "68104"
    assert mapping["38439"] == "29301"


def test_load_tsic_code_mapping_returns_empty_dict_when_file_missing(tmp_path):
    mapping = load_tsic_code_mapping(tmp_path / "does_not_exist.csv")
    assert mapping == {}


def test_load_tsic_code_mapping_extensible_via_csv_rows(tmp_path):
    """เพิ่มคู่รหัสใหม่ได้แค่เพิ่มแถวในไฟล์ CSV ไม่ต้องแก้โค้ด"""

    path = tmp_path / "tsic_code_mapping.csv"
    path.write_text("old_code,new_code,notes\nAAAA,BBBB,ทดสอบ\n", encoding="utf-8")
    mapping = load_tsic_code_mapping(path)
    assert mapping == {"AAAA": "BBBB"}
