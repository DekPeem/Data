"""โครงสร้างข้อมูล (data models) ของโมดูล amr_mapping"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BusinessType:
    """ประเภทธุรกิจของผู้ใช้ไฟ (เช่น TSIC code)

    section_code/division_code (ถ้าทราบ) คือตำแหน่งใน "หมวดหมู่ธุรกิจ" ตามมาตรฐาน TSIC
    ของไทย (อิงตาม ISIC) แบบลำดับชั้น:
        Section  (หมวดใหญ่ เช่น "C" = การผลิต)      — 1 ตัวอักษร A-U
        Division (หมวดย่อย เช่น "17" = การผลิตกระดาษ) — 2 หลัก
    ใช้เป็นชั้นสำรองในการจับคู่ (ดู web/app.py:_suggest_business_type_for_division) เมื่อไม่มี
    business_type_code นี้ตรงๆ ในระบบ แต่มี business_type อื่นใน division/section เดียวกัน —
    ปล่อยว่าง (None) ได้ถ้ายังไม่ได้ตรวจสอบว่า code นี้ตรงกับ TSIC จริงแค่ไหน

    alias_of (ถ้าทราบ) คือรหัส TSIC อีกรหัสหนึ่งที่ "เรื่องเดียวกัน" กับ code นี้เป๊ะๆ ในแง่ความ
    หมายทางธุรกิจ แค่คนละเวอร์ชันมาตรฐาน/คนละยุคที่ประกาศใช้ (เช่น 86101 ปัจจุบัน vs 93311
    รหัสเก่าของ "โรงพยาบาลทั่วไป") — ต่างจาก division_code ตรงที่ division เป็นแค่ "กลุ่ม
    อุตสาหกรรมใกล้เคียงกัน" ส่วน alias_of คือ "เหมือนกันทุกประการ" """

    code: str
    name_th: str
    category: str
    notes: str = ""
    section_code: Optional[str] = None
    section_name_th: str = ""
    division_code: Optional[str] = None
    division_name_th: str = ""
    alias_of: Optional[str] = None


@dataclass(frozen=True)
class Customer:
    """ผู้ใช้ไฟที่ต้องการจับคู่ประเภทธุรกิจ (TSIC)."""

    account_no: str
    name: str
    business_type_code: Optional[str] = None
    has_amr: bool = False
    # รหัส TSIC ดิบที่รับเข้ามาจริง ก่อนแปลงเป็นรหัสมาตรฐานใหม่ (business_type_code ด้านบนคือ
    # รหัสที่แปลงแล้ว ใช้ประมวลผล matching จริง) — เก็บไว้เป็น audit trail เฉยๆ ไม่มีผลต่อการจับคู่
    # ใดๆ ทั้งสิ้น ดู tsic_normalize.normalize_tsic_code_with_audit — None ถ้าไม่เคยผ่านการแปลง
    # (เช่น ลูกค้าเก่าที่มีมาก่อนฟีเจอร์นี้) หรือรหัสที่กรอกมาว่างเปล่าตั้งแต่แรก
    business_type_code_raw: Optional[str] = None
    # เลขทะเบียนนิติบุคคล 13 หลักของกรมพัฒนาธุรกิจการค้า (DBD) — ไม่บังคับกรอก กรอกเองได้จากหน้า
    # /overview ใช้แทนชื่อบริษัทตอนค้นหา TSIC ที่ DBD DataWarehouse ได้ (แม่นยำกว่าค้นด้วยชื่อ
    # เพราะชื่อที่สแกนมาจากหน้า PEA อาจสะกด/มีคำนำหน้า-ต่อท้ายไม่ตรงกับที่จดทะเบียนไว้เป๊ะ)
    registration_no: Optional[str] = None
