"""แก้ TSIC ในทะเบียนลูกค้า (หน้า /overview) ให้ตรงกับ TSIC ที่ผูกไว้ตอนอัปโหลด AMR จริง (หน้า
Admin) สำหรับบัญชีที่ scripts/check_amr_tsic_consistency.py รายงานว่า TSIC ไม่ตรงกัน — ยึด AMR log
เป็นค่าที่ถูกต้อง (ตามที่ผู้ใช้ยืนยันไว้ เหมือนกับ scripts/add_missing_amr_customers_to_registry.py)
เขียนลง customers_local.csv เท่านั้น (local-only ไม่กระทบ customers.csv ที่ commit เข้า git)

รันแบบดูก่อนไม่เขียนจริง (dry-run — ค่าเริ่มต้น):
    python scripts/fix_amr_tsic_mismatches.py

รันแบบเขียนจริงลง customers_local.csv:
    python scripts/fix_amr_tsic_mismatches.py --apply
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
    customer_by_account = {c.account_no: c for c in reference.customers if c.account_no}
    business_type_name = {bt.code: bt.name_th for bt in reference.business_types.values()}

    storage_path = DEFAULT_DATA_DIR / "amr_boxplot_intervals_local.csv"
    amr_rows = [r for r in summarize_available_by_account(storage_path) if r["account_no"]]

    mismatches = []
    for r in amr_rows:
        customer = customer_by_account.get(r["account_no"])
        if customer is None:
            continue
        if (customer.business_type_code or "") != r["business_type_code"]:
            mismatches.append((r, customer))

    if not mismatches:
        print("ไม่มีบัญชีไหน TSIC ไม่ตรงกันเลยครับ (เทียบกับบัญชีที่อยู่ในทะเบียนลูกค้าแล้ว) ไม่ต้องแก้อะไร")
        return

    def label(code: str) -> str:
        name = business_type_name.get(code, "")
        return f"{name} · {code}" if name else f"(ไม่พบชื่อในระบบ) · {code}"

    verb = "แก้" if args.apply else "จะแก้ (dry-run — ใส่ --apply เพื่อเขียนจริง)"
    print(f"{verb} {len(mismatches)} บัญชีในทะเบียนลูกค้า (customers_local.csv) ให้ TSIC ตรงกับ AMR log:\n")

    customers_local_path = DEFAULT_DATA_DIR / "customers_local.csv"
    for r, customer in sorted(mismatches, key=lambda m: (m[1].name or "", m[0]["account_no"])):
        name = r["company_name"] or customer.name or "(ไม่ทราบชื่อ)"
        print(f"  {name} — บัญชี {r['account_no']}")
        print(f"    เดิม (ทะเบียนลูกค้า): {label(customer.business_type_code or '')}")
        print(f"    ใหม่ (จาก AMR log):  {label(r['business_type_code'])}")
        print()
        if args.apply:
            upsert_customer_local(
                customers_local_path,
                Customer(
                    account_no=customer.account_no,
                    name=customer.name or r["company_name"],
                    business_type_code=r["business_type_code"],
                    has_amr=True,
                    registration_no=customer.registration_no or (r["registration_no"] or None),
                ),
            )

    if args.apply:
        print(f"✅ แก้แล้ว {len(mismatches)} บัญชี — ไปดูที่หน้า /overview ได้เลย")
    else:
        print("(นี่คือ dry-run ยังไม่ได้เขียนอะไรลงไฟล์ — รันซ้ำพร้อม --apply เพื่อเขียนจริง)")


if __name__ == "__main__":
    main()
