"""ตรรกะหลัก: จับคู่ ธุรกิจ -> อัตรา -> โปรไฟล์ P/OP/H

ลำดับความสำคัญของการจับคู่ (จากแม่นยำสุดไปหาประมาณการสุด):
    1. EXACT           ตรงทั้งประเภทธุรกิจ ประเภทอัตรา และสถานะ Solar (ถ้าทราบ)
    1b. SOLAR_MISMATCH ตรงประเภทธุรกิจ+อัตรา แต่ไม่มีโปรไฟล์ของสถานะ Solar ที่ตรงกับที่ระบุมา
                       (เช่น ลูกค้าติด Solar แต่มีข้อมูลอ้างอิงเฉพาะรายที่ไม่ติด Solar) — ยังดีกว่า
                       fallback ไปประเภทธุรกิจอื่นเปล่าๆ
    2. BUSINESS_ONLY   ตรงประเภทธุรกิจ แต่ไม่ตรงอัตรา (หรือไม่ทราบอัตรา)
    3. DIVISION_ONLY   ไม่มีโปรไฟล์ของธุรกิจนี้ตรงๆ แต่มีโปรไฟล์ของธุรกิจ "อื่น" ใน TSIC
                       division เดียวกัน (ต้องทราบ division ของทั้งสองฝั่งจาก business_types.csv)
                       — เช่น ยังไม่มีโปรไฟล์ AMR จริงของธุรกิจนี้ แต่มีของธุรกิจอื่นในกลุ่ม
                       อุตสาหกรรมเดียวกัน (เช่น การผลิตกระดาษ) ก็ยังดีกว่าตกไปที่ DEFAULT เปล่าๆ
    4. RATE_ONLY       ไม่ทราบ/ไม่ตรงประเภทธุรกิจ แต่ตรงประเภทอัตรา
    5. DEFAULT         ไม่พบข้อมูลที่ตรงกันเลย ใช้ค่ากลาง (business_type_code == "DEFAULT")

สถานะ Solar (has_solar) มีผลแค่ชั้น EXACT เท่านั้น — ชั้นที่ประมาณการอยู่แล้ว (BUSINESS_ONLY
เป็นต้นไป) ไม่ต้องพิจารณา Solar เพิ่ม เพราะความแม่นยำต่ำอยู่แล้ว การกรอง Solar ซ้อนเข้าไปจะยิ่ง
ลดจำนวนตัวเลือกโดยไม่ได้ช่วยอะไร ถ้าไม่ทราบสถานะ Solar ของลูกค้า (has_solar=None) จะเลือกโปรไฟล์
ที่ไม่ติด Solar ก่อนเสมอถ้ามีให้เลือก (ค่าเริ่มต้นที่พบบ่อยกว่า)

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


def _pick_by_solar(candidates: List[LoadProfile], has_solar: Optional[bool]) -> tuple:
    """เลือกโปรไฟล์ที่เหมาะกับสถานะ Solar ที่สุดจากรายการที่ตรงธุรกิจ+อัตราแล้ว (candidates
    ต้องไม่ว่าง) คืน (โปรไฟล์ที่เลือก, ตรงสถานะ Solar หรือไม่) — ใช้ตัดสิน EXACT vs SOLAR_MISMATCH

    - ทราบสถานะ Solar (has_solar ไม่ใช่ None): เลือกตัวที่ has_solar ตรงกันก่อน ถ้าไม่มีเลย
      ใช้ตัวแรกที่เจอแทน (ดีกว่าไม่มีอะไรให้ใช้เลย) แต่ต้องรายงานว่าไม่ตรง (SOLAR_MISMATCH)
    - ไม่ทราบสถานะ Solar: เลือกตัวที่ไม่ติด Solar ก่อนเสมอถ้ามี (ค่าเริ่มต้นที่พบบ่อยกว่า)
    """

    if has_solar is not None:
        solar_matches = [p for p in candidates if p.has_solar == has_solar]
        if solar_matches:
            return solar_matches[0], True
        return candidates[0], False

    non_solar = [p for p in candidates if not p.has_solar]
    return (non_solar[0] if non_solar else candidates[0]), True


def find_load_profile(
    profiles: Iterable[LoadProfile],
    business_type_code: Optional[str] = None,
    rate_code: Optional[str] = None,
    business_types: Optional[Dict[str, BusinessType]] = None,
    has_solar: Optional[bool] = None,
) -> MatchResult:
    """จับคู่โปรไฟล์ที่เหมาะสมที่สุดตามลำดับความสำคัญ (ดู docstring ของโมดูล)

    business_types (ถ้าระบุ) ใช้สำหรับชั้น DIVISION_ONLY เท่านั้น — เป็น dict เดียวกับ
    ReferenceData.business_types (code -> BusinessType) เพื่อดู section_code/division_code

    has_solar (ถ้าระบุ — True/False) ใช้กรองเฉพาะชั้น EXACT เท่านั้น ปล่อยเป็น None ถ้าไม่ทราบ
    สถานะ Solar ของลูกค้า (พฤติกรรมเดิมก่อนมีมิตินี้)
    """

    profiles = list(profiles)

    if business_type_code and rate_code:
        exact_candidates = [
            p for p in profiles if p.business_type_code == business_type_code and p.rate_code == rate_code
        ]
        if exact_candidates:
            chosen, solar_ok = _pick_by_solar(exact_candidates, has_solar)
            return MatchResult(chosen, MatchLevel.EXACT if solar_ok else MatchLevel.SOLAR_MISMATCH)

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


def find_load_curve(
    curves: Iterable[LoadCurve],
    business_type_code: str,
    rate_code: str,
    has_solar: Optional[bool] = None,
) -> Optional[LoadCurve]:
    """หาเส้นโค้งรายชั่วโมงของ (business_type_code, rate_code) คู่หนึ่ง — ไม่ต้องทำ fallback
    tier แบบ find_load_profile เพราะฟังก์ชันนี้ถูกเรียกด้วยคู่ค่าที่ find_load_profile จับคู่
    (แก้ fallback) ให้แล้วเสมอ (ดู web/app.py) — คืน None ถ้ายังไม่มีข้อมูลเส้นโค้งของคู่นี้เลย
    (เช่น ยังไม่เคยนำเข้า AMR จริงที่มีข้อมูลราย 15 นาทีมาก่อน)

    has_solar เลือกระหว่างเส้นโค้งที่ติด/ไม่ติด Solar ของคู่นี้ (ถ้ามีทั้งสองแบบ) ด้วยกติกา
    เดียวกับ find_load_profile — ทราบสถานะ: เลือกที่ตรงก่อน (ไม่มีก็ใช้ที่มีแทน) ไม่ทราบ: เลือก
    ที่ไม่ติด Solar ก่อนถ้ามี
    """

    candidates = [c for c in curves if c.business_type_code == business_type_code and c.rate_code == rate_code]
    if not candidates:
        return None

    if has_solar is not None:
        solar_matches = [c for c in candidates if c.has_solar == has_solar]
        return solar_matches[0] if solar_matches else candidates[0]

    non_solar = [c for c in candidates if not c.has_solar]
    return non_solar[0] if non_solar else candidates[0]


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
        has_solar=customer.has_solar,
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
