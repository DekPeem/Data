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
    3b. SECTION_ONLY   ไม่มีโปรไฟล์ใน division เดียวกันเลย แต่มีโปรไฟล์ของธุรกิจอื่นใน TSIC
                       section (หมวดใหญ่ เช่น C=การผลิต, G=ขายส่ง/ปลีก) เดียวกัน — กว้างกว่า
                       DIVISION_ONLY แต่ยังดีกว่า RATE_ONLY/DEFAULT ที่ไม่สนใจประเภทธุรกิจเลย
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

from .clustering import BusinessTypeCluster
from .loader import ReferenceData
from .models import BusinessType, Customer, ForecastResult, LoadCurve, LoadProfile, MatchLevel, MatchResult, PERIODS

DEFAULT_BUSINESS_CODE = "DEFAULT"
DEFAULT_RATE_CODE = "DEFAULT"

# ค่า rate_code พิเศษสำหรับตอนนำเข้า AMR จริงที่รู้ประเภทธุรกิจแต่ "ตั้งใจไม่ทราบ" รหัสอัตรา
# (ต่างจาก DEFAULT_RATE_CODE ซึ่งหมายถึง "ไม่มีข้อมูลอะไรเลย ใช้ค่ากลางสุดท้าย") — โปรไฟล์ที่
# บันทึกด้วยค่านี้ยังมีประโยชน์ที่ชั้น BUSINESS_ONLY (จับคู่แค่ประเภทธุรกิจ ไม่สนอัตรา — ดู
# find_load_profile) แต่จะไม่มีวันถูกจับคู่เป็น EXACT ให้ใครเลย เพราะไม่มีอัตราจริงให้ตรงกัน
UNKNOWN_RATE_CODE = "UNKNOWN"


def _equivalent_codes(business_type_code: str, business_types: Optional[Dict[str, BusinessType]]) -> set:
    """คืนชุดรหัสธุรกิจทั้งหมดที่ถือว่า "เรื่องเดียวกัน" กับ business_type_code (ตัวเอง + คู่
    alias ทุกทิศทาง) — ใช้ยกระดับชั้น EXACT/BUSINESS_ONLY ให้ข้ามไปมาระหว่างรหัสที่เป็น alias
    กันได้ (เช่น TSIC ปัจจุบัน 86101 กับรหัสเก่า 93311 ของ "โรงพยาบาลทั่วไป") แทนที่จะตกไปชั้น
    DIVISION_ONLY ซึ่งเป็นแค่การประมาณการจากกลุ่มอุตสาหกรรมใกล้เคียง ไม่ใช่ธุรกิจเดียวกันจริงๆ

    ไม่ต้องมี business_types ก็ได้ (คืนแค่ {business_type_code} เฉยๆ — พฤติกรรมเดิมก่อนมี
    alias_of)"""

    codes = {business_type_code}
    if not business_types:
        return codes

    target_bt = business_types.get(business_type_code)
    canonical = target_bt.alias_of if target_bt and target_bt.alias_of else business_type_code
    codes.add(canonical)
    for code, bt in business_types.items():
        if code == canonical or bt.alias_of == canonical:
            codes.add(code)
    return codes


