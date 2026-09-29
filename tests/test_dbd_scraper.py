import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from amr_mapping.dbd_lookup import BlockedByAntiBot
from amr_mapping.dbd_scraper.tsic_lookup import (
    _build_candidates,
    _extract_tsic_after_header,
    _extract_tsic_from_juristic_dict,
)


# ── _extract_tsic_after_header (regex บนข้อความทั้งหน้า — fallback เมื่อ juristic dict ไม่มี TSIC) ──


def test_extract_tsic_after_header_finds_code_and_name():
    text = (
        "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด\nประเภทธุรกิจ\n"
        "32909 การผลิตผลิตภัณฑ์อื่นๆซึ่งไม่ได้จัดประเภทไว้ในที่อื่น\nวัตถุประสงค์\nผลิตและจำหน่ายเครื่องกรองน้ำ"
    )
    result = _extract_tsic_after_header(text, "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด")
    assert result == ("32909", "การผลิตผลิตภัณฑ์อื่นๆซึ่งไม่ได้จัดประเภทไว้ในที่อื่น")


def test_extract_tsic_after_header_respects_next_header_boundary():
    """ต้องอ่านแค่ในโซนของ header แรก ไม่เผลอข้ามไปอ่านรหัสของ header ถัดไป"""

    text = (
        "ประเภทธุรกิจตอนจดทะเบียน\nประเภทธุรกิจ\n28250 การผลิตเครื่องจักร\n"
        "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด\nประเภทธุรกิจ\n32909 การผลิตผลิตภัณฑ์อื่นๆ"
    )
    result = _extract_tsic_after_header(
        text, "ประเภทธุรกิจตอนจดทะเบียน", next_header="ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด"
    )
    assert result == ("28250", "การผลิตเครื่องจักร")


def test_extract_tsic_after_header_returns_none_when_header_missing():
    assert _extract_tsic_after_header("ไม่มีหัวข้อนี้เลย", "ประเภทธุรกิจตอนจดทะเบียน") is None


# ── _extract_tsic_from_juristic_dict (ทาง "ตรง" ก่อน — เผื่อการ์ดใช้โครงสร้าง .prompt เดียวกัน) ──


def test_extract_tsic_from_juristic_dict_finds_matching_keys():
    data = {
        "ชื่อนิติบุคคล": "บริษัท ทดสอบ จำกัด",
        "ประเภทธุรกิจตอนจดทะเบียน": "28250 การผลิตเครื่องจักร",
        "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด": "32909 การผลิตผลิตภัณฑ์อื่นๆ",
    }
    found = _extract_tsic_from_juristic_dict(data)
    codes = {code for code, _name, _key in found}
    assert codes == {"28250", "32909"}


def test_extract_tsic_from_juristic_dict_ignores_non_tsic_keys():
    data = {"ชื่อนิติบุคคล": "บริษัท ทดสอบ จำกัด", "ทุนจดทะเบียน": "160,000,000.00 บาท"}
    assert _extract_tsic_from_juristic_dict(data) == []


def test_extract_tsic_from_juristic_dict_ignores_key_without_leading_code():
    data = {"ประเภทธุรกิจ": "ไม่มีรหัสนำหน้าเลย"}
    assert _extract_tsic_from_juristic_dict(data) == []


# ── _build_candidates (รวมทั้ง 2 ทาง + dedupe + ลำดับ "ปีล่าสุด" ขึ้นก่อน) ──

_SAMPLE_BODY_TEXT = """ชื่อนิติบุคคล : บริษัท สยามคาสท์ไนล่อน จำกัด
เลขทะเบียนนิติบุคคล : 0145537000805
ประเภทธุรกิจตอนจดทะเบียน
ประเภทธุรกิจ
28250 การผลิตเครื่องจักรที่ใช้ในกระบวนการผลิตอาหาร เครื่องดื่ม และ ยาสูบ
วัตถุประสงค์
การผลิตและจำหน่ายเครื่องกรองน้ำทุกชนิด
ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด
ประเภทธุรกิจ
32909 การผลิตผลิตภัณฑ์อื่นๆซึ่งไม่ได้จัดประเภทไว้ในที่อื่น
วัตถุประสงค์
ผลิตและจำหน่ายเครื่องกรองน้ำ ไส้กรองน้ำ
"""

_SAMPLE_JURISTIC = {
    "ชื่อนิติบุคคล": "บริษัท สยามคาสท์ไนล่อน จำกัด",
    "ประเภทนิติบุคคล": "บริษัทจำกัด",
    "สถานะนิติบุคคล": "ยังดำเนินกิจการอยู่",
}


