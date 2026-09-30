"""เพิ่มลูกค้าที่มีข้อมูล AMR จริงอัปโหลดไว้แล้ว (หน้า Admin) แต่ยังไม่มีในทะเบียนลูกค้า (หน้า
/overview) เข้าไปในทะเบียนให้อัตโนมัติ — ยึด TSIC ที่ผูกไว้ตอนอัปโหลด AMR เป็นค่าที่ถูกต้อง (ตามที่
ผู้ใช้ยืนยันว่าให้ใช้ข้อมูลฝั่ง AMR log เป็นหลัก) ใช้ชื่อบริษัท/เลขบัญชี/เลขทะเบียนนิติบุคคลจาก AMR
log ตรงๆ เขียนลง customers_local.csv (local-only อยู่แล้ว ไม่กระทบ customers.csv ที่ commit เข้า
git — ดู scripts/check_amr_tsic_consistency.py ที่หาบัญชีกลุ่มนี้ให้ก่อนแล้ว)

รันแบบดูก่อนไม่เขียนจริง (dry-run — ค่าเริ่มต้น):
    python scripts/add_missing_amr_customers_to_registry.py

รันแบบเขียนจริงลง customers_local.csv:
    python scripts/add_missing_amr_customers_to_registry.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.amr_boxplot import summarize_available_by_account
from amr_mapping.loader import DEFAULT_DATA_DIR, load_reference_data, upsert_customer_local
from amr_mapping.models import Customer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="เขียนจริงลง customers_local.csv (ไม่ใส่ = dry-run แสดงรายการอย่างเดียว)")
    args = parser.parse_args()

    reference = load_reference_data(DEFAULT_DATA_DIR)
    known_accounts = {c.account_no for c in reference.customers if c.account_no}

    storage_path = DEFAULT_DATA_DIR / "amr_boxplot_intervals_local.csv"
    amr_rows = [r for r in summarize_available_by_account(storage_path) if r["account_no"]]
    missing = [r for r in amr_rows if r["account_no"] not in known_accounts]

    if not missing:
        print("ทุกบัญชีที่มีข้อมูล AMR จริงอยู่ในทะเบียนลูกค้าแล้วครับ ไม่ต้องเพิ่มอะไร")
        return

    verb = "เพิ่ม" if args.apply else "จะเพิ่ม (dry-run — ใส่ --apply เพื่อเขียนจริง)"
    print(f"{verb} {len(missing)} บัญชีเข้าทะเบียนลูกค้า (customers_local.csv):\n")

    customers_local_path = DEFAULT_DATA_DIR / "customers_local.csv"
    for r in sorted(missing, key=lambda r: (r["company_name"] or "", r["account_no"])):
        name = r["company_name"] or f"(ไม่ทราบชื่อ — บัญชี {r['account_no']})"
        print(f"  {name} — บัญชี {r['account_no']} — TSIC {r['business_type_code']}")
        if args.apply:
            upsert_customer_local(
                customers_local_path,
                Customer(
                    account_no=r["account_no"],
                    name=name,
                    business_type_code=r["business_type_code"],
                    has_amr=True,
                    registration_no=r["registration_no"] or None,
                ),
            )

    if args.apply:
        print(f"\n✅ เพิ่มแล้ว {len(missing)} บัญชี — ไปดูที่หน้า /overview ได้เลย")
    else:
        print("\n(นี่คือ dry-run ยังไม่ได้เขียนอะไรลงไฟล์ — รันซ้ำพร้อม --apply เพื่อเขียนจริง)")


if __name__ == "__main__":
    main()
