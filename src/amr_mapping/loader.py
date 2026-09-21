"""โหลดข้อมูลอ้างอิง (reference data) จากไฟล์ CSV ใน data/reference/"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .models import DAY_TYPES, BusinessType, Customer, LoadCurve, LoadProfile, RateSchedule, PERIODS

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"


def _to_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if value == "":
        return None
    return float(value)


def _to_bool(value: str) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def _to_optional_bool(value: str) -> Optional[bool]:
    """แปลงค่า tri-state: "" (ไม่ทราบ) -> None, "true"/"1"/"yes" -> True, อย่างอื่น -> False"""

    value = (value or "").strip().lower()
    if value == "":
        return None
    return value in ("1", "true", "yes")


def _load_business_types(path: Path) -> Dict[str, BusinessType]:
    result: Dict[str, BusinessType] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            # section_code/division_code เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลัง — ไฟล์เก่าที่ยังไม่มี
            # คอลัมน์นี้เลย (row.get คืน None) ต้องโหลดได้ตามปกติ ไม่ error
            section_code = (row.get("section_code") or "").strip() or None
            division_code = (row.get("division_code") or "").strip() or None
            bt = BusinessType(
                code=row["code"].strip(),
                name_th=row["name_th"].strip(),
                category=row["category"].strip(),
                notes=row.get("notes", "").strip(),
                section_code=section_code,
                section_name_th=(row.get("section_name_th") or "").strip(),
                division_code=division_code,
                division_name_th=(row.get("division_name_th") or "").strip(),
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
]


def save_business_types(business_types: Dict[str, BusinessType], path: Path) -> None:
    """เขียน business_types กลับเป็นไฟล์ business_types.csv (เขียนทับทั้งไฟล์)"""

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_BUSINESS_TYPE_FIELDNAMES)
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
                }
            )


def upsert_business_type(business_types: Dict[str, BusinessType], new_bt: BusinessType) -> Dict[str, BusinessType]:
    """แทนที่/เพิ่มประเภทธุรกิจตาม code (คืน dict ใหม่ ไม่แก้ของเดิม)"""

    result = dict(business_types)
    result[new_bt.code] = new_bt
    return result


def _load_rate_schedules(path: Path) -> Dict[str, RateSchedule]:
    result: Dict[str, RateSchedule] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rs = RateSchedule(
                code=row["code"].strip(),
                billing_method=row["billing_method"].strip(),
                voltage_level=row["voltage_level"].strip(),
                description=row.get("description", "").strip(),
            )
            result[rs.code] = rs
    return result


def _load_load_profiles(path: Path) -> List[LoadProfile]:
    profiles: List[LoadProfile] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            demand_kw = {p: _to_float(row[f"demand_{p.lower()}_kw"]) or 0.0 for p in PERIODS}
            energy_kwh = {p: _to_float(row[f"energy_{p.lower()}_kwh"]) or 0.0 for p in PERIODS}
            profiles.append(
                LoadProfile(
                    business_type_code=row["business_type_code"].strip(),
                    rate_code=row["rate_code"].strip(),
                    billing_method=row["billing_method"].strip(),
                    demand_kw=demand_kw,
                    energy_kwh=energy_kwh,
                    contract_kva_ref=_to_float(row.get("contract_kva_ref", "")),
                    sample_size=int((row.get("sample_size") or "0").strip() or 0),
                    notes=row.get("notes", "").strip(),
                    # has_solar เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลัง — ไฟล์เก่าที่ไม่มีคอลัมน์นี้
                    # (row.get คืน None) ต้องโหลดได้ตามปกติ ถือว่าไม่ติด Solar (False)
                    has_solar=_to_bool(row.get("has_solar", "")),
                )
            )
    return profiles


_CURVE_HOUR_FIELDNAMES = [f"h{h:02d}" for h in range(24)]
_LOAD_CURVE_FIELDNAMES = [
    "business_type_code",
    "rate_code",
    "day_type",
    "contract_kva_ref",
    "sample_size",
    "notes",
    "has_solar",
] + _CURVE_HOUR_FIELDNAMES


def _load_load_curves(path: Path) -> List[LoadCurve]:
    """โหลด load_curves.csv (เส้นโค้งรายชั่วโมง แยกตามวัน) — ไฟล์นี้เป็นฟีเจอร์เสริมที่เพิ่ม
    เข้ามาทีหลัง ถ้ายังไม่มีไฟล์ (data dir เก่า) ให้ถือว่าไม่มีข้อมูลเส้นโค้งเลย ไม่ error"""

    if not path.exists():
        return []

    curves_by_key: Dict[tuple, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            business_type_code = row["business_type_code"].strip()
            rate_code = row["rate_code"].strip()
            day_type = row["day_type"].strip()
            # has_solar เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลัง (เหมือน load_profiles.csv) — ไฟล์เก่า
            # ที่ไม่มีคอลัมน์นี้ถือว่าไม่ติด Solar (False) และเป็นส่วนหนึ่งของ key เพื่อไม่ให้
            # เส้นโค้งที่ติด/ไม่ติด Solar ของธุรกิจ+อัตราเดียวกันถูกรวมเป็นแถวเดียวกันโดยไม่ตั้งใจ
            has_solar = _to_bool(row.get("has_solar", ""))
            key = (business_type_code, rate_code, has_solar)
            entry = curves_by_key.setdefault(
                key,
                {
                    "business_type_code": business_type_code,
                    "rate_code": rate_code,
                    "has_solar": has_solar,
                    "hours": {},
                    "contract_kva_ref": _to_float(row.get("contract_kva_ref", "")),
                    "sample_size": int((row.get("sample_size") or "0").strip() or 0),
                    "notes": row.get("notes", "").strip(),
                },
            )
            entry["hours"][day_type] = [_to_float(row.get(f"h{h:02d}", "")) for h in range(24)]

    return [
        LoadCurve(
            business_type_code=e["business_type_code"],
            rate_code=e["rate_code"],
            hours=e["hours"],
            contract_kva_ref=e["contract_kva_ref"],
            sample_size=e["sample_size"],
            notes=e["notes"],
            has_solar=e["has_solar"],
        )
        for e in curves_by_key.values()
    ]


def save_load_curves(curves: List[LoadCurve], path: Path) -> None:
    """เขียนรายการ LoadCurve กลับเป็นไฟล์ load_curves.csv (เขียนทับทั้งไฟล์) — 1 curve
    เขียนเป็นหลายแถว (แถวละ 1 day_type) เท่าจำนวน day_type ที่มีข้อมูลจริงเท่านั้น"""

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_LOAD_CURVE_FIELDNAMES)
        writer.writeheader()
        for curve in curves:
            for day_type in DAY_TYPES:
                if day_type not in curve.hours:
                    continue
                row = {
                    "business_type_code": curve.business_type_code,
                    "rate_code": curve.rate_code,
                    "day_type": day_type,
                    "contract_kva_ref": "" if curve.contract_kva_ref is None else curve.contract_kva_ref,
                    "sample_size": curve.sample_size,
                    "notes": curve.notes,
                    "has_solar": "true" if curve.has_solar else "false",
                }
                for h, val in enumerate(curve.hours[day_type]):
                    row[f"h{h:02d}"] = "" if val is None else val
                writer.writerow(row)


def upsert_load_curve(curves: List[LoadCurve], new_curve: LoadCurve) -> List[LoadCurve]:
    """แทนที่เส้นโค้งที่มี key (business_type_code, rate_code) ตรงกัน ด้วยเส้นโค้งใหม่
    หรือเพิ่มต่อท้ายถ้ายังไม่มีคู่นี้อยู่ (คืน list ใหม่ ไม่แก้ของเดิม)"""

    result = [c for c in curves if c.key() != new_curve.key()]
    result.append(new_curve)
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
                    rate_code=(row.get("rate_code") or "").strip() or None,
                    contract_kva=_to_float(row.get("contract_kva", "")),
                    has_amr=_to_bool(row.get("has_amr", "")),
                    # has_solar เป็นคอลัมน์ที่เพิ่มเข้ามาทีหลัง (เหมือน load_profiles.csv) —
                    # ต่างจาก has_amr ตรงที่ไม่ทราบ (คอลัมน์ว่าง/ไม่มีคอลัมน์) ต้องเป็น None
                    # ไม่ใช่ False เพราะ "ไม่ทราบ" กับ "ไม่ติด Solar แน่ๆ" มีความหมายต่างกัน
                    has_solar=_to_optional_bool(row.get("has_solar", "")),
                )
            )
    return customers


_LOAD_PROFILE_FIELDNAMES = [
    "business_type_code",
    "rate_code",
    "billing_method",
    "demand_p_kw",
    "demand_op_kw",
    "demand_h_kw",
    "energy_p_kwh",
    "energy_op_kwh",
    "energy_h_kwh",
    "contract_kva_ref",
    "sample_size",
    "notes",
    "has_solar",
]


def save_load_profiles(profiles: List[LoadProfile], path: Path) -> None:
    """เขียนรายการ LoadProfile กลับเป็นไฟล์ load_profiles.csv (เขียนทับทั้งไฟล์)"""

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_LOAD_PROFILE_FIELDNAMES)
        writer.writeheader()
        for p in profiles:
            writer.writerow(
                {
                    "business_type_code": p.business_type_code,
                    "rate_code": p.rate_code,
                    "billing_method": p.billing_method,
                    "demand_p_kw": p.demand_kw["P"],
                    "demand_op_kw": p.demand_kw["OP"],
                    "demand_h_kw": p.demand_kw["H"],
                    "energy_p_kwh": p.energy_kwh["P"],
                    "energy_op_kwh": p.energy_kwh["OP"],
                    "energy_h_kwh": p.energy_kwh["H"],
                    "contract_kva_ref": "" if p.contract_kva_ref is None else p.contract_kva_ref,
                    "sample_size": p.sample_size,
                    "notes": p.notes,
                    "has_solar": "true" if p.has_solar else "false",
                }
            )


def upsert_load_profile(profiles: List[LoadProfile], new_profile: LoadProfile) -> List[LoadProfile]:
    """แทนที่โปรไฟล์ที่มี key (business_type_code, rate_code) ตรงกัน ด้วยโปรไฟล์ใหม่
    หรือเพิ่มต่อท้ายถ้ายังไม่มีคู่นี้อยู่ (คืน list ใหม่ ไม่แก้ของเดิม)
    """

    result = [p for p in profiles if p.key() != new_profile.key()]
    result.append(new_profile)
    return result


@dataclass
class ReferenceData:
    business_types: Dict[str, BusinessType]
    rate_schedules: Dict[str, RateSchedule]
    load_profiles: List[LoadProfile]
    load_curves: List[LoadCurve]
    customers: List[Customer]


def load_reference_data(data_dir: Optional[Path] = None) -> ReferenceData:
    """โหลดตารางอ้างอิงทั้งหมด (business_types, rate_schedules, load_profiles, customers)

    Parameters
    ----------
    data_dir:
        โฟลเดอร์ที่เก็บไฟล์ business_types.csv / rate_schedules.csv / load_profiles.csv /
        customers.csv ถ้าไม่ระบุ จะใช้ data/reference/ ที่ root ของ repo นี้

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
        rate_schedules=_load_rate_schedules(data_dir / "rate_schedules.csv"),
        load_profiles=_load_load_profiles(data_dir / "load_profiles.csv"),
        load_curves=_load_load_curves(data_dir / "load_curves.csv"),
        customers=list(customers_by_account.values()),
    )


