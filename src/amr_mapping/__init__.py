"""amr_mapping

โมดูลสำหรับจับคู่ (mapping) บริษัท/บัญชีผู้ใช้ไฟกับ "ประเภทธุรกิจ" (TSIC) ของกรมพัฒนาธุรกิจ
การค้า (DBD) — ค้นหาจากชื่อบริษัทหรือเลขทะเบียนนิติบุคคล แล้วจับคู่กับหมวดหมู่ในระบบ
"""

from .loader import (
    ReferenceData,
    load_reference_data,
    load_tsic_code_mapping,
    save_business_types,
    upsert_business_type,
)
from .models import BusinessType, Customer
from .tsic_normalize import normalize_tsic_code, normalize_tsic_code_with_audit

__all__ = [
    "BusinessType",
    "Customer",
    "ReferenceData",
    "load_reference_data",
    "load_tsic_code_mapping",
    "save_business_types",
    "upsert_business_type",
    "normalize_tsic_code",
    "normalize_tsic_code_with_audit",
]
