"""ตรวจหารายการใน pending_amr_local.csv ("รอทราบอัตรา") ที่ "ไม่จำเป็นต้องรออีกแล้ว" เพราะบัญชี
นั้นมีข้อมูลอยู่แล้วในระบบ — ใช้ตอนอัปโหลดไฟล์ AMR ซ้ำ (เช่น อัปโหลดโฟลเดอร์เดิมซ้ำ หรือไฟล์
.zip ที่รวมหลายบริษัท มีบัญชีที่เคยนำเข้า/เคยรู้จักอยู่แล้วปนอยู่ด้วย ผ่านโหมด "นำเข้าหลายบริษัท
พร้อมกัน") ทำให้ได้รายการ "รอทราบอัตรา" ซ้ำซ้อนกับที่มีอยู่แล้ว

รายการหนึ่งถือว่า "ซ้ำซ้อน" ถ้าเข้าเงื่อนไขข้อใดข้อหนึ่ง:
    1. บัญชีนั้นมีประเภทธุรกิจ+รหัสอัตราอยู่ในทะเบียนลูกค้าแล้ว (customers.csv/customers_local.csv)
       — ไม่ควรต้องรอกรอกเองอีก ไปที่หน้า /overview แล้วกด "บันทึก" แทนเพื่อนำเข้าจริง
    2. บัญชีนั้นเคยนำเข้า AMR สำเร็จมาก่อนแล้ว (มีในประวัติการนำเข้า import_log_local.csv)
    3. มีรายการ "รอทราบอัตรา" อื่นของบัญชีเดียวกันอยู่ก่อนแล้ว (รายการที่เข้ามาทีหลังถือว่าซ้ำซ้อน)

โดยดีฟอลต์แค่ "แสดงรายการที่ซ้ำซ้อน" ให้ดูก่อนเฉยๆ (dry-run) ไม่ลบอะไรจริง — ต้องใส่ --apply
ถึงจะลบออกจาก pending_amr_local.csv จริง (ไฟล์ AMR ที่แนบไว้ตอนนำเข้าครั้งนั้นไม่ถูกลบตามไปด้วย
ยังอยู่ที่ amr_downloads/uploaded/ เหมือนเดิม)

ตัวอย่างการใช้งาน:
    python scripts/dedupe_pending_amr.py              # ดูรายการที่ซ้ำซ้อนก่อน (ไม่ลบ)
    python scripts/dedupe_pending_amr.py --apply       # ลบรายการที่ซ้ำซ้อนออกจริง
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import (
    DEFAULT_DATA_DIR,
    load_import_log_local,
    load_pending_amr_local,
    load_reference_data,
    remove_pending_amr_local,
)


def find_redundant_pending_entries(data_dir: Path) -> List[Tuple[dict, str]]:
    """คืน list ของ (entry, เหตุผล) ที่ "ไม่จำเป็นต้องรออีกแล้ว" — ฟังก์ชันนี้แค่หา ไม่ลบอะไรเอง
    เรียงตามลำดับที่อ่านจาก pending_amr_local.csv (เก่าไปใหม่ เพราะเป็นไฟล์ append-only) —
    ถ้าบัญชีเดียวกันมีหลายรายการ จะเก็บรายการแรกสุดไว้เป็น "ตัวจริง" แล้วรายการที่เข้ามาทีหลัง
    ถือว่าซ้ำซ้อนทั้งหมด"""

    reference = load_reference_data(data_dir)
    customers_by_account = {c.account_no: c for c in reference.customers}

    import_log_entries = load_import_log_local(data_dir / "import_log_local.csv")
    imported_accounts = {e.get("account_no") for e in import_log_entries if e.get("account_no")}

    pending_entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")

    redundant: List[Tuple[dict, str]] = []
    seen_accounts_in_pending: dict = {}

    for entry in pending_entries:
        account_no = (entry.get("account_no") or "").strip()
        if not account_no:
            continue  # ไม่มีเลขบัญชี (เช่นใช้ชื่อโฟลเดอร์แทน) เทียบซ้ำซ้อนไม่ได้ ข้ามไปเฉยๆ

        customer = customers_by_account.get(account_no)
        if customer and customer.business_type_code and customer.rate_code:
            redundant.append(
                (
                    entry,
                    f"บัญชี {account_no} มีประเภทธุรกิจ+อัตราในทะเบียนแล้ว "
                    f"({customer.business_type_code}/{customer.rate_code}) — ไปหน้า /overview "
                    'กด "บันทึก" แทนเพื่อนำเข้าจริง',
                )
            )
            continue

        if account_no in imported_accounts:
            redundant.append(
                (entry, f"บัญชี {account_no} เคยนำเข้าสำเร็จมาก่อนแล้ว (มีในประวัติการนำเข้า import_log_local.csv)")
            )
            continue

        if account_no in seen_accounts_in_pending:
            redundant.append(
                (
                    entry,
                    f"บัญชี {account_no} มีรายการ \"รอทราบอัตรา\" อื่นอยู่แล้ว "
                    f"(pending_id={seen_accounts_in_pending[account_no]}) — รายการนี้ซ้ำซ้อน",
                )
            )
            continue

        seen_accounts_in_pending[account_no] = entry.get("pending_id")

    return redundant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="ลบรายการที่ซ้ำซ้อนออกจริง (ไม่ใส่ = แค่แสดงให้ดูก่อนเฉยๆ)")
    args = parser.parse_args()

    data_dir = DEFAULT_DATA_DIR
    redundant = find_redundant_pending_entries(data_dir)

    if not redundant:
        print('ไม่พบรายการ "รอทราบอัตรา" ที่ซ้ำซ้อนเลย')
        return

    print(f"พบ {len(redundant)} รายการที่ซ้ำซ้อน/ไม่จำเป็นต้องรออีกแล้ว:\n")
    for entry, reason in redundant:
        label = entry.get("company_name") or entry.get("account_no") or "(ไม่ทราบชื่อ)"
        print(f"  - {label} (บัญชี {entry.get('account_no') or '-'}) — {reason}")

    if not args.apply:
        print('\n(นี่แค่แสดงให้ดูก่อนเฉยๆ ยังไม่ได้ลบ — รันซ้ำพร้อม --apply เพื่อลบออกจริง)')
        return

    removed = 0
    for entry, _reason in redundant:
        if remove_pending_amr_local(entry["pending_id"], data_dir / "pending_amr_local.csv"):
            removed += 1
    print(f"\nลบไปแล้ว {removed} รายการ")


if __name__ == "__main__":
    main()