_IMPORT_LOG_FIELDNAMES = ["imported_at", "business_type_code", "rate_code", "company_name", "account_no", "has_solar"]


def _migrate_import_log_header_if_needed(path: Path) -> None:
    """ถ้าไฟล์เดิมมี header แบบเก่า (คอลัมน์ไม่ตรงกับ _IMPORT_LOG_FIELDNAMES ปัจจุบัน — เช่น
    ไฟล์ที่สร้างไว้ก่อนเพิ่มคอลัมน์ has_solar) ให้ย้ายข้อมูลเดิมทั้งหมดมาเขียนใหม่ด้วย header
    ปัจจุบัน (เติมคอลัมน์ใหม่ที่ขาดเป็นค่าว่าง) ก่อนจะ append แถวใหม่ — กันไม่ให้ได้ไฟล์ CSV ที่
    แต่ละแถวมีจำนวนคอลัมน์ไม่เท่ากัน (ragged rows: แถวใหม่มีคอลัมน์เกินกว่า header เก่าประกาศไว้)
    ซึ่งทำให้อ่านกลับมาพัง (append_import_log_local เดิมเช็กแค่ "ไฟล์มีอยู่แล้วหรือยัง" ก่อนเขียน
    header ไม่เคยเช็กว่า header ที่มีอยู่ตรงกับ schema ปัจจุบันไหม)"""

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == _IMPORT_LOG_FIELDNAMES:
            return  # header ตรงกับปัจจุบันอยู่แล้ว ไม่ต้องทำอะไร
        rows = list(reader)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_IMPORT_LOG_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) or "" for k in _IMPORT_LOG_FIELDNAMES})


