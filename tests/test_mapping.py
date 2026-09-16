import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import Customer, MatchLevel, estimate_customer_load, load_reference_data
from amr_mapping.mapping import find_load_curve, find_load_profile
from amr_mapping.models import BusinessType, LoadCurve, LoadProfile


@pytest.fixture(scope="module")
def reference():
    return load_reference_data()


def test_exact_match(reference):
    match = find_load_profile(reference.load_profiles, business_type_code="63201", rate_code="50")
    assert match.level == MatchLevel.EXACT
    assert match.profile.business_type_code == "63201"
    assert match.profile.rate_code == "50"


def test_business_only_fallback(reference):
    # โรงพยาบาล (86101) มีเฉพาะรหัสอัตรา 50 ในตารางอ้างอิง -> ขออัตราอื่นที่ไม่มีจริง ต้อง fallback
    match = find_load_profile(reference.load_profiles, business_type_code="86101", rate_code="9999")
    assert match.level == MatchLevel.BUSINESS_ONLY
    assert match.profile.business_type_code == "86101"


def test_rate_only_fallback(reference):
    match = find_load_profile(reference.load_profiles, business_type_code=None, rate_code="3224")
    assert match.level == MatchLevel.RATE_ONLY
    assert match.profile.rate_code == "3224"


def test_default_fallback(reference):
    match = find_load_profile(reference.load_profiles, business_type_code=None, rate_code=None)
    assert match.level == MatchLevel.DEFAULT
    assert match.profile.business_type_code == "DEFAULT"


def test_scaling_by_kva(reference):
    customer = Customer(
        account_no="TEST-001",
        name="ทดสอบ",
        business_type_code="63201",
        rate_code="50",
        contract_kva=1000,  # ครึ่งหนึ่งของ contract_kva_ref (2000)
        has_amr=False,
    )
    result = estimate_customer_load(customer, reference)
    assert result.scale_factor == pytest.approx(0.5)

    # เทียบกับค่าดิบของโปรไฟล์อ้างอิงโดยตรง แทนการ hardcode ตัวเลข เพื่อไม่ให้ test
    # พังทุกครั้งที่ข้อมูลอ้างอิงถูกอัปเดตด้วยค่าเฉลี่ยจาก AMR จริงชุดใหม่
    ref_profile = next(
        p for p in reference.load_profiles if p.business_type_code == "63201" and p.rate_code == "50"
    )
    assert result.demand_kw["P"] == pytest.approx(ref_profile.demand_kw["P"] * 0.5, rel=1e-3)
    assert result.energy_kwh["P"] == pytest.approx(ref_profile.energy_kwh["P"] * 0.5, rel=1e-3)


def test_no_kva_no_scaling(reference):
    customer = Customer(
        account_no="TEST-002",
        name="ทดสอบไม่ทราบ KVA",
        business_type_code=None,
        rate_code="3224",
        contract_kva=None,
        has_amr=False,
    )
    result = estimate_customer_load(customer, reference)
    assert result.scale_factor == 1.0
    assert any("contract_kva" in w for w in result.warnings)


def test_has_amr_raises(reference):
    customer = Customer(account_no="X", name="มี AMR อยู่แล้ว", has_amr=True)
    with pytest.raises(ValueError):
        estimate_customer_load(customer, reference)


def test_find_load_profile_falls_back_to_same_tsic_division():
    """ไม่มีโปรไฟล์ของ "17012" ตรงๆ เลย แต่มีโปรไฟล์ของ "17011" ซึ่งอยู่ division "17"
    เดียวกัน (ทั้งคู่ระบุไว้ใน business_types) — ต้องได้ DIVISION_ONLY แทนที่จะตกไป DEFAULT"""

    business_types = {
        "17011": BusinessType(code="17011", name_th="ผลิตเยื่อกระดาษ", category="paper", division_code="17"),
        "17012": BusinessType(code="17012", name_th="ผลิตกระดาษแข็ง", category="paper", division_code="17"),
    }
    profiles = [
        LoadProfile(
            business_type_code="17011", rate_code="40", billing_method="TOU",
            demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1},
        ),
        LoadProfile(
            business_type_code="DEFAULT", rate_code="DEFAULT", billing_method="TOU",
            demand_kw={"P": 0, "OP": 0, "H": 0}, energy_kwh={"P": 0, "OP": 0, "H": 0},
        ),
    ]

    match = find_load_profile(profiles, business_type_code="17012", rate_code="40", business_types=business_types)
    assert match.level == MatchLevel.DIVISION_ONLY
    assert match.profile.business_type_code == "17011"


def test_find_load_profile_division_fallback_requires_business_types_dict():
    """ถ้าไม่ส่ง business_types มาเลย ต้องข้ามชั้น DIVISION_ONLY ไปตกที่ DEFAULT ตามปกติ
    (backward compatible กับโค้ดเก่าที่ยังไม่รู้จักพารามิเตอร์นี้)"""

    profiles = [
        LoadProfile(
            business_type_code="17011", rate_code="40", billing_method="TOU",
            demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1},
        ),
        LoadProfile(
            business_type_code="DEFAULT", rate_code="DEFAULT", billing_method="TOU",
            demand_kw={"P": 0, "OP": 0, "H": 0}, energy_kwh={"P": 0, "OP": 0, "H": 0},
        ),
    ]

    match = find_load_profile(profiles, business_type_code="17012", rate_code="999")
    assert match.level == MatchLevel.DEFAULT


