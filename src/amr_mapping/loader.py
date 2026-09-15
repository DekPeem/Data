"""โหลดข้อมูลอ้างอิง (reference data) จากไฟล์ CSV ใน data/reference/"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .models import BusinessType, Customer, LoadProfile, RateSchedule, PERIODS

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"


def _to_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if value == "":
        return None
    return float(value)


def _load_business_types(path: Path) -> Dict[str, BusinessType]:
    result: Dict[str, BusinessType] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            bt = BusinessType(
                code=row["code"].strip(),
                name_th=row["name_th"].strip(),
                category=row["category"].strip(),
                notes=row.get("notes", "").strip(),
            )
            result[bt.code] = bt
    return result


_BUSINESS_TYPE_FIELDNAMES = ["code", "name_th", "category", "notes"]


def save_business_types(business_types: Dict[str, BusinessType], path: Path) -> None:
    """เขียน business_types กลับเป็นไฟล์ business_types.csv (เขียนทับทั้งไฟล์)"""

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_BUSINESS_TYPE_FIELDNAMES)
        writer.writeheader()
        for bt in business_types.values():
            writer.writerow({"code": bt.code, "name_th": bt.name_th, "category": bt.category, "notes": bt.notes})


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
                )
            )
    return profiles


def _load_customers(path: Path) -> List[Customer]:
    """โหลดทะเบียนผู้ใช้ไฟตัวอย่าง (สมมติ) จาก customers.csv

    ⚠️ ไฟล์นี้มีไว้สำหรับสาธิต/ทดสอบเท่านั้น — ห้ามใส่ข้อมูลลูกค้าจริง (ชื่อ/เลขบัญชี/
    เลขมิเตอร์จริง) เพราะ repo นี้เป็น public
    """

    customers: List[Customer] = []
    if not path.exists():
        return customers
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            has_amr_raw = (row.get("has_amr") or "").strip().lower()
            customers.append(
                Customer(
                    account_no=row["account_no"].strip(),
                    name=row["name"].strip(),
                    business_type_code=(row.get("business_type_code") or "").strip() or None,
                    rate_code=(row.get("rate_code") or "").strip() or None,
                    contract_kva=_to_float(row.get("contract_kva", "")),
                    has_amr=has_amr_raw in ("1", "true", "yes"),
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
    customers: List[Customer]


def load_reference_data(data_dir: Optional[Path] = None) -> ReferenceData:
    """โหลดตารางอ้างอิงทั้งหมด (business_types, rate_schedules, load_profiles, customers)

    Parameters
    ----------
    data_dir:
        โฟลเดอร์ที่เก็บไฟล์ business_types.csv / rate_schedules.csv / load_profiles.csv /
        customers.csv ถ้าไม่ระบุ จะใช้ data/reference/ ที่ root ของ repo นี้
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    return ReferenceData(
        business_types=_load_business_types(data_dir / "business_types.csv"),
        rate_schedules=_load_rate_schedules(data_dir / "rate_schedules.csv"),
        load_profiles=_load_load_profiles(data_dir / "load_profiles.csv"),
        customers=_load_customers(data_dir / "customers.csv"),
    )
