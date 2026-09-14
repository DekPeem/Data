"""โหลดข้อมูลอ้างอิง (reference data) จากไฟล์ CSV ใน data/reference/"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .models import BusinessType, LoadProfile, RateSchedule, PERIODS

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


@dataclass
class ReferenceData:
    business_types: Dict[str, BusinessType]
    rate_schedules: Dict[str, RateSchedule]
    load_profiles: List[LoadProfile]


def load_reference_data(data_dir: Optional[Path] = None) -> ReferenceData:
    """โหลดตารางอ้างอิงทั้งหมด (business_types, rate_schedules, load_profiles)

    Parameters
    ----------
    data_dir:
        โฟลเดอร์ที่เก็บไฟล์ business_types.csv / rate_schedules.csv / load_profiles.csv
        ถ้าไม่ระบุ จะใช้ data/reference/ ที่ root ของ repo นี้
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    return ReferenceData(
        business_types=_load_business_types(data_dir / "business_types.csv"),
        rate_schedules=_load_rate_schedules(data_dir / "rate_schedules.csv"),
        load_profiles=_load_load_profiles(data_dir / "load_profiles.csv"),
    )