def test_find_load_profile_division_fallback_requires_known_division_on_target():
    """ถ้า business type เป้าหมายเองไม่ทราบ division_code (ยังไม่ตรวจสอบ) ต้องข้ามชั้น
    DIVISION_ONLY ไปเลย ไม่เดาสุ่ม"""

    business_types = {
        "17011": BusinessType(code="17011", name_th="ผลิตเยื่อกระดาษ", category="paper", division_code="17"),
        "99999": BusinessType(code="99999", name_th="ยังไม่ตรวจสอบ", category="unverified"),  # ไม่มี division_code
    }
    profiles = [
        LoadProfile(
            business_type_code="17011", rate_code="40", billing_method="TOU",
            demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1},
        ),
        LoadProfile(
            business_type_code="DEFAULT", rate_code="DEFAULT", billing_method="TOU",
            demand_kw={"P": 0, "OP": 0, "H": 0}, energy_kwh={"P": 0, "OP": 0, "H": 0},
        ),
    ]

    match = find_load_profile(profiles, business_type_code="99999", rate_code="999", business_types=business_types)
    assert match.level == MatchLevel.DEFAULT


def test_find_load_curve_exact_match_only_no_fallback():
    curves = [
        LoadCurve(business_type_code="63201", rate_code="50", hours={"all": [1.0] * 24}),
        LoadCurve(business_type_code="DEFAULT", rate_code="DEFAULT", hours={"all": [0.0] * 24}),
    ]

    found = find_load_curve(curves, "63201", "50")
    assert found is not None
    assert found.hours["all"][0] == 1.0

    # ต่างจาก find_load_profile — ไม่มี fallback tier ใดๆ ทั้งสิ้น ไม่ตกไปที่ DEFAULT เอง
    assert find_load_curve(curves, "63201", "9999") is None
    assert find_load_curve(curves, "NOPE", "50") is None


# ── has_solar เป็นมิติที่เพิ่มเข้ามาทีหลัง — มีผลแค่ชั้น EXACT เท่านั้น (ดู docstring โมดูล) ──

_SOLAR_PROFILES = [
    LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 100, "OP": 100, "H": 100}, energy_kwh={"P": 100, "OP": 100, "H": 100},
        has_solar=False,
    ),
    LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 40, "OP": 100, "H": 100}, energy_kwh={"P": 40, "OP": 100, "H": 100},
        has_solar=True,
    ),
]


def test_find_load_profile_picks_matching_solar_status_when_known():
    match = find_load_profile(_SOLAR_PROFILES, business_type_code="63201", rate_code="50", has_solar=True)
    assert match.level == MatchLevel.EXACT
    assert match.profile.has_solar is True
    assert match.profile.demand_kw["P"] == 40


def test_find_load_profile_picks_non_solar_by_default_when_unknown():
    """ไม่ทราบสถานะ Solar ของลูกค้า (has_solar=None) — ต้องเลือกโปรไฟล์ที่ไม่ติด Solar ก่อนเสมอ
    ถ้ามีให้เลือก (ค่าเริ่มต้นที่พบบ่อยกว่า) ไม่ใช่สุ่มเลือกตามลำดับใน list"""

    match = find_load_profile(_SOLAR_PROFILES, business_type_code="63201", rate_code="50")
    assert match.level == MatchLevel.EXACT
    assert match.profile.has_solar is False


def test_find_load_profile_solar_mismatch_when_requested_status_unavailable():
    """ลูกค้าติด Solar แต่มีข้อมูลอ้างอิงเฉพาะรายที่ไม่ติด Solar เท่านั้น — ต้องได้
    SOLAR_MISMATCH (ยังดีกว่า fallback ไปประเภทธุรกิจอื่น) ไม่ใช่ EXACT เฉยๆ"""

    non_solar_only = [_SOLAR_PROFILES[0]]
    match = find_load_profile(non_solar_only, business_type_code="63201", rate_code="50", has_solar=True)
    assert match.level == MatchLevel.SOLAR_MISMATCH
    assert match.profile.has_solar is False


def test_find_load_curve_picks_matching_solar_status():
    curves = [
        LoadCurve(business_type_code="63201", rate_code="50", hours={"all": [10.0] * 24}, has_solar=False),
        LoadCurve(business_type_code="63201", rate_code="50", hours={"all": [4.0] * 24}, has_solar=True),
    ]

    assert find_load_curve(curves, "63201", "50", has_solar=True).hours["all"][0] == 4.0
    assert find_load_curve(curves, "63201", "50", has_solar=False).hours["all"][0] == 10.0
    # ไม่ทราบสถานะ -> เลือกที่ไม่ติด Solar ก่อน
    assert find_load_curve(curves, "63201", "50").hours["all"][0] == 10.0


def test_estimate_customer_load_passes_customer_solar_status():
    """estimate_customer_load ต้องส่ง customer.has_solar เข้า find_load_profile ด้วย ไม่ใช่
    เพิกเฉยแล้วได้โปรไฟล์ไม่ติด Solar เสมอทั้งที่ลูกค้าติด Solar จริง"""

    from amr_mapping.loader import ReferenceData

    reference = ReferenceData(
        business_types={}, rate_schedules={}, load_profiles=_SOLAR_PROFILES, load_curves=[], customers=[],
    )
    customer = Customer(
        account_no="ACC-SOLAR", name="ลูกค้าติด Solar", business_type_code="63201", rate_code="50",
        contract_kva=None, has_amr=False, has_solar=True,
    )

    result = estimate_customer_load(customer, reference)
    assert result.match_level == MatchLevel.EXACT
    assert result.matched_profile.has_solar is True
