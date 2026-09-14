"""โครงสร้างข้อมูล (data models) ของโมดูล amr_mapping

ช่วงเวลาที่ใช้ทั่วทั้งโมดูล อิงตามระบบอัตรา TOU ของการไฟฟ้า:
    P  = Peak (ช่วงเวลาปกติ/ค่าไฟแพง)
    OP = Off-Peak (ช่วงเวลานอกเวลาปกติ/ค่าไฟถูกกว่า)
    H  = Holiday (วันหยุด)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

PERIODS = ("P", "OP", "H")


@dataclass(frozen=True)
class BusinessType:
    """ประเภทธุรกิจของผู้ใช้ไฟ (เช่น TSIC code)."""

    code: str
    name_th: str
    category: str
    notes: str = ""


@dataclass(frozen=True)
class RateSchedule:
    """ประเภทอัตราค่าไฟฟ้า."""

    code: str
    billing_method: str  # เช่น "TOU", "Normal"
    voltage_level: str
    description: str = ""


@dataclass(frozen=True)
class LoadProfile:
    """โปรไฟล์การใช้ไฟฟ้าอ้างอิง (P/OP/H) ของธุรกิจ + อัตรา คู่หนึ่ง

    ใช้เป็น "ต้นแบบ" (proxy) สำหรับผู้ใช้ไฟที่ไม่มีข้อมูล AMR ของตัวเอง
    """

    business_type_code: str
    rate_code: str
    billing_method: str
    demand_kw: Dict[str, float]     # กำลังไฟฟ้าสูงสุด {"P": .., "OP": .., "H": ..}
    energy_kwh: Dict[str, float]    # พลังงานไฟฟ้า {"P": .., "OP": .., "H": ..}
    contract_kva_ref: Optional[float] = None
    sample_size: int = 0
    notes: str = ""

    def key(self) -> tuple:
        return (self.business_type_code, self.rate_code)


class MatchLevel(str, Enum):
    """ระดับความแม่นยำของการจับคู่โปรไฟล์ (จากแม่นยำสุด -> ประมาณการสุด)."""

    EXACT = "exact_business_and_rate"
    BUSINESS_ONLY = "business_type_only"
    RATE_ONLY = "rate_only"
    DEFAULT = "default_fallback"


@dataclass(frozen=True)
class Customer:
    """ผู้ใช้ไฟที่ต้องการพยากรณ์โปรไฟล์ (กรณีไม่มี AMR)."""

    account_no: str
    name: str
    business_type_code: Optional[str] = None
    rate_code: Optional[str] = None
    contract_kva: Optional[float] = None
    has_amr: bool = False


@dataclass(frozen=True)
class MatchResult:
    profile: LoadProfile
    level: MatchLevel


@dataclass(frozen=True)
class ForecastResult:
    """ผลลัพธ์การพยากรณ์โปรไฟล์ของลูกค้ารายหนึ่ง."""

    customer: Customer
    matched_profile: LoadProfile
    match_level: MatchLevel
    scale_factor: float
    demand_kw: Dict[str, float]
    energy_kwh: Dict[str, float]
    warnings: list = field(default_factory=list)
