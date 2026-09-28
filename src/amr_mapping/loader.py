"""โหลดข้อมูลอ้างอิง (reference data) จากไฟล์ CSV ใน data/reference/"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .models import BusinessType, Customer

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"

_LEADING_FOLDER_INDEX_RE = re.compile(r"^\d+[_\-.\s]+")


def normalize_company_name(name: str) -> str:
    """ตัดช่องว่างซ้ำ/พิมพ์เล็กหมดก่อนเทียบชื่อ + ตัด "เลขลำดับโฟลเดอร์" ที่ Google Drive ชอบนำหน้า
    ชื่อไฟล์/โฟลเดอร์ทิ้งด้วย (เช่น "15_บริษัท โนเบลเอ็นซี จำกัด" หรือ "35_บริษัท เอส เค บี...") —
    เจอกรณีจริงที่ไฟล์อ่านเลขบัญชีไม่ได้เลย ระบบเลยใช้ชื่อโฟลเดอร์ทั้งดุ้น (รวม prefix เลข) แทน
    ทำให้เทียบกับชื่อลูกค้าที่บันทึกไว้แบบสะอาดๆ ในทะเบียนไม่ตรงกันเฉยๆ ทั้งที่เป็นบริษัทเดียวกัน —
    ใช้ร่วมกันทั้ง scripts/dedupe_pending_amr.py (เทียบรายการรอทราบอัตรา) และ web/app.py (เทียบ
    ก่อนนำเข้าโหมดหลายบริษัทพร้อมกัน) กันตรรกะเทียบชื่อเพี้ยนไปคนละแบบ"""

    name = _LEADING_FOLDER_INDEX_RE.sub("", (name or "").strip())
    return " ".join(name.split()).lower()


def _to_bool(value: str) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def _load_business_types(path: Path) -> Dict[str, BusinessType]:
    result: Dict[str, BusinessType] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            # section_code/division_code เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลัง — ไฟล์เก่าที่ยังไม่มี
            # คอลัมน์นี้เลย (row.get คืน None) ต้องโหลดได้ตามปกติ ไม่ error
            section_code = (row.get("section_code") or "").strip() or None
            division_code = (row.get("division_code") or "").strip() or None
            # alias_of เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลังเหมือนกัน — ไฟล์เก่าที่ยังไม่มีคอลัมน์นี้
            # ต้องโหลดได้ตามปกติ (ไม่มี alias เลย)
            alias_of = (row.get("alias_of") or "").strip() or None
            bt = BusinessType(
                code=row["code"].strip(),
                name_th=row["name_th"].strip(),
                category=row["category"].strip(),
                notes=row.get("notes", "").strip(),
                section_code=section_code,
                section_name_th=(row.get("section_name_th") or "").strip(),
                division_code=division_code,
                division_name_th=(row.get("division_name_th") or "").strip(),
                alias_of=alias_of,
            )
            result[bt.code] = bt
    return result


_BUSINESS_TYPE_FIELDNAMES = [
    "code",
    "name_th",
    "category",
    "notes",
    "section_code",
    "section_name_th",
    "division_code",
    "division_name_th",
    "alias_of",
]


def save_business_types(business_types: Dict[str, BusinessType], path: Path) -> None:
    """เขียน business_types กลับเป็นไฟล์ business_types.csv (เขียนทับทั้งไฟล์)"""

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_BUSINESS_TYPE_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for bt in business_types.values():
            writer.writerow(
                {
                    "code": bt.code,
                    "name_th": bt.name_th,
                    "category": bt.category,
                    "notes": bt.notes,
                    "section_code": bt.section_code or "",
                    "section_name_th": bt.section_name_th,
                    "division_code": bt.division_code or "",
                    "division_name_th": bt.division_name_th,
                    "alias_of": bt.alias_of or "",
                }
            )


def load_tsic_code_mapping(path: Optional[Path] = None) -> Dict[str, str]:
    """โหลดตารางแปลงรหัส TSIC ระบบเดิมของ PEA/AMR (TSIC 2544) -> รหัสมาตรฐานใหม่ (TSIC 2552/
    กรมพัฒนาธุรกิจการค้า) จาก data/reference/tsic_code_mapping.csv คืน dict {รหัสเก่า: รหัสใหม่}

    เพิ่มคู่รหัสใหม่ในอนาคตได้ง่ายๆ แค่เพิ่มแถวในไฟล์ CSV นี้ (คอลัมน์ old_code, new_code, notes)
    ไม่ต้องแก้โค้ดไฟล์นี้หรือ tsic_normalize.py เลย — คืน dict ว่างถ้ายังไม่มีไฟล์นี้ (ไม่ error
    ระบบยังทำงานได้ปกติ แค่ไม่แปลงอะไรให้เท่านั้น ดู tsic_normalize.normalize_tsic_code)"""

    path = path or (DEFAULT_DATA_DIR / "tsic_code_mapping.csv")
    mapping: Dict[str, str] = {}
    if not path.exists():
        return mapping
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            old_code = (row.get("old_code") or "").strip()
            new_code = (row.get("new_code") or "").strip()
            if old_code and new_code:
                mapping[old_code] = new_code
    return mapping


def upsert_business_type(business_types: Dict[str, BusinessType], new_bt: BusinessType) -> Dict[str, BusinessType]:
    """แทนที่/เพิ่มประเภทธุรกิจตาม code (คืน dict ใหม่ ไม่แก้ของเดิม)"""

    result = dict(business_types)
    result[new_bt.code] = new_bt
    return result


def _load_customers(path: Path) -> List[Customer]:
    """โหลดทะเบียนผู้ใช้ไฟจากไฟล์ CSV หนึ่งไฟล์ (customers.csv หรือ customers_local.csv)

    ข้ามบรรทัดว่างและบรรทัดที่ขึ้นต้นด้วย "#" (คอมเมนต์) ทิ้งไปเฉยๆ — เผื่อกรณีคัดลอกจาก
    customers_local.csv.example มาโดยลืมลบบรรทัดคำอธิบายที่ขึ้นต้นด้วย # ออกก่อน
    """

    customers: List[Customer] = []
    if not path.exists():
        return customers
    with path.open(encoding="utf-8-sig", newline="") as f:
        lines = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
        for row in csv.DictReader(lines):
            if not row.get("account_no", "").strip():
                continue
            customers.append(
                Customer(
                    account_no=row["account_no"].strip(),
                    name=row["name"].strip(),
                    business_type_code=(row.get("business_type_code") or "").strip() or None,
                    has_amr=_to_bool(row.get("has_amr", "")),
                    # business_type_code_raw เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลัง — ไฟล์เก่าที่ยังไม่มี
                    # คอลัมน์นี้ต้องโหลดได้ตามปกติ (ไม่มี raw code ให้ตรวจสอบ)
                    business_type_code_raw=(row.get("business_type_code_raw") or "").strip() or None,
                    # registration_no เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลังเหมือนกัน — ไฟล์เก่าที่ยังไม่มี
                    # คอลัมน์นี้ต้องโหลดได้ตามปกติ
                    registration_no=(row.get("registration_no") or "").strip() or None,
                )
            )
    return customers


_CUSTOMER_FIELDNAMES = [
    "account_no",
    "name",
    "business_type_code",
    "has_amr",
    "business_type_code_raw",
    "registration_no",
]


def load_customers_local(path: Path) -> List[Customer]:
    """โหลด customers_local.csv ตรงๆ (ไม่รวมกับ customers.csv) — ใช้ตอนจะแก้ไข/upsert แถวเดียว
    ต้องอ่านของเดิมทั้งหมดมาก่อนเขียนทับ คืน list ว่างถ้ายังไม่มีไฟล์"""

    return _load_customers(path)


def save_customers_local(customers: List[Customer], path: Path) -> None:
    """เขียนทับ customers_local.csv ทั้งไฟล์ (ไฟล์นี้อยู่ใน .gitignore แล้ว ห้าม commit เด็ดขาด)"""

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CUSTOMER_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for c in customers:
            writer.writerow(
                {
                    "account_no": c.account_no,
                    "name": c.name,
                    "business_type_code": c.business_type_code or "",
                    "has_amr": "true" if c.has_amr else "false",
                    "business_type_code_raw": c.business_type_code_raw or "",
                    "registration_no": c.registration_no or "",
                }
            )


def upsert_customer_local(path: Path, updated: Customer) -> List[Customer]:
    """แทนที่/เพิ่มลูกค้า 1 รายตาม account_no ใน customers_local.csv (เขียนทับทั้งไฟล์) คืนรายชื่อ
    ทั้งหมดหลังอัปเดต — ใช้ตอนแก้ไขประเภทธุรกิจของบัญชีหนึ่งจากหน้า Admin แล้วต้องการให้ทั้งระบบ
    (หน้าค้นหา ซึ่งอ่านทะเบียนนี้) เห็นค่าใหม่ทันที"""

    customers = load_customers_local(path)
    customers = [c for c in customers if c.account_no != updated.account_no]
    customers.append(updated)
    save_customers_local(customers, path)
    return customers


@dataclass
class ReferenceData:
    business_types: Dict[str, BusinessType]
    customers: List[Customer]


def load_reference_data(data_dir: Optional[Path] = None) -> ReferenceData:
    """โหลดตารางอ้างอิงทั้งหมด (business_types, customers)

    Parameters
    ----------
    data_dir:
        โฟลเดอร์ที่เก็บไฟล์ business_types.csv / customers.csv ถ้าไม่ระบุ จะใช้ data/reference/
        ที่ root ของ repo นี้

    ทะเบียนผู้ใช้ไฟ (customers) โหลดจาก 2 ไฟล์รวมกัน:
      1. customers.csv — สาธิต/ทดสอบเท่านั้น (commit เข้า repo ได้ ห้ามมีข้อมูลลูกค้าจริง)
      2. customers_local.csv — ไม่บังคับต้องมี, ใส่ .gitignore ไว้แล้ว (ไม่ถูก commit
         เด็ดขาด) ใช้เก็บข้อมูลลูกค้าจริงสำหรับดูในเครื่องตัวเองเท่านั้น ถ้ามีบัญชีซ้ำกับ
         customers.csv จะใช้ข้อมูลจาก customers_local.csv แทน (ให้ override ได้)
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

    customers_by_account: Dict[str, Customer] = {c.account_no: c for c in _load_customers(data_dir / "customers.csv")}
    local_path = data_dir / "customers_local.csv"
    if local_path.exists():
        for c in _load_customers(local_path):
            customers_by_account[c.account_no] = c

    return ReferenceData(
        business_types=_load_business_types(data_dir / "business_types.csv"),
        customers=list(customers_by_account.values()),
    )