def _weighted_average_profile(
    candidates: List[LoadProfile], business_type_code: str, rate_code: Optional[str]
) -> LoadProfile:
    """ถัวเฉลี่ย demand_kw/energy_kwh/contract_kva_ref ของโปรไฟล์ผู้สมัครทั้งหมด (candidates)
    ถ่วงน้ำหนักตาม sample_size (อย่างน้อยเป็น 1 เสมอ กันโปรไฟล์ที่ไม่ทราบ sample_size ถูกลด
    น้ำหนักเหลือ 0 จนหายไปจากการเฉลี่ยทั้งที่ยังเป็นข้อมูลจริง) แทนที่จะหยิบ candidates[0]
    ตัวแรกในลิสต์เฉยๆ (พฤติกรรมเดิมของชั้น BUSINESS_ONLY/DIVISION_ONLY/RATE_ONLY) — ใช้เมื่อมี
    มากกว่า 1 ตัวเลือกเท่านั้น (ตัวเดียวคืนตัวเดิมตรงๆ ไม่สร้างโปรไฟล์สังเคราะห์ขึ้นมาเปล่าๆ)

    business_type_code/rate_code ที่ส่งมาคือรหัสที่ลูกค้าขอจริง (ใช้เป็น label ของโปรไฟล์
    สังเคราะห์ที่คืนออกไป) ไม่ใช่รหัสของ candidate ตัวใดตัวหนึ่งเจาะจง — ตัวเรียกใช้
    (find_load_profile) ต้องแนบ candidates ดิบไว้ใน MatchResult.contributing_profiles ด้วย
    เพราะ web/app.py ต้องใช้รหัสจริงของแต่ละ candidate ไปหาเส้นโค้งรายชั่วโมงมาถัวเฉลี่ยด้วย
    น้ำหนักเดียวกัน (โปรไฟล์สังเคราะห์นี้ไม่มีเส้นโค้งเป็นของตัวเอง)"""

    if len(candidates) == 1:
        return candidates[0]

    def weight(p: LoadProfile) -> float:
        return max(p.sample_size, 1)

    total_weight = sum(weight(p) for p in candidates)
    demand_kw = {
        period: round(sum(p.demand_kw[period] * weight(p) for p in candidates) / total_weight, 2)
        for period in PERIODS
    }
    energy_kwh = {
        period: round(sum(p.energy_kwh[period] * weight(p) for p in candidates) / total_weight, 2)
        for period in PERIODS
    }

    kva_candidates = [p for p in candidates if p.contract_kva_ref]
    contract_kva_ref = None
    if kva_candidates:
        kva_weight = sum(weight(p) for p in kva_candidates)
        contract_kva_ref = round(sum(p.contract_kva_ref * weight(p) for p in kva_candidates) / kva_weight, 2)

    source_labels = sorted({f"{p.business_type_code}/{p.rate_code}" for p in candidates})
    return LoadProfile(
        business_type_code=business_type_code,
        rate_code=rate_code or candidates[0].rate_code,
        billing_method=candidates[0].billing_method,
        demand_kw=demand_kw,
        energy_kwh=energy_kwh,
        contract_kva_ref=contract_kva_ref,
        sample_size=sum(p.sample_size for p in candidates),
        notes=f"ค่าเฉลี่ยถ่วงน้ำหนักจาก {len(candidates)} โปรไฟล์: {', '.join(source_labels)}",
        has_solar=candidates[0].has_solar,
    )


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


def _restrict_to_dominant_cluster(
    candidates: List[LoadProfile], clusters: List[BusinessTypeCluster]
) -> List[LoadProfile]:
    """ใช้ข้อมูล cluster รูปแบบการใช้ไฟจริง (จาก clustering.cluster_business_types) แคบ
    candidates เหลือแค่สมาชิกของ "กลุ่มรูปแบบที่พบบ่อยที่สุด" ในกลุ่ม candidates นี้ก่อนค่อยถัว
    เฉลี่ย — กันเอาธุรกิจที่ใช้ไฟคนละรูปแบบกันมาปนกัน (เช่น หมวด TSIC section เดียวกัน แต่ตัวหนึ่ง
    ใช้ไฟกลางวันเป็นหลัก อีกตัวใช้ไฟกลางคืนเป็นหลัก ถัวเฉลี่ยรวมกันตรงๆ จะได้รูปแบบที่ไม่เหมือน
    ธุรกิจไหนเลยสักตัว) ใช้กับชั้น SECTION_ONLY เท่านั้น (DIVISION_ONLY แคบพอแล้วโดยธรรมชาติ ไม่ต้อง
    กรองซ้ำ)

    คืน candidates เดิมทั้งหมดถ้า: ไม่มีข้อมูล cluster ของสมาชิกเลยสักตัว, หรือกรองแล้วไม่เหลือเลย
    (กันเคสแปลกๆ ที่ทำให้ผลลัพธ์แย่กว่าไม่กรองเลย)"""

    cluster_by_business_code = {c.business_type_code: c.cluster_id for c in clusters}
    candidate_cluster_ids = [cluster_by_business_code.get(p.business_type_code) for p in candidates]

    counts: Dict[int, int] = {}
    for cid in candidate_cluster_ids:
        if cid is not None:
            counts[cid] = counts.get(cid, 0) + 1
    if not counts:
        return candidates

    dominant_cluster_id = max(counts, key=lambda cid: counts[cid])
    filtered = [p for p, cid in zip(candidates, candidate_cluster_ids) if cid == dominant_cluster_id]
    return filtered if filtered else candidates