def append_import_log_local(entry: dict, path: Path) -> None:
    """บันทึก 1 แถวประวัติการนำเข้า AMR จริง (มีชื่อบริษัท/เลขบัญชีจริง) ต่อท้ายไฟล์
    import_log_local.csv — ไฟล์นี้อยู่ใน .gitignore แล้ว (ห้าม commit เด็ดขาด) ใช้ดูในเครื่อง
    ตัวเองเท่านั้นว่า "ทำอะไรไปแล้วบ้าง มีข้อมูลของใครบ้าง" (หลักการเดียวกับ
    customers_local.csv) — สร้างไฟล์ใหม่พร้อม header ถ้ายังไม่มี ไม่งั้น append ต่อท้าย (ย้าย
    header เก่าให้ตรงกับ schema ปัจจุบันก่อนเสมอ ถ้าจำเป็น — ดู _migrate_import_log_header_if_needed)
    """

    file_exists = path.exists()
    if file_exists:
        _migrate_import_log_header_if_needed(path)

    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_IMPORT_LOG_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: entry.get(k, "") for k in _IMPORT_LOG_FIELDNAMES})


def load_import_log_local(path: Path) -> List[dict]:
    """อ่านประวัติการนำเข้า AMR จริงทั้งหมด (ไฟล์นี้ไม่บังคับต้องมี — คืน list ว่างถ้ายังไม่มี)

    ถ้าไฟล์มีแถวที่ "ยาวเกินกว่า header" (ragged row — เช่นไฟล์เก่าที่เขียนก่อนมีการ migrate
    header ให้ตรงกับ schema ปัจจุบัน) csv.DictReader จะยัดค่าส่วนเกินไว้ใต้คีย์ None (restkey)
    ซึ่งถ้าปล่อยผ่านไปตรงๆ จะทำให้ jsonify() ที่ web/app.py พังตอน sort คีย์แบบผสม
    (เทียบ None กับ str ไม่ได้) จึงตัดคีย์ None ทิ้งตรงนี้ก่อนคืนค่า"""

    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: v for k, v in row.items() if k is not None} for row in csv.DictReader(f)]