def test_build_candidates_uses_only_latest_financial_statement_from_body_text():
    """ต้องอ่านแค่การ์ด "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด" เท่านั้น — ไม่คืน "ตอนจดทะเบียน" มา
    เป็นตัวเลือกเลยแม้จะเจอทั้งคู่ในหน้าเดียวกัน (ยืนยันชัดเจนจากผู้ใช้ว่าอยากได้แค่ตัวนี้ หลังเจอ
    เคสจริงที่ "ตอนจดทะเบียน" หลุดมาเป็นตัวที่ระบบใช้อยู่ดีทั้งที่เคย sort ให้ "ปีล่าสุด" ขึ้นก่อนแล้ว)"""

    logs = []
    candidates = _build_candidates("0145537000805", _SAMPLE_JURISTIC, _SAMPLE_BODY_TEXT, logs.append)

    assert len(candidates) == 1
    assert candidates[0].tsic_code == "32909"
    assert "ปีล่าสุด" in candidates[0].tsic_name_th
    assert "ตอนจดทะเบียน" not in candidates[0].tsic_name_th
    c = candidates[0]
    assert c.registration_no == "0145537000805"
    assert c.juristic_name == "บริษัท สยามคาสท์ไนล่อน จำกัด"
    assert c.juristic_type == "บริษัทจำกัด"
    assert c.status == "ยังดำเนินกิจการอยู่"
    assert any("พบ TSIC" in m for m in logs) or any("TSIC" in m for m in logs)


def test_build_candidates_prefers_juristic_dict_when_it_has_tsic():
    juristic = dict(_SAMPLE_JURISTIC)
    juristic["ประเภทธุรกิจ"] = "99999 รหัสจากการ์ดโดยตรง"
    candidates = _build_candidates("0145537000805", juristic, "ข้อความหน้าอื่นที่ไม่เกี่ยวกัน", lambda m: None)

    assert len(candidates) == 1
    assert candidates[0].tsic_code == "99999"


def test_build_candidates_uses_only_latest_financial_statement_via_dict_path():
    """เหมือน test_build_candidates_uses_only_latest_financial_statement_from_body_text แต่ผ่านทาง
    juristic dict โดยตรง ไม่ใช่ fallback ไปอ่าน body text — ยืนยันเคสจริงที่บริษัทมี TSIC ตอนจดทะเบียน/
    ปีล่าสุดต่างกัน (เช่น เปลี่ยนสายธุรกิจไปแล้ว) scraper.py's _JURISTIC_JS ใช้หัวข้อการ์ดเป็น key
    แยกกันสำหรับ 2 การ์ดนี้โดยเฉพาะ (label "ประเภทธุรกิจ" ซ้ำกันทั้งคู่) แต่ _build_candidates ต้อง
    เลือกอ่านเฉพาะการ์ด "ปีล่าสุด" เท่านั้น ไม่ใช่คืนทั้งคู่มาให้เลือก"""

    juristic = dict(_SAMPLE_JURISTIC)
    juristic["ประเภทธุรกิจตอนจดทะเบียน"] = "28250 การผลิตเครื่องจักร"
    juristic["ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด"] = "32909 การผลิตผลิตภัณฑ์อื่นๆ"

    candidates = _build_candidates("0145537000805", juristic, "ข้อความหน้าอื่นที่ไม่เกี่ยวกัน", lambda m: None)

    assert len(candidates) == 1
    assert candidates[0].tsic_code == "32909"
    assert "ปีล่าสุด" in candidates[0].tsic_name_th


def test_build_candidates_falls_back_to_registration_when_no_latest_statement_found():
    """บริษัทตั้งใหม่ที่ยังไม่เคยส่งงบการเงินเลย ไม่มีการ์ด "ปีล่าสุด" ให้อ่าน — ต้อง fallback ไปใช้
    "ตอนจดทะเบียน" แทน (ดีกว่าไม่มีข้อมูลเลย) พร้อมบอกในชื่อ/log ว่าเป็นข้อมูลตอนจดทะเบียน ไม่ใช่
    ปีล่าสุด"""

    juristic = dict(_SAMPLE_JURISTIC)
    juristic["ประเภทธุรกิจตอนจดทะเบียน"] = "28250 การผลิตเครื่องจักร"

    logs = []
    candidates = _build_candidates("0145537000805", juristic, "ข้อความหน้าอื่นที่ไม่เกี่ยวกัน", logs.append)

    assert len(candidates) == 1
    assert candidates[0].tsic_code == "28250"
    assert "ตอนจดทะเบียน" in candidates[0].tsic_name_th
    assert any("ยังไม่พบข้อมูลงบการเงิน" in m or "ตอนจดทะเบียน" in m for m in logs)


def test_build_candidates_returns_empty_list_and_logs_when_no_tsic_found_anywhere():
    logs = []
    candidates = _build_candidates("0145537000805", _SAMPLE_JURISTIC, "ไม่มีข้อมูล TSIC เลยในหน้านี้", logs.append)
    assert candidates == []
    assert any("อ่านรหัส TSIC ไม่สำเร็จ" in m for m in logs)