def find_load_profile(
    profiles: Iterable[LoadProfile],
    business_type_code: Optional[str] = None,
    rate_code: Optional[str] = None,
    business_types: Optional[Dict[str, BusinessType]] = None,
    has_solar: Optional[bool] = None,
    section_code: Optional[str] = None,
    clusters: Optional[List[BusinessTypeCluster]] = None,
) -> MatchResult:
    """จับคู่โปรไฟล์ที่เหมาะสมที่สุดตามลำดับความสำคัญ (ดู docstring ของโมดูล)

    business_types (ถ้าระบุ) ใช้ 2 อย่าง: (1) ชั้น DIVISION_ONLY/SECTION_ONLY — ดู
    section_code/division_code (2) ยกระดับชั้น EXACT/BUSINESS_ONLY ให้ข้ามไปมาระหว่างรหัสที่เป็น
    alias กันได้ (ดู BusinessType.alias_of/_equivalent_codes) เช่น business_type_code ที่ลูกค้า
    ระบุมาคือ 86101 (TSIC ปัจจุบัน) แต่โปรไฟล์จริงในระบบบันทึกไว้เป็น 93311 (รหัสเก่า alias กัน)
    จะยังจับคู่ที่ EXACT ได้เลย ไม่ต้องตกไป DIVISION_ONLY

    section_code (ถ้าระบุ) ใช้เป็น TSIC section เป้าหมายสำหรับชั้น SECTION_ONLY โดยตรง — สำหรับ
    กรณีที่รู้แค่หมวดใหญ่ (เช่น "C" การผลิต) แต่ไม่รู้ business_type_code (รหัส TSIC 5 หลัก) เลย
    ถ้าระบุ business_type_code มาด้วยและเจอใน business_types จะใช้ section_code ของ
    business_type_code นั้นแทน (แม่นยำกว่า ไม่สนใจค่านี้)

    clusters (ถ้าระบุ — ผลจาก clustering.cluster_business_types) ใช้เสริมความแม่นยำของชั้น
    SECTION_ONLY เท่านั้น: หมวดใหญ่หนึ่งมักมีธุรกิจที่ใช้ไฟคนละรูปแบบกันปนอยู่ (เช่น ใช้ไฟกลางวัน
    vs กลางคืน) ถ้าระบุ clusters มาจะแคบผู้สมัครเหลือแค่ "กลุ่มรูปแบบการใช้ไฟที่พบบ่อยที่สุด" ใน
    หมวดนั้นก่อนถัวเฉลี่ย (ดู _restrict_to_dominant_cluster) แทนที่จะเฉลี่ยรวมทุกรูปแบบปนกันแบบ
    ไม่เลือก — ไม่มีผลต่อชั้นอื่น (EXACT/BUSINESS_ONLY/DIVISION_ONLY แคบพอโดยธรรมชาติอยู่แล้ว)

    has_solar (ถ้าระบุ — True/False) ใช้กรองเฉพาะชั้น EXACT เท่านั้น ปล่อยเป็น None ถ้าไม่ทราบ
    สถานะ Solar ของลูกค้า (พฤติกรรมเดิมก่อนมีมิตินี้)
    """

    profiles = list(profiles)
    # รหัสธุรกิจที่ถือว่าเรื่องเดียวกัน (ตัวเอง + คู่ alias เช่น TSIC ปัจจุบัน/รหัสเก่า) — ใช้แทน
    # การเทียบ business_type_code ตรงๆ ในชั้น EXACT/BUSINESS_ONLY ทั้งหมดด้านล่าง คืนแค่
    # {business_type_code} เฉยๆ ถ้าไม่มี business_types หรือไม่มี alias (พฤติกรรมเดิม)
    equivalent_codes = _equivalent_codes(business_type_code, business_types) if business_type_code else set()
    target_bt = business_types.get(business_type_code) if business_types and business_type_code else None

    if business_type_code and rate_code:
        exact_candidates = [
            p for p in profiles if p.business_type_code in equivalent_codes and p.rate_code == rate_code
        ]
        if exact_candidates:
            chosen, solar_ok = _pick_by_solar(exact_candidates, has_solar)
            return MatchResult(chosen, MatchLevel.EXACT if solar_ok else MatchLevel.SOLAR_MISMATCH, [chosen])

    if business_type_code:
        candidates = [p for p in profiles if p.business_type_code in equivalent_codes]
        if candidates:
            # ถ้าทราบอัตราด้วย ให้เลือกตัวที่ billing_method ตรงกันก่อน (รองลงมาจาก exact)
            if rate_code:
                preferred = [p for p in candidates if p.rate_code == rate_code]
                if preferred:
                    return MatchResult(preferred[0], MatchLevel.EXACT, [preferred[0]])
            # ไม่ตรงอัตราเลยสักตัว — ถัวเฉลี่ยถ่วงน้ำหนักจากทุกโปรไฟล์ของธุรกิจนี้ (ทุกอัตรา/
            # สถานะ Solar) แทนการหยิบตัวแรกในลิสต์เฉยๆ (ดู _weighted_average_profile)
            averaged = _weighted_average_profile(candidates, business_type_code, rate_code)
            return MatchResult(averaged, MatchLevel.BUSINESS_ONLY, candidates)

        # ไม่มีโปรไฟล์ของ business_type_code นี้ตรงๆ เลย — ลองหาโปรไฟล์ของธุรกิจอื่นที่อยู่ใน
        # TSIC division เดียวกัน (ต้องทราบ division_code ของทั้งเป้าหมายและผู้สมัครทุกตัว)
        if business_types and target_bt and target_bt.division_code:
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
                        averaged = _weighted_average_profile(preferred, business_type_code, rate_code)
                        return MatchResult(averaged, MatchLevel.DIVISION_ONLY, preferred)
                averaged = _weighted_average_profile(division_candidates, business_type_code, rate_code)
                return MatchResult(averaged, MatchLevel.DIVISION_ONLY, division_candidates)

    # ไม่มีโปรไฟล์ตรงธุรกิจ/division เดียวกันเลย (หรือไม่ได้ระบุ business_type_code มาตั้งแต่ต้น
    # รู้แค่หมวดใหญ่) — ลองหมวดใหญ่กว่า (TSIC section เช่น C=การผลิต) แทน ก่อนตกไปที่
    # RATE_ONLY/DEFAULT ที่ไม่สนใจประเภทธุรกิจเลย — section ของ business_type_code (ถ้ารู้จัก)
    # แม่นยำกว่า section_code ที่ระบุมาตรงๆ เสมอ
    effective_section_code = (target_bt.section_code if target_bt else None) or section_code
    if effective_section_code and business_types:
        section_candidates = [
            p
            for p in profiles
            if business_types.get(p.business_type_code) is not None
            and business_types[p.business_type_code].section_code == effective_section_code
        ]
        if section_candidates and clusters:
            # หมวดใหญ่หนึ่งมักมีธุรกิจที่ใช้ไฟคนละรูปแบบกันปนอยู่ — แคบเหลือแค่กลุ่มรูปแบบที่พบ
            # บ่อยที่สุดในหมวดนี้ก่อนถัวเฉลี่ย (ดู _restrict_to_dominant_cluster)
            section_candidates = _restrict_to_dominant_cluster(section_candidates, clusters)
        if section_candidates:
            # ป้ายกำกับโปรไฟล์สังเคราะห์ที่คืนออกไป — ใช้ business_type_code จริงถ้ารู้ (แค่ไม่มี
            # โปรไฟล์ของมันเองพอดี) ไม่งั้นระบุ section แทน "DEFAULT" ตรงๆ กันสับสนว่าไม่เจอข้อมูล
            # อะไรเลย ทั้งที่จริงเจอแล้ว (แค่กว้างระดับ section ไม่ใช่ธุรกิจเป๊ะๆ)
            synthetic_label = business_type_code or f"SECTION:{effective_section_code}"
            if rate_code:
                preferred = [p for p in section_candidates if p.rate_code == rate_code]
                if preferred:
                    averaged = _weighted_average_profile(preferred, synthetic_label, rate_code)
                    return MatchResult(averaged, MatchLevel.SECTION_ONLY, preferred)
            averaged = _weighted_average_profile(section_candidates, synthetic_label, rate_code)
            return MatchResult(averaged, MatchLevel.SECTION_ONLY, section_candidates)

    if rate_code:
        candidates = [p for p in profiles if p.rate_code == rate_code]
        if candidates:
            averaged = _weighted_average_profile(candidates, business_type_code or DEFAULT_BUSINESS_CODE, rate_code)
            return MatchResult(averaged, MatchLevel.RATE_ONLY, candidates)

    default = next(
        (p for p in profiles if p.business_type_code == DEFAULT_BUSINESS_CODE and p.rate_code == DEFAULT_RATE_CODE),
        None,
    )
    if default is not None:
        return MatchResult(default, MatchLevel.DEFAULT, [default])

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


