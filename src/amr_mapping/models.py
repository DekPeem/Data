"""โครงสร้างข้อมูล (data models) ของโมดูล amr_mapping

ช่วงเวลาที่ใช้ทั่วทั้งโมดูล อิงตามระบบอัตรา TOU ของการไฟฟ้า:
    P  = Peak (ช่วงเวลาปกติ/ค่าไฟแพง)
    OP = Off-Peak (ช่วงเวลานอกเวลาปกติ/ค่าไฟถูกกว่า)
    H  = Holiday (วันหยุด)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

PERIODS = ("P", "OP", "H")

# วันในสัปดาห์ที่ใช้แยกเส้นโค้งการใช้ไฟฟ้ารายชั่วโมง — "all" คือค่าเฉลี่ยรวมทุกวัน
# (ตรงกับ amr_mapping.pea_ingest.DAY_TYPE_CODES)
DAY_TYPES = ("all", "mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class BusinessType:
    """ประเภทธุรกิจของผู้ใช้ไฟ (เช่น TSIC code)

    section_code/division_code (ถ้าทราบ) คือตำแหน่งใน "หมวดหมู่ธุรกิจ" ตามมาตรฐาน TSIC
    ของไทย (อิงตาม ISIC) แบบลำดับชั้น:
        Section  (หมวดใหญ่ เช่น "C" = การผลิต)      — 1 ตัวอักษร A-U
        Division (หมวดย่อย เช่น "17" = การผลิตกระดาษ) — 2 หลัก
    ใช้เป็นชั้นสำรองในการจับคู่โปรไฟล์ (ดู mapping.find_load_profile) เมื่อไม่มีโปรไฟล์ของ
    business_type_code นี้ตรงๆ แต่มีโปรไฟล์ของธุรกิจอื่นใน division/section เดียวกัน —
    ปล่อยว่าง (None) ได้ถ้ายังไม่ได้ตรวจสอบว่า code นี้ตรงกับ TSIC จริงแค่ไหน (โค้ดที่ scrape
    มาจากหน้า PEA เช่น "34111" ไม่ใช่รูปแบบ TSIC มาตรฐานเสมอไป — ดู notes ของแต่ละแถวใน
    business_types.csv)
    """

    code: str
    name_th: str
    category: str
    notes: str = ""
    section_code: Optional[str] = None
    section_name_th: str = ""
    division_code: Optional[str] = None
    division_name_th: str = ""


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
    has_solar: bool = False  # ติดตั้ง Solar/Net Metering แล้วหรือยัง — แยกโปรไฟล์ต่างหาก
    # จากคู่ธุรกิจ+อัตราเดียวกันที่ไม่มี เพราะรูปแบบการใช้ไฟช่วงกลางวันต่างกันมาก (ดึงจากกริด
    # น้อยลง/ผลิตเองบางส่วน) — เป็น flag ที่ต้องกรอกเอง (ดู amr_import) เพราะหน้า AMR ของ PEA
    # ไม่มีฟิลด์บอกสถานะ Solar ให้ตรวจจับอัตโนมัติได้

    def key(self) -> tuple:
        return (self.business_type_code, self.rate_code, self.has_solar)


@dataclass(frozen=True)
class LoadCurve:
    """เส้นโค้งกำลังไฟฟ้าเฉลี่ยรายชั่วโมง (kW) ของธุรกิจ + อัตรา คู่หนึ่ง แยกตามวันในสัปดาห์

    ต่างจาก LoadProfile (ยอดรวม/พีคของทั้งคาบ P/OP/H) — ตัวนี้ละเอียดระดับชั่วโมง ใช้แสดง
    กราฟเส้น "ช่วงเวลาไหนของวันใช้ไฟเยอะ/น้อย" พร้อมเลือกดูแยกตามวันในสัปดาห์ได้
    """

    business_type_code: str
    rate_code: str
    hours: Dict[str, List[Optional[float]]]  # day_type -> [ชม.0..23] (None = ไม่มีข้อมูล)
    contract_kva_ref: Optional[float] = None
    sample_size: int = 0
    notes: str = ""
    has_solar: bool = False  # ดู LoadProfile.has_solar — เหตุผลเดียวกัน

    def key(self) -> tuple:
        return (self.business_type_code, self.rate_code, self.has_solar)


class MatchLevel(str, Enum):
    """ระดับความแม่นยำของการจับคู่โปรไฟล์ (จากแม่นยำสุด -> ประมาณการสุด)."""

    EXACT = "exact_business_and_rate"
    SOLAR_MISMATCH = "exact_business_and_rate_solar_mismatch"  # ตรงธุรกิจ+อัตรา แต่สถานะ
    # Solar ที่ระบุมาไม่ตรงกับโปรไฟล์ที่มี (เช่น ลูกค้าติด Solar แต่มีข้อมูลอ้างอิงเฉพาะราย
    # ที่ไม่ติด Solar) — ยังดีกว่า fallback ไปประเภทธุรกิจอื่น
    BUSINESS_ONLY = "business_type_only"
    DIVISION_ONLY = "same_tsic_division"  # ธุรกิจไม่ตรงเป๊ะ แต่อยู่ TSIC division เดียวกัน
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
    has_solar: Optional[bool] = None  # None = ไม่ทราบ (ไม่บังคับกรอก — ดู LoadProfile.has_solar)


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
