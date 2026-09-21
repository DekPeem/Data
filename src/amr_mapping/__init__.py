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
    LoadCurve,
    DAY_TYPES,
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
    save_load_curves,
    upsert_business_type,
    upsert_load_profile,
    upsert_load_curve,
    remove_load_profile,
    remove_load_curve,
    append_import_log_local,
    load_import_log_local,
    append_site_curve_local,
    load_site_curves_local,
    append_pending_amr_local,
    load_pending_amr_local,
    remove_pending_amr_local,
)
from .mapping import find_load_profile, find_load_curve, estimate_customer_load, UNKNOWN_RATE_CODE

__all__ = [
    "BusinessType",
    "RateSchedule",
    "LoadProfile",
    "LoadCurve",
    "DAY_TYPES",
    "Customer",
    "MatchLevel",
    "MatchResult",
    "ForecastResult",
    "ReferenceData",
    "load_reference_data",
    "save_load_profiles",
    "upsert_load_profile",
    "remove_load_profile",
    "save_load_curves",
    "upsert_load_curve",
    "remove_load_curve",
    "save_business_types",
    "upsert_business_type",
    "append_import_log_local",
    "load_import_log_local",
    "append_site_curve_local",
    "load_site_curves_local",
    "append_pending_amr_local",
    "load_pending_amr_local",
    "remove_pending_amr_local",
    "find_load_profile",
    "find_load_curve",
    "estimate_customer_load",
    "UNKNOWN_RATE_CODE",
]
