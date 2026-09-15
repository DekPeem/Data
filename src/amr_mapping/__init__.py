"""amr_mapping

โมดูลสำหรับโปรเจกต์ "No AMR": พยากรณ์โปรไฟล์การใช้ไฟฟ้า (P / OP / H)
ของผู้ใช้ไฟที่ไม่มีข้อมูล AMR (Automatic Meter Reading) ของตัวเอง
โดยอาศัยการจับคู่ (mapping) จาก "ประเภทธุรกิจ" และ "ประเภทอัตราค่าไฟ"
ไปยังโปรไฟล์อ้างอิงของธุรกิจกลุ่มเดียวกัน แล้วปรับสเกลตามขนาดสัญญา (KVA)
ของผู้ใช้ไฟรายนั้น
"""

from .models import (
    BusinessType,
    RateSchedule,
    LoadProfile,
    Customer,
    MatchLevel,
    MatchResult,
    ForecastResult,
)
from .loader import (
    ReferenceData,
    load_reference_data,
    save_business_types,
    save_load_profiles,
    upsert_business_type,
    upsert_load_profile,
)
from .mapping import find_load_profile, estimate_customer_load

__all__ = [
    "BusinessType",
    "RateSchedule",
    "LoadProfile",
    "Customer",
    "MatchLevel",
    "MatchResult",
    "ForecastResult",
    "ReferenceData",
    "load_reference_data",
    "save_load_profiles",
    "upsert_load_profile",
    "save_business_types",
    "upsert_business_type",
    "find_load_profile",
    "estimate_customer_load",
]
