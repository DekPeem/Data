"""จัดการรายการใน pending_amr_local.csv ("รอทราบอัตรา") ที่ไม่ควรต้องรอกรอกเองอีกต่อไป — ใช้ตอน
อัปโหลดไฟล์ AMR ซ้ำ (เช่น อัปโหลดโฟลเดอร์เดิมซ้ำ หรือไฟล์ .zip ที่รวมหลายบริษัท ผ่านโหมด "นำเข้า
หลายบริษัทพร้อมกัน") แล้วได้รายการ "รอทราบอัตรา" ของบัญชีที่จริงๆ แล้วรู้ประเภทธุรกิจ/อัตราอยู่แล้ว

แยกเป็น 2 กลุ่ม ทำคนละแบบ (สำคัญมาก — ห้ามลบทั้งคู่เหมือนกัน):

    1. "ลบได้เลย" (--delete-safe) — ไม่มีไฟล์ใหม่ให้เสียของจริงๆ:
       - บัญชีมีประเภทธุรกิจ+อัตราอยู่ในทะเบียนลูกค้าแล้ว (ควรไปกด "บันทึก" ที่หน้า /overview แทน)
       - มีรายการ "รอทราบอัตรา" ซ้ำบัญชีเดียวกันอยู่ก่อนแล้ว (เก็บรายการแรกสุดไว้ ลบตัวที่ซ้ำทีหลัง)

    2. "นำเข้าอัตโนมัติ" (--auto-resolve) — ⚠️ ห้ามลบเฉยๆ เด็ดขาด:
       บัญชีเคยนำเข้า AMR สำเร็จมาก่อนแล้ว (มีในประวัติ import_log_local.csv) แต่ไม่มีในทะเบียน
       ลูกค้า (เช่น นำเข้าผ่านโหมด "ดึงจากเว็บ PEA" ที่กรอกประเภทธุรกิจ/อัตราตรงๆ ไม่เคยผูกกับ
       ทะเบียนลูกค้าเลย) — ไฟล์ที่อัปโหลดรอบใหม่นี้อาจเป็น "เดือนใหม่ที่ยังไม่เคยนำเข้า" ไม่ใช่ไฟล์
       ซ้ำเดือนเดิม ถ้าลบทิ้งเฉยๆ จะเสียข้อมูลจริงไป — โหมดนี้จะดึงประเภทธุรกิจ/อัตราล่าสุดที่เคย
       ใช้กับบัญชีนั้นจากประวัติมา "นำเข้าจริง" ให้ (ข้อมูลใหม่จะถูกถ่วงน้ำหนักรวมกับของเดิมอัตโนมัติ
       ผ่าน upsert_load_profile/upsert_load_curve เหมือนนำเข้าปกติ) แล้วค่อยลบออกจากคิวรอ

โดยดีฟอลต์ (ไม่ใส่ flag ใดเลย) แค่ "แสดงรายการทั้ง 2 กลุ่ม" ให้ดูก่อนเฉยๆ ไม่ทำอะไรจริง

ตัวอย่างการใช้งาน:
    python scripts/dedupe_pending_amr.py                        # ดูรายการทั้ง 2 กลุ่มก่อน (ไม่ทำอะไร)
    python scripts/dedupe_pending_amr.py --delete-safe           # ลบเฉพาะกลุ่มที่ 1 (ปลอดภัย ไม่มีไฟล์ใหม่)
    python scripts/dedupe_pending_amr.py --auto-resolve          # นำเข้ากลุ่มที่ 2 จริง (ไม่ลบเฉยๆ)
    python scripts/dedupe_pending_amr.py --delete-safe --auto-resolve   # ทำทั้งคู่
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.amr_import import import_amr_from_files
from amr_mapping.loader import (
    DEFAULT_DATA_DIR,
    load_import_log_local,
    load_pending_amr_local,
    load_reference_data,
    remove_pending_amr_local,
)


def find_deletable_entries(data_dir: Path) -> List[Tuple[dict, str]]:
    """คืน list ของ (entry, เหตุผล) ที่ลบทิ้งได้เลย ไม่มีไฟล์ใหม่ให้เสียของ (ดู docstring ของโมดูล
    กลุ่มที่ 1) — เรียงตามลำดับที่อ่านจาก pending_amr_local.csv (เก่าไปใหม่ เพราะเป็นไฟล์
    append-only) ถ้าบัญชีเดียวกันมีหลายรายการ จะเก็บรายการแรกสุดไว้เป็น "ตัวจริง" แล้วรายการที่
    เข้ามาทีหลังถือว่าซ้ำซ้อน"""

    reference = load_reference_data(data_dir)
    customers_by_account = {c.account_no: c for c in reference.customers}
    pending_entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")

    deletable: List[Tuple[dict, str]] = []
    seen_accounts_in_pending: dict = {}

    for entry in pending_entries:
        account_no = (entry.get("account_no") or "").strip()
        if not account_no:
            continue  # ไม่มีเลขบัญชี (เช่นใช้ชื่อโฟลเดอร์แทน) เทียบซ้ำซ้อนไม่ได้ ข้ามไปเฉยๆ

        customer = customers_by_account.get(account_no)
        if customer and customer.business_type_code and customer.rate_code:
            deletable.append(
                (
                    entry,
                    f"บัญชี {account_no} มีประเภทธุรกิจ+อัตราในทะเบียนแล้ว "
                    f"({customer.business_type_code}/{customer.rate_code}) — ไปหน้า /overview "
                    'กด "บันทึก" แทนเพื่อนำเข้าจริง',
                )
            )
            continue

        if account_no in seen_accounts_in_pending:
            deletable.append(
                (
                    entry,
                    f"บัญชี {account_no} มีรายการ \"รอทราบอัตรา\" อื่นอยู่แล้ว "
                    f"(pending_id={seen_accounts_in_pending[account_no]}) — รายการนี้ซ้ำซ้อน",
                )
            )
            continue

        seen_accounts_in_pending[account_no] = entry.get("pending_id")

    return deletable


def find_resolvable_entries(data_dir: Path) -> List[Tuple[dict, str, str]]:
    """คืน list ของ (entry, business_type_code, rate_code) ที่ "นำเข้าอัตโนมัติได้" เพราะบัญชีนี้
    เคยนำเข้าสำเร็จมาก่อน (มีในประวัติ import_log_local.csv) แม้จะไม่มีในทะเบียนลูกค้าก็ตาม — ใช้
    ประเภทธุรกิจ/อัตราจากรายการล่าสุดในประวัติของบัญชีนั้น (เรียงตาม imported_at ถ้าพาร์สได้ ไม่งั้น
    ใช้ลำดับที่อ่านจากไฟล์ — ไฟล์เป็น append-only จึงเรียงเก่า->ใหม่อยู่แล้วโดยธรรมชาติ)

    ⚠️ ฟังก์ชันนี้แค่ "หา" ไม่ได้นำเข้าจริง — ดู resolve_entry สำหรับขั้นตอนนำเข้าจริง"""

    import_log_entries = load_import_log_local(data_dir / "import_log_local.csv")
    latest_by_account: Dict[str, dict] = {}
    for e in import_log_entries:
        account_no = (e.get("account_no") or "").strip()
        if account_no:
            latest_by_account[account_no] = e  # เขียนทับเรื่อยๆ -> ตัวสุดท้ายที่เจอคือล่าสุด

    pending_entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")

    resolvable: List[Tuple[dict, str, str]] = []
    for entry in pending_entries:
        account_no = (entry.get("account_no") or "").strip()
        if not account_no or account_no not in latest_by_account:
            continue
        log_entry = latest_by_account[account_no]
        business_type_code = (log_entry.get("business_type_code") or "").strip()
        rate_code = (log_entry.get("rate_code") or "").strip()
        if business_type_code and rate_code:
            resolvable.append((entry, business_type_code, rate_code))

    return resolvable


def resolve_entry(entry: dict, business_type_code: str, rate_code: str, data_dir: Path, log=print) -> bool:
    """นำเข้าไฟล์ AMR ของรายการ pending 1 รายการจริงๆ ด้วยประเภทธุรกิจ/อัตราที่ระบุ (เหมือนกด
    "แก้ไข" ที่หน้า /pending-amr ในเว็บทุกอย่าง) แล้วลบออกจากคิวรอเมื่อสำเร็จ — คืน True ถ้าสำเร็จ"""

    file_paths = [p for p in (entry.get("file_paths") or "").split("|") if p]
    missing = [p for p in file_paths if not Path(p).exists()]
    if not file_paths or missing:
        log(f"  ⚠️ ข้าม (ไม่พบไฟล์ที่เก็บไว้ตอนนำเข้าครั้งแรกแล้ว): {entry.get('company_name') or entry.get('account_no')}")
        return False

    contract_kva: Optional[float] = None
    if entry.get("contract_kva"):
        try:
            contract_kva = float(entry["contract_kva"])
        except ValueError:
            contract_kva = None
    has_solar = entry.get("has_solar") == "true"

    try:
        import_amr_from_files(
            file_paths=file_paths,
            business_type_code=business_type_code,
            rate_code=rate_code,
            contract_kva=contract_kva,
            source_label=entry.get("source_label", ""),
            has_solar=has_solar,
            data_dir=data_dir,
            site_label="",
            log=log,
        )
    except Exception as e:  # noqa: BLE001 — รายการหนึ่งพังต้องไม่ทำให้รายการอื่นหยุดนำเข้าไปด้วย
        log(f"  ❌ นำเข้าไม่สำเร็จ: {entry.get('company_name') or entry.get('account_no')} — {e}")
        return False

    remove_pending_amr_local(entry["pending_id"], data_dir / "pending_amr_local.csv")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delete-safe", action="store_true", help="ลบกลุ่มที่ 1 ออกจริง (ปลอดภัย ไม่มีไฟล์ใหม่ให้เสีย)")
    parser.add_argument("--auto-resolve", action="store_true", help="นำเข้ากลุ่มที่ 2 จริง (ไม่ใช่แค่ลบ — ข้อมูลใหม่จะถูกรวมเข้าไปด้วย)")
    args = parser.parse_args()

    data_dir = DEFAULT_DATA_DIR

    deletable = find_deletable_entries(data_dir)
    resolvable = find_resolvable_entries(data_dir)

    print(f"กลุ่มที่ 1 — ลบได้เลย (ไม่มีไฟล์ใหม่ให้เสีย): {len(deletable)} รายการ")
    for entry, reason in deletable:
        label = entry.get("company_name") or entry.get("account_no") or "(ไม่ทราบชื่อ)"
        print(f"  - {label} (บัญชี {entry.get('account_no') or '-'}) — {reason}")

    print(f"\nกลุ่มที่ 2 — นำเข้าอัตโนมัติได้ (⚠️ ต้องนำเข้าจริง ห้ามลบเฉยๆ): {len(resolvable)} รายการ")
    for entry, business_type_code, rate_code in resolvable:
        label = entry.get("company_name") or entry.get("account_no") or "(ไม่ทราบชื่อ)"
        print(f"  - {label} (บัญชี {entry.get('account_no') or '-'}) — จะนำเข้าด้วย {business_type_code}/{rate_code}")

    if not args.delete_safe and not args.auto_resolve:
        print("\n(นี่แค่แสดงให้ดูก่อนเฉยๆ ยังไม่ได้ทำอะไร — ใส่ --delete-safe และ/หรือ --auto-resolve เพื่อดำเนินการจริง)")
        return

    if args.delete_safe and deletable:
        removed = 0
        for entry, _reason in deletable:
            if remove_pending_amr_local(entry["pending_id"], data_dir / "pending_amr_local.csv"):
                removed += 1
        print(f"\n✅ ลบกลุ่มที่ 1 ไปแล้ว {removed} รายการ")

    if args.auto_resolve and resolvable:
        print("\nกำลังนำเข้ากลุ่มที่ 2 ...")
        succeeded = 0
        for entry, business_type_code, rate_code in resolvable:
            label = entry.get("company_name") or entry.get("account_no") or "(ไม่ทราบชื่อ)"
            print(f"📂 {label} ({business_type_code}/{rate_code})")
            if resolve_entry(entry, business_type_code, rate_code, data_dir, log=lambda m: print(f"  {m}")):
                succeeded += 1
        print(f"\n✅ นำเข้ากลุ่มที่ 2 สำเร็จ {succeeded}/{len(resolvable)} รายการ")


if __name__ == "__main__":
    main()
