"""เช็คว่าเลขบัญชีที่มีข้อมูล AMR จริงอัปโหลดไว้แล้ว (หน้า Admin) กับประเภทธุรกิจ (TSIC) ที่ผูกไว้ใน
ทะเบียนลูกค้า (หน้า /overview) ตรงกันไหม — สองหน้านี้เป็นคนละแหล่งข้อมูลกัน (ทะเบียนลูกค้ามาจาก
customers.csv/customers_local.csv ส่วน AMR log มาจาก amr_boxplot_intervals_local.csv ที่กรอก/
ตรวจจับ TSIC ตอนอัปโหลดแยกกันเอง) จึงเพี้ยนกันได้ถ้าพิมพ์ผิด/เลือก TSIC ผิดตอนอัปโหลด หรือทะเบียน
ลูกค้ายังไม่อัปเดต

รายงาน 2 กรณี:
  1. เลขบัญชีมีข้อมูล AMR แล้ว แต่ TSIC ที่ผูกไว้ตอนอัปโหลดไม่ตรงกับ TSIC ในทะเบียนลูกค้า
  2. เลขบัญชีมีข้อมูล AMR แล้ว แต่ไม่มีอยู่ในทะเบียนลูกค้าเลย (หา TSIC ไม่ได้ว่าควรเป็นอันไหนกันแน่)

ใช้:
    python scripts/check_amr_tsic_consistency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.amr_boxplot import summarize_available_by_account
from amr_mapping.loader import DEFAULT_DATA_DIR, load_reference_data


def main() -> None:
    reference = load_reference_data(DEFAULT_DATA_DIR)
    customer_by_account = {c.account_no: c for c in reference.customers if c.account_no}
    business_type_name = {bt.code: bt.name_th for bt in reference.business_types.values()}

    storage_path = DEFAULT_DATA_DIR / "amr_boxplot_intervals_local.csv"
    amr_rows = [r for r in summarize_available_by_account(storage_path) if r["account_no"]]

    if not amr_rows:
        print("ยังไม่มีข้อมูล AMR จริงที่ระบุเลขบัญชีไว้เลยครับ")
        return

    mismatches = []
    not_in_registry = []

    for r in sorted(amr_rows, key=lambda r: (r["company_name"] or "", r["account_no"])):
        account_no = r["account_no"]
        amr_code = r["business_type_code"]
        customer = customer_by_account.get(account_no)

        if customer is None:
            not_in_registry.append(r)
            continue

        if (customer.business_type_code or "") != amr_code:
            mismatches.append((r, customer))

    def label(code: str) -> str:
        name = business_type_name.get(code, "")
        return f"{name} · {code}" if name else f"(ไม่พบชื่อในระบบ) · {code}"

    print(f"ตรวจ {len(amr_rows)} บัญชีที่มีข้อมูล AMR จริง (ระบุเลขบัญชีไว้) จากทั้งหมด\n")

    if mismatches:
        print(f"⚠️  TSIC ไม่ตรงกัน {len(mismatches)} บัญชี (AMR log vs ทะเบียนลูกค้า /overview):\n")
        for r, customer in mismatches:
            name = r["company_name"] or customer.name or "(ไม่ทราบชื่อ)"
            print(f"  {name} — บัญชี {r['account_no']}")
            print(f"    AMR log ผูกไว้กับ:      {label(r['business_type_code'])}")
            print(f"    ทะเบียนลูกค้าผูกไว้กับ:  {label(customer.business_type_code or '')}")
            print()
    else:
        print("✅ ไม่มีบัญชีไหน TSIC ไม่ตรงกันเลย (เทียบกับบัญชีที่อยู่ในทะเบียนลูกค้าแล้ว)\n")

    if not_in_registry:
        print(f"⚠️  มีข้อมูล AMR แล้วแต่ไม่มีในทะเบียนลูกค้าเลย {len(not_in_registry)} บัญชี (เพิ่มลูกค้านี้ในหน้า /overview ก่อน ถึงจะเช็คได้ว่า TSIC ตรงไหม):\n")
        for r in not_in_registry:
            name = r["company_name"] or "(ไม่ทราบชื่อ)"
            print(f"  {name} — บัญชี {r['account_no']} — AMR log ผูกไว้กับ {label(r['business_type_code'])}")
        print()


if __name__ == "__main__":
    main()
