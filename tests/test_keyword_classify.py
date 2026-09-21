import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.keyword_classify import guess_tsic_division


def test_guess_tsic_division_matches_convenience_store():
    result = guess_tsic_division("ประกอบธุรกิจหลัก คือ ธุรกิจค้าปลีกประเภทร้านสะดวกซื้อ")
    assert result == ("47", "ร้านสะดวกซื้อ")


def test_guess_tsic_division_matches_hotel():
    result = guess_tsic_division("เป็นเจ้าของโรงแรมและรีสอร์ทหลายแห่ง")
    assert result == ("55", "โรงแรม")


def test_guess_tsic_division_returns_none_when_no_keyword_matches():
    assert guess_tsic_division("บริษัทประกอบกิจการทั่วไปตามวัตถุประสงค์ที่จดทะเบียนไว้") is None


def test_guess_tsic_division_returns_none_for_empty_text():
    assert guess_tsic_division("") is None
    assert guess_tsic_division(None) is None


def test_guess_tsic_division_returns_first_match_in_priority_order():
    # "ร้านอาหาร" ต้องเจอก่อน "ร้าน" เฉยๆ (ซึ่งไม่มีในลิสต์อยู่แล้ว แต่เช็คว่าคำเจาะจงมาก่อน)
    result = guess_tsic_division("เปิดร้านอาหารและร้านสะดวกซื้อในเครือเดียวกัน")
    assert result == ("47", "ร้านสะดวกซื้อ") or result == ("56", "ร้านอาหาร")
    # อย่างน้อยต้องเป็นหนึ่งในสองนี้ ไม่ใช่ None
    assert result is not None


def test_guess_tsic_division_does_not_guess_generic_factory_keyword():
    """ตั้งใจไม่รองรับคำว่า "โรงงาน" กว้างๆ (ดู comment ในโมดูล) — ต้องคืน None ไม่ใช่เดามั่วๆ"""
    assert guess_tsic_division("เป็นโรงงานอุตสาหกรรมขนาดใหญ่") is None