def estimate_customer_load(
    customer: Customer,
    reference: ReferenceData,
    section_code: Optional[str] = None,
    clusters: Optional[List[BusinessTypeCluster]] = None,
) -> ForecastResult:
    """พยากรณ์โปรไฟล์ P/OP/H ของลูกค้าที่ไม่มีข้อมูล AMR ของตัวเอง

    ขั้นตอน:
        1. จับคู่โปรไฟล์อ้างอิงที่ใกล้เคียงที่สุด (ดู find_load_profile)
        2. ปรับสเกลตาม contract_kva ของลูกค้า เทียบกับ contract_kva_ref ของโปรไฟล์

    section_code (ถ้าระบุ) ส่งต่อให้ find_load_profile เป็นทางเลือกสำรองระดับ SECTION_ONLY เมื่อ
    ไม่มี customer.business_type_code เลย (รู้แค่หมวดใหญ่ TSIC เช่น "C" การผลิต) — ไม่ใช่ฟิลด์ที่
    บันทึกไว้ถาวรใน Customer/customers.csv เจตนาใช้แค่ตอนพยากรณ์แบบ ad-hoc ไม่บันทึกข้อมูลเท่านั้น

    clusters (ถ้าระบุ — ผลจาก clustering.cluster_business_types) ส่งต่อให้ find_load_profile
    เสริมความแม่นยำของชั้น SECTION_ONLY (ดู docstring ของ find_load_profile)
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
        section_code=section_code,
        clusters=clusters,
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
        if len(match.contributing_profiles) > 1:
            warnings.append(
                f"ค่าที่แสดงเป็นค่าเฉลี่ยถ่วงน้ำหนักจากโปรไฟล์อ้างอิง {len(match.contributing_profiles)} รายการ "
                "(ถ่วงน้ำหนักตามจำนวนตัวอย่าง/ไฟล์ AMR ที่ใช้สร้างแต่ละโปรไฟล์)"
            )

    demand_kw = {p: round(profile.demand_kw[p] * scale_factor, 2) for p in PERIODS}
    energy_kwh = {p: round(profile.energy_kwh[p] * scale_factor, 2) for p in PERIODS}

    return ForecastResult(
        customer=customer,
        matched_profile=profile,
        match_level=match.level,
        scale_factor=round(scale_factor, 4),
        demand_kw=demand_kw,
        energy_kwh=energy_kwh,
        contributing_profiles=match.contributing_profiles,
        warnings=warnings,
    )