# ── เส้นโค้งรายชั่วโมงของ "แต่ละไซต์/บัญชี" แยกต่างหากจากค่าเฉลี่ยรวมใน load_curves.csv ──
# ไฟล์นี้มีชื่อบริษัท/เลขบัญชีจริงอยู่ (หลักการเดียวกับ import_log_local.csv) จึงต้องอยู่ใน
# .gitignore เท่านั้น ห้าม commit เด็ดขาด — ใช้ตอนกดดูกราฟของบริษัท/ไซต์ใดไซต์หนึ่งโดยเฉพาะใน
# หน้า Admin (ต่างจาก load_curves.csv ซึ่งเป็นค่าเฉลี่ยรวมของทุกไซต์แบบ anonymized แล้ว)
# บันทึกเฉพาะตอนนำเข้าแบบอัตโนมัติ (import_amr_auto) เท่านั้น เพราะโหมดกรอกเอง
# (import_amr_for_business) ไม่เคยทราบชื่อบริษัทจริงเลย (เหมือนหลักการของ import_log_local.csv)

_SITE_CURVE_FIELDNAMES = [
    "company_name",
    "account_no",
    "business_type_code",
    "rate_code",
    "has_solar",
    "day_type",
    "contract_kva_ref",
    "sample_size",
    "notes",
] + _CURVE_HOUR_FIELDNAMES


