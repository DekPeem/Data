"""แสดงรายชื่อ บอ (บริษัท/ผู้ใช้ไฟ) ทั้งหมดที่ "ทำไปแล้ว" ในเครื่องนี้ พร้อมเลขบัญชี — เป็น text
ในเทอร์มินัลโดยตรง ไม่ต้องเปิดเว็บไปดูหน้า /overview

รวมข้อมูลจาก 2 แหล่ง (เหมือนหน้า /overview ใช้อยู่):
  1. customers_local.csv — ทะเบียนลูกค้าที่จัดประเภทธุรกิจ+อัตราไว้แล้ว
  2. import_log_local.csv — ประวัติที่เคยนำเข้า AMR สำเร็จมาก่อน แม้จะไม่มีในทะเบียนก็ตาม (เช่น
     นำเข้าผ่านโหมด "ดึงจากเว็บ PEA" ที่กรอกประเภทธุรกิจ/อัตราตรงๆ ไม่เคยผูกกับทะเบียนลูกค้าเลย)

บัญชีเดียวกันถ้ามีทั้ง 2 แหล่ง จะให้ข้อมูลจากทะเบียนลูกค้า (customers_local.csv) ชนะ เพราะเป็นข้อมูล
ล่าสุด/แก้ไขเองได้ในหน้า /overview ตรงๆ

ใช้:
    python scripts/list_known_companies.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import DEFAULT_DATA_DIR, load_import_log_local, load_reference_data


def collect_known_companies(data_dir: Path) -> Dict[str, dict]:
    """คืน dict {account_no: {"name", "business_type_code", "rate_code"}} รวมจาก customers_local.csv
    + import_log_local.csv (ดู docstring ของโมดูล) — เลขบัญชีที่ไม่มีเลยถูกข้ามไป (เทียบซ้ำไม่ได้)"""

    reference = load_reference_data(data_dir)
    rows: Dict[str, dict] = {}

    for e in load_import_log_local(data_dir / "import_log_local.csv"):
        account_no = (e.get("account_no") or "").strip()
        if not account_no:
            continue
        rows[account_no] = {
            "name": (e.get("company_name") or "").strip(),
            "business_type_code": (e.get("business_type_code") or "").strip(),
            "rate_code": (e.get("rate_code") or "").strip(),
        }

    # ทะเบียนลูกค้าชนะประวัติเสมอ (เขียนทับทีหลัง) เพราะแก้ไขเองได้ตรงๆ ในหน้า /overview
    for c in reference.customers:
        if not c.account_no:
            continue
        rows[c.account_no] = {
            "name": c.name or rows.get(c.account_no, {}).get("name", ""),
            "business_type_code": c.business_type_code or "",
            "rate_code": c.rate_code or "",
        }

    return rows


def main() -> None:
    rows = collect_known_companies(DEFAULT_DATA_DIR)

    if not rows:
        print("ยังไม่มีบัญชีไหนที่ทำไปแล้วเลยครับ")
        return

    print(f"รวม {len(rows)} บัญชีที่ทำไปแล้ว:\n")
    for account_no, info in sorted(rows.items(), key=lambda kv: (kv[1]["name"] or "", kv[0])):
        name = info["name"] or "(ไม่ทราบชื่อ)"
        bt = info["business_type_code"] or "?"
        rate = info["rate_code"] or "?"
        print(f"  {name} — บัญชี {account_no} — ประเภทธุรกิจ {bt} / อัตรา {rate}")


if __name__ == "__main__":
    main()
