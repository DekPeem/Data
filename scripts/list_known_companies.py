"""แสดงรายชื่อ บอ (บริษัท/ผู้ใช้ไฟ) ทั้งหมดในทะเบียนของเครื่องนี้ พร้อมเลขบัญชี — เป็น text
ในเทอร์มินัลโดยตรง ไม่ต้องเปิดเว็บไปดูหน้า /overview

อ่านจาก customers.csv (ตัวอย่าง/สาธิต) + customers_local.csv (ถ้ามี — ข้อมูลจริงในเครื่อง ชนะ
customers.csv ถ้าเลขบัญชีซ้ำกัน) เหมือนที่หน้า /overview ใช้อยู่

ใช้:
    python scripts/list_known_companies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import DEFAULT_DATA_DIR, load_reference_data


def main() -> None:
    reference = load_reference_data(DEFAULT_DATA_DIR)
    customers = [c for c in reference.customers if c.account_no]

    if not customers:
        print("ยังไม่มีบัญชีไหนในทะเบียนเลยครับ")
        return

    print(f"รวม {len(customers)} บัญชีในทะเบียน:\n")
    for c in sorted(customers, key=lambda c: (c.name or "", c.account_no)):
        name = c.name or "(ไม่ทราบชื่อ)"
        bt = c.business_type_code or "?"
        print(f"  {name} — บัญชี {c.account_no} — ประเภทธุรกิจ {bt}")


if __name__ == "__main__":
    main()