def append_site_curve_local(company_name: str, account_no: str, curve: LoadCurve, path: Path) -> None:
    """บันทึกเส้นโค้งรายชั่วโมงของไซต์หนึ่งราย (มีชื่อบริษัท/เลขบัญชีจริง) ต่อท้ายไฟล์
    site_curves_local.csv — ถ้าเคยนำเข้าเลขบัญชีนี้มาก่อนแล้ว แถวเก่าจะไม่ถูกลบ (ไฟล์นี้เป็นแค่
    ประวัติ append-only เหมือน import_log_local.csv ไม่ใช่ตาราง upsert) ผู้เรียกที่อ่านกลับมา
    (load_site_curves_local) จะใช้แถวล่าสุดของแต่ละ account_no เสมอ"""

    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_SITE_CURVE_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for day_type in DAY_TYPES:
            if day_type not in curve.hours:
                continue
            row = {
                "company_name": company_name,
                "account_no": account_no,
                "business_type_code": curve.business_type_code,
                "rate_code": curve.rate_code,
                "has_solar": "true" if curve.has_solar else "false",
                "day_type": day_type,
                "contract_kva_ref": "" if curve.contract_kva_ref is None else curve.contract_kva_ref,
                "sample_size": curve.sample_size,
                "notes": curve.notes,
            }
            for h, val in enumerate(curve.hours[day_type]):
                row[f"h{h:02d}"] = "" if val is None else val
            writer.writerow(row)


def load_site_curves_local(path: Path) -> List[dict]:
    """อ่านเส้นโค้งของแต่ละไซต์ทั้งหมด จัดกลุ่มกลับเป็น list ของ dict {company_name, account_no,
    business_type_code, rate_code, has_solar, sample_size, hours} หนึ่งรายการต่อ account_no —
    ถ้าเลขบัญชีเดียวกันถูกนำเข้าซ้ำหลายครั้ง (append หลายรอบ) ใช้ข้อมูลจากรอบล่าสุดเสมอ

    ไฟล์นี้ไม่บังคับต้องมี — คืน list ว่างถ้ายังไม่เคยนำเข้าแบบอัตโนมัติมาก่อนเลย (หรือไฟล์เก่า
    ก่อนฟีเจอร์นี้ ที่มีแค่ import_log_local.csv แต่ไม่มี site_curves_local.csv)"""

    if not path.exists():
        return []

    # แถวของ account_no เดียวกันจากรอบนำเข้าใหม่กว่า (อยู่ท้ายไฟล์กว่า เพราะเป็น append-only)
    # จะเขียนทับค่า metadata และชั่วโมงของ day_type เดียวกันจากรอบเก่าไปเรื่อยๆ ผลลัพธ์สุดท้าย
    # คือข้อมูลจากรอบล่าสุดเสมอ โดยไม่ต้องเรียงลำดับ/กรองเองเพิ่ม
    grouped: Dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            account_no = row["account_no"].strip()
            entry = grouped.setdefault(account_no, {"account_no": account_no, "hours": {}})
            entry["company_name"] = row["company_name"].strip()
            entry["business_type_code"] = row["business_type_code"].strip()
            entry["rate_code"] = row["rate_code"].strip()
            entry["has_solar"] = _to_bool(row.get("has_solar", ""))
            entry["sample_size"] = int((row.get("sample_size") or "0").strip() or 0)
            entry["hours"][row["day_type"].strip()] = [_to_float(row.get(f"h{h:02d}", "")) for h in range(24)]

    return list(grouped.values())


