"""TSIC Code Normalization — แปลงรหัสประเภทธุรกิจ (TSIC) จากระบบเดิมของ PEA/AMR (TSIC 2544)
ให้เป็นรหัสมาตรฐานใหม่ (TSIC 2552 / กรมพัฒนาธุรกิจการค้า) ทันทีตอนข้อมูลเข้าสู่ระบบ ไม่ว่าจะมา
จากการสแกน AMR อัตโนมัติหรือผู้ใช้กรอกเอง (ดู amr_import.py และ web/app.py ที่เรียกใช้)

หลักการ 3 ข้อ:
    1. Normalize — รหัสเก่าที่อยู่ใน mapping table ถูกแปลงเป็นรหัสใหม่ทันที ก่อนนำไปใช้จับคู่/บันทึก
       ลง business_type_code (ฟิลด์หลักที่ใช้ประมวลผล matching จริงทั้งระบบ)
    2. Audit trail — รหัสดิบที่รับเข้ามาต้องถูกเก็บไว้แยกต่างหาก (Customer.business_type_code_raw,
       import_log_local.csv คอลัมน์ business_type_code_raw) ไม่ทิ้งไปเฉยๆ เผื่อต้องตรวจสอบย้อนหลัง
       ว่าระบบต้นทาง (PEA/ผู้ใช้) ส่งรหัสอะไรมาจริงๆ
    3. Fallback — รหัสที่ไม่อยู่ใน mapping table (เป็นรหัสใหม่อยู่แล้ว หรือยังไม่รู้จัก/ยังไม่เคย
       ตรวจสอบ) ใช้ค่าเดิมได้เลยตรงๆ ไม่ error ไม่บล็อกการทำงาน

Mapping table โหลดจาก data/reference/tsic_code_mapping.csv ผ่าน loader.load_tsic_code_mapping()
— เพิ่มคู่รหัสใหม่ได้แค่เพิ่มแถวในไฟล์ CSV นั้น ไม่ต้องแก้โค้ดไฟล์นี้เลย ฟังก์ชันในโมดูลนี้รับ
mapping เป็นพารามิเตอร์ตรงๆ (ไม่โหลดเองภายใน) ตามรูปแบบเดียวกับ mapping.find_load_profile ที่รับ
business_types เป็นพารามิเตอร์ — ทำให้เทสต์ง่าย และเรียกจากจุดที่มี data_dir ไม่เหมือนกันได้ (เช่น
เทสต์ที่ใช้ tmp_path แยกจาก data/reference/ จริง)"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


def normalize_tsic_code(code: Optional[str], mapping: Dict[str, str]) -> Optional[str]:
    """แปลงรหัส TSIC 1 ตัวให้เป็นรหัสมาตรฐานใหม่

    - code เป็น None/ว่างเปล่า -> คืนค่าเดิมกลับไปเฉยๆ (ไม่มีอะไรให้แปลง)
    - code อยู่ใน mapping (รหัสเก่า) -> คืนรหัสใหม่ที่แมปไว้
    - code ไม่อยู่ใน mapping (เป็นรหัสใหม่อยู่แล้ว หรือยังไม่รู้จัก) -> คืนค่าเดิม (ตัดช่องว่าง
      หัว-ท้ายออกให้) กลับไปตรงๆ ไม่ error (Fallback Logic)
    """

    if not code:
        return code
    code = code.strip()
    if not code:
        return code
    return mapping.get(code, code)


def normalize_tsic_code_with_audit(
    code: Optional[str], mapping: Dict[str, str]
) -> Tuple[Optional[str], Optional[str]]:
    """เหมือน normalize_tsic_code แต่คืน (รหัสใหม่ที่ใช้ประมวลผลจริง, รหัสดิบที่รับเข้ามา) คู่กัน
    — ใช้ตอนต้อง "เก็บ audit trail" ด้วย เช่น Customer.business_type_code_raw หรือ
    import_log_local.csv คอลัมน์ business_type_code_raw

    รหัสดิบที่คืนมาเป็น None ถ้า code ที่รับเข้ามาว่างเปล่าตั้งแต่แรก (ไม่มีอะไรให้เก็บเป็น audit)
    — คืนรหัสดิบเสมอไม่ว่าจะถูกแปลงจริงหรือไม่ (แม้รหัสใหม่อยู่แล้วก็ยังบันทึกไว้ เพื่อให้ audit
    trail สอดคล้องกันทุกกรณี ไม่ใช่แค่ตอนที่มีการแปลงเกิดขึ้นจริงเท่านั้น)"""

    raw = (code or "").strip() or None
    normalized = normalize_tsic_code(code, mapping)
    return normalized, raw
