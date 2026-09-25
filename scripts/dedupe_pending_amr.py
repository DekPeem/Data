"""จัดการรายการใน pending_amr_local.csv ("รอทราบอัตรา") ที่ไม่ควรต้องรอกรอกเองอีกต่อไป — ใช้ตอน
อัปโหลดไฟล์ AMR ซ้ำ (เช่น อัปโหลดโฟลเดอร์เดิมซ้ำ หรือไฟล์ .zip ที่รวมหลายบริษัท ผ่านโหมด "นำเข้า
หลายบริษัทพร้อมกัน") แล้วได้รายการ "รอทราบอัตรา" ของบัญชีที่จริงๆ แล้วรู้ประเภทธุรกิจ/อัตราอยู่แล้ว

แยกเป็น 2 กลุ่ม ทำคนละแบบ (สำคัญมาก — ห้ามลบทั้งคู่เหมือนกัน):

    1. "ลบได้เลย" (--delete-safe) — ไม่มีไฟล์ใหม่ให้เสียของจริงๆ:
       - บัญชีมีประเภทธุรกิจ+อัตราอยู่ในทะเบียนลูกค้าแล้ว (ควรไปกด "บันทึก" ที่หน้า /overview แทน)
       - มีรายการ "รอทราบอัตรา" ซ้ำบัญชีเดียวกันอยู่ก่อนแล้ว (เก็บรายการแรกสุดไว้ ลบตัวที่ซ้ำทีหลัง)
       - เนื้อหาไฟล์ตรงกับที่เคยนำเข้าไปแล้วเป๊ะทุกตัวอักษร (เทียบด้วย hash เนื้อหาไฟล์ ไม่ใช่แค่เลข
         บัญชี — ดู compute_file_signature ใน loader.py) เช่น อัปโหลด zip/โฟลเดอร์เดิมซ้ำโดยไม่ได้
         ตั้งใจ ยืนยันได้ชัดเจนว่าเป็นไฟล์ชุดเดิมเป๊ะ ไม่ใช่แค่ "บัญชีเดิมแต่อาจเป็นเดือนใหม่" จึงลบได้
         โดยไม่ต้องนำเข้าซ้ำ (⚠️ ใช้ได้เฉพาะบัญชีที่การนำเข้าครั้งก่อนบันทึก file_signature ไว้แล้ว
         เท่านั้น — รายการเก่าที่นำเข้าไปก่อนเพิ่มฟีเจอร์นี้จะไม่มีให้เทียบ ตกไปอยู่กลุ่มที่ 2 แทน)

    2. บัญชีเคยนำเข้า AMR สำเร็จมาก่อนแล้ว (มีในประวัติ import_log_local.csv) แต่ไม่มีในทะเบียน
       ลูกค้า (เช่น นำเข้าผ่านโหมด "ดึงจากเว็บ PEA" ที่กรอกประเภทธุรกิจ/อัตราตรงๆ ไม่เคยผูกกับ
       ทะเบียนลูกค้าเลย) — กลุ่มนี้ "เทียบด้วยเลขบัญชีอย่างเดียว" แยกแยะไม่ได้เองว่าไฟล์รอบใหม่คือ
       (ก) เดือนใหม่ที่ยังไม่เคยนำเข้า → ต้อง "นำเข้าจริง" ไม่ใช่ลบทิ้ง หรือ (ข) อัปโหลด zip/โฟลเดอร์
       เดิมซ้ำโดยไม่ได้ตั้งใจ (เช่น กดผิด/ทดสอบซ้ำ) → ข้อมูลถูกรวมเข้า load_profiles/load_curves
       ไปแล้วตั้งแต่รอบก่อน ถ้า "นำเข้าซ้ำ" อีกจะยิ่งถ่วงน้ำหนัก sample_size เพิ่มเป็นสองเท่าผิดๆ
       ต้องเลือกเอาอย่างใดอย่างหนึ่งเท่านั้น (ห้ามใส่ทั้งคู่พร้อมกัน):

       - (--auto-resolve) กรณี (ก) — ดึงประเภทธุรกิจ/อัตราล่าสุดที่เคยใช้กับบัญชีนั้นจากประวัติมา
         "นำเข้าจริง" ให้ (ข้อมูลใหม่จะถูกถ่วงน้ำหนักรวมกับของเดิมอัตโนมัติผ่าน
         upsert_load_profile/upsert_load_curve เหมือนนำเข้าปกติ) แล้วค่อยลบออกจากคิวรอ
       - (--delete-duplicates) กรณี (ข) — ⚠️ ใช้เฉพาะตอนที่ "ยืนยันแล้วจริงๆ" ว่าเป็นการอัปโหลดซ้ำ
         ของเดิม (เช่น ผู้ใช้ยืนยันเองว่ากดอัปโหลดไฟล์/โฟลเดอร์เดิมซ้ำ) เท่านั้น — ลบรายการออกจากคิวรอ
         เฉยๆ โดยไม่นำเข้าซ้ำ เพราะข้อมูลถูกรวมเข้าไปแล้วตั้งแต่รอบก่อนหน้า ห้ามใช้เป็นค่าเริ่มต้น
         หรือเดาเอาเองว่าเป็นกรณีนี้ — ถ้าไม่แน่ใจว่าเป็นไฟล์ใหม่หรือไฟล์ซ้ำ ให้ใช้ --auto-resolve
         แทนเสมอ (นำเข้าซ้ำโดยไม่ตั้งใจแค่ทำให้ตัวเลขเบี้ยว แต่ลบไฟล์ใหม่ทิ้งจะเสียข้อมูลจริงถาวร)

    3. "ชื่อตรงกับที่มีอยู่แล้ว แต่ไม่มีเลขบัญชีให้ยืนยัน" (--delete-name-matches) — ⚠️ เสี่ยงสุด
       ในสามกลุ่ม ต้องเช็คเองก่อนเสมอ: รายการที่อ่านเลขบัญชีจากไฟล์ไม่ได้เลย (ใช้ชื่อโฟลเดอร์แทน)
       แต่ชื่อไปตรงกับชื่อลูกค้าที่มีอยู่แล้วในทะเบียนพอดี — เทียบด้วย "ชื่อ" เท่านั้น (ไม่มีเลขบัญชี
       ให้ยืนยันแบบกลุ่มที่ 1) อาจเป็นบริษัทคนละรายที่ชื่อพ้องกันก็ได้ หรือไฟล์อาจเป็นเดือนใหม่จริงๆ
       ก็ได้ — ให้ "แสดงให้ดูเฉยๆ" เป็นค่าเริ่มต้นเสมอ (ไม่ถูกลบพร้อมกลุ่ม 1/2 แม้ใส่ --delete-safe
       ก็ตาม) ต้องใส่ --delete-name-matches แยกต่างหากอย่างตั้งใจเท่านั้นถึงจะลบ

โดยดีฟอลต์ (ไม่ใส่ flag ใดเลย) แค่ "แสดงรายการทั้ง 3 กลุ่ม" ให้ดูก่อนเฉยๆ ไม่ทำอะไรจริง

ตัวอย่างการใช้งาน:
    python scripts/dedupe_pending_amr.py                        # ดูรายการทั้ง 3 กลุ่มก่อน (ไม่ทำอะไร)
    python scripts/dedupe_pending_amr.py --delete-safe           # ลบเฉพาะกลุ่มที่ 1 (ปลอดภัย ไม่มีไฟล์ใหม่)
    python scripts/dedupe_pending_amr.py --auto-resolve          # นำเข้ากลุ่มที่ 2 จริง (คิดว่าเป็นไฟล์ใหม่)
    python scripts/dedupe_pending_amr.py --delete-duplicates     # ลบกลุ่มที่ 2 เฉยๆ (⚠️ ยืนยันแล้วว่าซ้ำของเดิม)
    python scripts/dedupe_pending_amr.py --delete-name-matches   # ลบกลุ่มที่ 3 (เช็คเองให้แน่ใจก่อน!)
    python scripts/dedupe_pending_amr.py --delete-safe --auto-resolve   # ทำ 1+2 พร้อมกัน
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
    compute_file_signature,
    load_import_log_local,
    load_pending_amr_local,
    load_reference_data,
    normalize_company_name,
    remove_pending_amr_local,
)


def _file_signatures_by_account(data_dir: Path) -> Dict[str, set]:
    """รวม file_signature ทุกอันที่เคยนำเข้าสำเร็จ แยกตามเลขบัญชี (ใช้เทียบเนื้อหาไฟล์ที่อัปโหลด
    รอบใหม่ว่าตรงกับที่เคยนำเข้าไปแล้วเป๊ะหรือไม่ — รายการเก่าที่นำเข้าก่อนเพิ่มฟีเจอร์นี้จะไม่มี
    file_signature บันทึกไว้ (ค่าว่าง) จึงเทียบไม่ได้และไม่ถูกนับ)"""

    import_log_entries = load_import_log_local(data_dir / "import_log_local.csv")
    signatures: Dict[str, set] = {}
    for e in import_log_entries:
        account_no = (e.get("account_no") or "").strip()
        sig = (e.get("file_signature") or "").strip()
        if account_no and sig:
            signatures.setdefault(account_no, set()).add(sig)
    return signatures


def find_deletable_entries(data_dir: Path) -> List[Tuple[dict, str]]:
    """คืน list ของ (entry, เหตุผล) ที่ลบทิ้งได้เลย ไม่มีไฟล์ใหม่ให้เสียของ (ดู docstring ของโมดูล
    กลุ่มที่ 1) — เรียงตามลำดับที่อ่านจาก pending_amr_local.csv (เก่าไปใหม่ เพราะเป็นไฟล์
    append-only) ถ้าบัญชีเดียวกันมีหลายรายการ จะเก็บรายการแรกสุดไว้เป็น "ตัวจริง" แล้วรายการที่
    เข้ามาทีหลังถือว่าซ้ำซ้อน"""

    reference = load_reference_data(data_dir)
    customers_by_account = {c.account_no: c for c in reference.customers}
    pending_entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")
    signatures_by_account = _file_signatures_by_account(data_dir)

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

        known_signatures = signatures_by_account.get(account_no)
        if known_signatures:
            file_paths = [p for p in (entry.get("file_paths") or "").split("|") if p]
            sig = compute_file_signature(file_paths)
            if sig and sig in known_signatures:
                deletable.append(
                    (
                        entry,
                        f"เนื้อหาไฟล์ตรงกับที่เคยนำเข้าไปแล้วเป๊ะ (บัญชี {account_no}) — น่าจะเป็นการ"
                        "อัปโหลดไฟล์/zip เดิมซ้ำ ไม่ใช่ข้อมูลใหม่",
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
    signatures_by_account = _file_signatures_by_account(data_dir)

    resolvable: List[Tuple[dict, str, str]] = []
    for entry in pending_entries:
        account_no = (entry.get("account_no") or "").strip()
        if not account_no or account_no not in latest_by_account:
            continue

        known_signatures = signatures_by_account.get(account_no)
        if known_signatures:
            file_paths = [p for p in (entry.get("file_paths") or "").split("|") if p]
            sig = compute_file_signature(file_paths)
            if sig and sig in known_signatures:
                continue  # เนื้อหาไฟล์ตรงกับที่เคยนำเข้าไปแล้วเป๊ะ -> find_deletable_entries จัดการแทน

        log_entry = latest_by_account[account_no]
        business_type_code = (log_entry.get("business_type_code") or "").strip()
        rate_code = (log_entry.get("rate_code") or "").strip()
        if business_type_code and rate_code:
            resolvable.append((entry, business_type_code, rate_code))

    return resolvable


def find_name_match_candidates(data_dir: Path) -> List[Tuple[dict, "object"]]:
    """คืน list ของ (entry, ลูกค้าที่มีอยู่แล้วในทะเบียน) ที่ "ชื่อตรงกัน" สำหรับรายการ pending ที่
    ไม่มีเลขบัญชีเลย (เทียบเลขบัญชีแบบกลุ่มที่ 1/2 ไม่ได้) — เทียบชื่อแบบตัดช่องว่างซ้ำ/พิมพ์เล็ก
    หมดก่อนเทียบ (กัน "บริษัท เอ" vs "บริษัท เอ " หรือตัวพิมพ์ใหญ่-เล็กต่างกันไม่ตรงกันเฉยๆ) แต่ก็ยัง
    เป็นแค่การเทียบชื่อ ไม่ใช่เลขบัญชี — อาจมีบริษัทคนละรายชื่อพ้องกันได้ ⚠️ ต้องเช็คเองก่อนลบเสมอ
    (ดู docstring ของโมดูล กลุ่มที่ 3)"""

    reference = load_reference_data(data_dir)
    customers_by_name = {normalize_company_name(c.name): c for c in reference.customers if c.name}

    pending_entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")

    matches: List[Tuple[dict, object]] = []
    for entry in pending_entries:
        if (entry.get("account_no") or "").strip():
            continue  # มีเลขบัญชีอยู่แล้ว ให้กลุ่มที่ 1/2 (เทียบด้วยเลขบัญชี แม่นกว่า) จัดการไป
        company_name = normalize_company_name(entry.get("company_name") or "")
        if not company_name:
            continue
        customer = customers_by_name.get(company_name)
        if customer:
            matches.append((entry, customer))

    return matches


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
    parser.add_argument(
        "--auto-resolve",
        action="store_true",
        help="นำเข้ากลุ่มที่ 2 จริง (คิดว่าเป็นไฟล์/เดือนใหม่ที่ยังไม่เคยนำเข้า — ห้ามใช้พร้อม --delete-duplicates)",
    )
    parser.add_argument(
        "--delete-duplicates",
        action="store_true",
        help="ลบกลุ่มที่ 2 ออกจริงโดยไม่นำเข้า (⚠️ ใช้เฉพาะตอนยืนยันแล้วว่าเป็นการอัปโหลดซ้ำของเดิม — ห้ามใช้พร้อม --auto-resolve)",
    )
    parser.add_argument(
        "--delete-name-matches",
        action="store_true",
        help="ลบกลุ่มที่ 3 ออกจริง (⚠️ เทียบด้วยชื่อเท่านั้น ไม่มีเลขบัญชียืนยัน เช็คเองให้แน่ใจก่อนเสมอ)",
    )
    args = parser.parse_args()

    if args.auto_resolve and args.delete_duplicates:
        parser.error("ใส่ --auto-resolve กับ --delete-duplicates พร้อมกันไม่ได้ (เป็นการกระทำที่ตรงข้ามกันบนกลุ่มเดียวกัน — เลือกอย่างใดอย่างหนึ่ง)")

    data_dir = DEFAULT_DATA_DIR

    deletable = find_deletable_entries(data_dir)
    resolvable = find_resolvable_entries(data_dir)
    name_matches = find_name_match_candidates(data_dir)

    print(f"กลุ่มที่ 1 — ลบได้เลย (ไม่มีไฟล์ใหม่ให้เสีย): {len(deletable)} รายการ")
    for entry, reason in deletable:
        label = entry.get("company_name") or entry.get("account_no") or "(ไม่ทราบชื่อ)"
        print(f"  - {label} (บัญชี {entry.get('account_no') or '-'}) — {reason}")

    print(
        f"\nกลุ่มที่ 2 — บัญชีนี้เคยนำเข้าสำเร็จมาก่อน: {len(resolvable)} รายการ "
        "(⚠️ เลือกเอา: --auto-resolve ถ้าเป็นไฟล์/เดือนใหม่ | --delete-duplicates ถ้ายืนยันแล้วว่าซ้ำของเดิม)"
    )
    for entry, business_type_code, rate_code in resolvable:
        label = entry.get("company_name") or entry.get("account_no") or "(ไม่ทราบชื่อ)"
        print(f"  - {label} (บัญชี {entry.get('account_no') or '-'}) — ประวัติล่าสุดคือ {business_type_code}/{rate_code}")

    print(f"\nกลุ่มที่ 3 — ชื่อตรงกับที่มีอยู่แล้ว แต่ไม่มีเลขบัญชียืนยัน (⚠️ เช็คเองก่อนลบเสมอ): {len(name_matches)} รายการ")
    for entry, customer in name_matches:
        label = entry.get("company_name") or "(ไม่ทราบชื่อ)"
        known_rate = customer.rate_code or "ไม่ทราบอัตรา"
        print(
            f"  - {label} — ชื่อตรงกับบัญชี {customer.account_no} ที่มีอยู่แล้ว "
            f"({customer.business_type_code or '?'}/{known_rate}) — อาจเป็นบริษัทเดียวกันจริง หรือชื่อพ้องกันก็ได้"
        )

    if not args.delete_safe and not args.auto_resolve and not args.delete_duplicates and not args.delete_name_matches:
        print(
            "\n(นี่แค่แสดงให้ดูก่อนเฉยๆ ยังไม่ได้ทำอะไร — ใส่ --delete-safe / --auto-resolve / "
            "--delete-duplicates / --delete-name-matches เพื่อดำเนินการจริง)"
        )
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

    if args.delete_duplicates and resolvable:
        removed = 0
        for entry, _business_type_code, _rate_code in resolvable:
            if remove_pending_amr_local(entry["pending_id"], data_dir / "pending_amr_local.csv"):
                removed += 1
        print(f"\n✅ ลบกลุ่มที่ 2 ไปแล้ว {removed} รายการ (ไม่ได้นำเข้าซ้ำ — ถือว่าข้อมูลถูกรวมเข้าไปแล้วตั้งแต่รอบก่อนหน้า)")

    if args.delete_name_matches and name_matches:
        removed = 0
        for entry, _customer in name_matches:
            if remove_pending_amr_local(entry["pending_id"], data_dir / "pending_amr_local.csv"):
                removed += 1
        print(f"\n✅ ลบกลุ่มที่ 3 ไปแล้ว {removed} รายการ")


if __name__ == "__main__":
    main()
