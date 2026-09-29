"""ย้ายรายชื่อบริษัทจาก import_log_local.csv (ไฟล์ log เก่าของฟีเจอร์นำเข้า AMR ที่ถูกตัดออก
จากระบบไปแล้ว) เข้าไปใน customers_local.csv ให้ครบ — ทำครั้งเดียวหลังอัปเดตโค้ด

ทำไมต้องรันสคริปต์นี้: หน้า /overview เวอร์ชันเก่ารวมข้อมูลจาก 2 ไฟล์เข้าด้วยกัน — customers_local.csv
(ทะเบียนที่บันทึกไว้ล่วงหน้า/แก้ไขเอง) กับ import_log_local.csv (ประวัติทุกครั้งที่นำเข้าไฟล์ AMR
ผ่านหน้า Admin เดิม) บริษัทจำนวนมากเข้าระบบทาง import_log_local.csv เพียงอย่างเดียว ไม่เคยถูกเขียน
ลง customers_local.csv เลย — พอฟีเจอร์นำเข้า AMR (และไฟล์ import_log_local.csv) ถูกตัดออกจากระบบ
พร้อมกับ /api/import-log-local หน้า /overview เวอร์ชันใหม่จึงอ่านได้แค่ customers_local.csv อย่างเดียว
ทำให้บริษัทที่เข้าระบบผ่าน import log ล้วนๆ หายไปจากตารางทันที (ไฟล์ยังอยู่ในเครื่อง แค่ไม่มีโค้ด
ฝั่งไหนอ่านมันแล้ว)

สคริปต์นี้อ่าน import_log_local.csv (ถ้ามี) รวมกับ customers_local.csv ปัจจุบัน แล้วเขียนกลับ
customers_local.csv ให้ครบทุกบัญชี (บัญชีที่มีอยู่ใน customers_local.csv แล้วจะไม่ถูกแก้ไข/เขียนทับ —
customers_local.csv ชนะเสมอเหมือนตรรกะเดิมของหน้า /overview) รันได้ซ้ำหลายครั้งโดยไม่มีผลเสีย
(idempotent — รันซ้ำแล้วไม่เพิ่มบัญชีซ้ำ)

ใช้:
    python scripts/migrate_import_log_to_customers.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import DEFAULT_DATA_DIR, load_customers_local, save_customers_local
from amr_mapping.models import Customer

_IMPORT_LOG_FIELDNAMES = [
    "imported_at",
    "business_type_code",
    "rate_code",
    "company_name",
    "account_no",
    "has_solar",
    "business_type_code_raw",
    "file_signature",
]


def _load_import_log(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        # ตัดคีย์ None ทิ้ง (ragged rows จากไฟล์เก่าก่อน migrate header) เหมือนที่โค้ดเดิมทำ
        return [{k: v for k, v in row.items() if k is not None} for row in csv.DictReader(f)]


def main() -> None:
    import_log_path = DEFAULT_DATA_DIR / "import_log_local.csv"
    customers_local_path = DEFAULT_DATA_DIR / "customers_local.csv"

    entries = _load_import_log(import_log_path)
    if not entries:
        print(f"ไม่พบ {import_log_path} เลย (หรือว่างเปล่า) — ไม่มีอะไรให้ย้าย")
        return

    existing = load_customers_local(customers_local_path)
    existing_accounts = {c.account_no for c in existing}

    # ไฟล์ log เป็นแบบ append-only (เขียนต่อท้ายทุกครั้งที่นำเข้า) — แถวหลังสุดของบัญชีเดียวกัน
    # คือข้อมูลล่าสุด เก็บแค่แถวล่าสุดต่อบัญชี (เดินไล่ตามลำดับไฟล์ ทับค่าเก่าด้วยค่าใหม่กว่าเรื่อยๆ)
    latest_by_account: dict = {}
    for entry in entries:
        account_no = (entry.get("account_no") or "").strip()
        if account_no:
            latest_by_account[account_no] = entry

    added: list = []
    for account_no, entry in latest_by_account.items():
        if account_no in existing_accounts:
            continue  # customers_local.csv ชนะเสมอ ไม่เขียนทับของที่มีอยู่แล้ว

        existing.append(
            Customer(
                account_no=account_no,
                name=(entry.get("company_name") or "").strip() or account_no,
                business_type_code=(entry.get("business_type_code") or "").strip() or None,
                has_amr=True,
                business_type_code_raw=(entry.get("business_type_code_raw") or "").strip() or None,
            )
        )
        added.append(account_no)

    if not added:
        print("ทุกบัญชีใน import_log_local.csv มีอยู่ใน customers_local.csv แล้ว — ไม่มีอะไรให้เพิ่ม")
        return

    save_customers_local(existing, customers_local_path)
    print(f"เพิ่ม {len(added)} บัญชีเข้า {customers_local_path} แล้ว:")
    for account_no in added:
        entry = latest_by_account[account_no]
        print(f"  {entry.get('company_name') or '(ไม่ทราบชื่อ)'} — บัญชี {account_no}")


if __name__ == "__main__":
    main()
