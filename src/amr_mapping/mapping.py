"""ตรรกะหลัก: จับคู่ ธุรกิจ -> อัตรา -> โปรไฟล์ P/OP/H

ลำดับความสำคัญของการจับคู่ (จากแม่นยำสุดไปหาประมาณการสุด):
    1. EXACT           ตรงทั้งประเภทธุรกิจ และประเภทอัตรา
    2. BUSINESS_ONLY   ตรงประเภทธุรกิจ แต่ไม่ตรงอัตรา (หรือไม่ทราบอัตรา)
    3. DIVISION_ONLY   ไม่มีโปรไฟล์ของธุรกิจนี้ตรงๆ แต่มีโปรไฟล์ของธุรกิจ "อื่น" ใน TSIC
                       division เดียวกัน (ต้องทราบ division ของทั้งสองฝั่งจาก business_types.csv)
                       — เช่น ยังไม่มีโปรไฟล์ AMR จริงของธุรกิจนี้ แต่มีของธุรกิจอื่นในกลุ่ม
                       อุตสาหกรรมเดียวกัน (เช่น การผลิตกระดาษ) ก็ยังดีกว่าตกไปที่ DEFAULT เปล่าๆ
    4. RATE_ONLY       ไม่ทราบ/ไม่ตรงประเภทธุรกิจ แต่ตรงประเภทอัตรา
    5. DEFAULT         ไม่พบข้อมูลที่ตรงกันเลย ใช้ค่ากลาง (business_type_code == "DEFAULT")

เมื่อจับคู่โปรไฟล์ได้แล้ว จะปรับสเกลตามขนาดสัญญา (KVA) ของลูกค้าเทียบกับ
KVA อ้างอิงของโปรไฟล์ (ถ้าทราบทั้งคู่) เพื่อไม่ให้ยกค่าดิบมาใช้ตรงๆ
โดยไม่คำนึงถึงขนาดของธุรกิจจริง
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .loader import ReferenceData
from .models import BusinessType, Customer, ForecastResult, LoadCurve, LoadProfile, MatchLevel, MatchResult, PERIODS

DEFAULT_BUSINESS_CODE = "DEFAULT"
DEFAULT_RATE_CODE = "DEFAULT"


def find_load_profile(
    profiles: Iterable[LoadProfile],
    business_type_code: Optional[str] = None,
    rate_code: Optional[str] = None,
    business_types: Optional[Dict[str, BusinessType]] = None,
) -> MatchResult:
    """จับคู่โปรไฟล์ที่เหมาะสมที่สุดตามลำดับความสำคัญ (ดู docstring ของโมดูล)

    business_types (ถ้าระบุ) ใช้สำหรับชั้น DIVISION_ONLY เท่านั้น — เป็น dict เดียวกับ
    ReferenceData.business_types (code -> BusinessType) เพื่อดู section_code/division_code
    """

    profiles = list(profiles)

    if business_type_code and rate_code:
        for p in profiles:
            if p.business_type_code == business_type_code and p.rate_code == rate_code:
                return MatchResult(p, MatchLevel.EXACT)

    if business_type_code:
        candidates = [p for p in profiles if p.business_type_code == business_type_code]
        if candidates:
            # ถ้าทราบอัตราด้วย ให้เลือกตัวที่ billing_method ตรงกันก่อน (รองลงมาจาก exact)
            if rate_code:
                preferred = [p for p in candidates if p.rate_code == rate_code]
                if preferred:
                    return MatchResult(preferred[0], MatchLevel.EXACT)
            return MatchResult(candidates[0], MatchLevel.BUSINESS_ONLY)

        # ไม่มีโปรไฟล์ของ business_type_code นี้ตรงๆ เลย — ลองหาโปรไฟล์ของธุรกิจอื่นที่อยู่ใน
        # TSIC division เดียวกัน (ต้องทราบ division_code ของทั้งเป้าหมายและผู้สมัครทุกตัว)
        if business_types:
            target_bt = business_types.get(business_type_code)
            if target_bt and target_bt.division_code:
                division_candidates = [
                    p
                    for p in profiles
                    if business_types.get(p.business_type_code) is not None
                    and business_types[p.business_type_code].division_code == target_bt.division_code
                ]
                if division_candidates:
                    if rate_code:
                        preferred = [p for p in division_candidates if p.rate_code == rate_code]
                        if preferred:
                            return MatchResult(preferred[0], MatchLevel.DIVISION_ONLY)
                    return MatchResult(division_candidates[0], MatchLevel.DIVISION_ONLY)

    if rate_code:
        candidates = [p for p in profiles if p.rate_code == rate_code]
        if candidates:
            return MatchResult(candidates[0], MatchLevel.RATE_ONLY)

    default = next(
        (p for p in profiles if p.business_type_code == DEFAULT_BUSINESS_CODE and p.rate_code == DEFAULT_RATE_CODE),
        None,
    )
    if default is not None:
        return MatchResult(default, MatchLevel.DEFAULT)

    raise LookupError(
        "ไม่พบโปรไฟล์ที่ตรงกัน และไม่มีค่า DEFAULT ใน load_profiles.csv "
        "(ต้องมีแถวที่ business_type_code=DEFAULT, rate_code=DEFAULT เป็นอย่างน้อย)"
    )


def find_load_curve(curves: Iterable[LoadCurve], business_type_code: str, rate_code: str) -> Optional[LoadCurve]:
    """หาเส้นโค้งรายชั่วโมงของ (business_type_code, rate_code) คู่หนึ่งแบบ exact เท่านั้น

    ไม่ต้องทำ fallback tier แบบ find_load_profile เพราะฟังก์ชันนี้ถูกเรียกด้วยคู่ค่าที่
    find_load_profile จับคู่ (แก้ fallback) ให้แล้วเสมอ (ดู web/app.py) — คืน None ถ้ายังไม่มี
    ข้อมูลเส้นโค้งของคู่นี้เลย (เช่น ยังไม่เคยนำเข้า AMR จริงที่มีข้อมูลราย 15 นาทีมาก่อน)
    """

    return next(
        (c for c in curves if c.business_type_code == business_type_code and c.rate_code == rate_code),
        None,
    )


def estimate_customer_load(customer: Customer, reference: ReferenceData) -> ForecastResult:
    """พยากรณ์โปรไฟล์ P/OP/H ของลูกค้าที่ไม่มีข้อมูล AMR ของตัวเอง

    ขั้นตอน:
        1. จับคู่โปรไฟล์อ้างอิงที่ใกล้เคียงที่สุด (ดู find_load_profile)
        2. ปรับสเกลตาม contract_kva ของลูกค้า เทียบกับ contract_kva_ref ของโปรไฟล์
    """

    if customer.has_amr:
        raise ValueError(
            f"ลูกค้า {customer.account_no} มีข้อมูล AMR ของตัวเองอยู่แล้ว "
            "ไม่จำเป็นต้องพยากรณ์จากโปรไฟล์อ้างอิง"
        )

    match = find_load_profile(
        reference.load_profiles,
        business_type_code=customer.business_type_code,
        rate_code=customer.rate_code,
        business_types=reference.business_types,
    )
    profile = match.profile
    warnings: List[str] = []

    scale_factor = 1.0
    if customer.contract_kva and profile.contract_kva_ref:
        scale_factor = customer.contract_kva / profile.contract_kva_ref
    elif customer.contract_kva and not profile.contract_kva_ref:
        warnings.append(
            "โปรไฟล์อ้างอิงไม่มีค่า contract_kva_ref จึงไม่สามารถปรับสเกลตามขนาดสัญญาได้ "
            "(ใช้ค่าดิบของโปรไฟล์อ้างอิงตรงๆ)"
        )
    elif not customer.contract_kva:
        warnings.append("ไม่ทราบ contract_kva ของลูกค้า จึงไม่สามารถปรับสเกลตามขนาดสัญญาได้")

    if match.level != MatchLevel.EXACT:
        warnings.append(f"ใช้การจับคู่แบบ {match.level.value} (ไม่ใช่ exact match) ผลลัพธ์เป็นเพียงค่าประมาณ")

    demand_kw = {p: round(profile.demand_kw[p] * scale_factor, 2) for p in PERIODS}
    energy_kwh = {p: round(profile.energy_kwh[p] * scale_factor, 2) for p in PERIODS}

    return ForecastResult(
        customer=customer,
        matched_profile=profile,
        match_level=match.level,
        scale_factor=round(scale_factor, 4),
        demand_kw=demand_kw,
        energy_kwh=energy_kwh,
        warnings=warnings,
    )