# ── รายการ AMR ที่นำเข้าไม่สำเร็จเพราะไม่ทราบประเภทธุรกิจ/รหัสอัตรา (รอกรอกภายหลัง) ──
# ไฟล์นี้มีชื่อบริษัท/เลขบัญชีจริงอยู่ (หลักการเดียวกับ import_log_local.csv) จึงต้องอยู่ใน
# .gitignore เท่านั้น ห้าม commit เด็ดขาด — ใช้ในหน้า Admin ส่วน "รอทราบอัตรา" เพื่อดูว่าเลขบัญชี
# ไหนยังไม่มีประเภทธุรกิจ/อัตราให้ไปถามเพิ่ม แล้วกลับมากรอกย้อนหลังได้ทีหลัง (ไฟล์ AMR ที่แนบไว้
# ตอนนำเข้าไม่สำเร็จยังอยู่ใน amr_downloads/uploaded/ เสมอ ไม่ถูกลบทิ้ง เพื่อ resolve ภายหลังได้
# โดยไม่ต้องอัปโหลดไฟล์ใหม่ — เก็บ path ของไฟล์เหล่านั้นไว้ในคอลัมน์ file_paths คั่นด้วย "|")

_PENDING_AMR_FIELDNAMES = [
    "pending_id",
    "created_at",
    "account_no",
    "company_name",
    "meter_no",
    "file_paths",
    "contract_kva",
    "has_solar",
    "source_label",
]


def append_pending_amr_local(entry: dict, path: Path) -> None:
    """บันทึก 1 รายการ AMR ที่รอทราบประเภทธุรกิจ/รหัสอัตรา ต่อท้ายไฟล์ pending_amr_local.csv
    (entry ต้องมี pending_id ที่ผู้เรียกสร้างเอง — ใช้อ้างอิงตอนแก้ไข/ลบภายหลัง)"""

    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PENDING_AMR_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: entry.get(k, "") for k in _PENDING_AMR_FIELDNAMES})


def load_pending_amr_local(path: Path) -> List[dict]:
    """อ่านรายการ AMR ที่รอทราบประเภทธุรกิจ/รหัสอัตราทั้งหมด (ไฟล์นี้ไม่บังคับต้องมี — คืน list
    ว่างถ้ายังไม่เคยมีการนำเข้าไม่สำเร็จแบบนี้เลย)"""

    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: v for k, v in row.items() if k is not None} for row in csv.DictReader(f)]


def remove_pending_amr_local(pending_id: str, path: Path) -> bool:
    """ลบรายการที่ pending_id ตรงกันออกจากไฟล์ (ใช้ตอน resolve สำเร็จแล้ว หรือผู้ใช้กดลบทิ้งเอง)
    คืน True ถ้าลบจริง (เจอ id นั้น), False ถ้าไม่เจอ — เขียนไฟล์ใหม่ทั้งไฟล์โดยไม่มีแถวนั้น
    (ไฟล์นี้เล็กมาก ไม่ต้องกังวลเรื่องประสิทธิภาพการ rewrite ทั้งไฟล์)"""

    if not path.exists():
        return False
    rows = load_pending_amr_local(path)
    remaining = [r for r in rows if r.get("pending_id") != pending_id]
    if len(remaining) == len(rows):
        return False
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PENDING_AMR_FIELDNAMES)
        writer.writeheader()
        for row in remaining:
            writer.writerow({k: row.get(k, "") for k in _PENDING_AMR_FIELDNAMES})
    return True
