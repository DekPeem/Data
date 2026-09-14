import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import Customer, MatchLevel, estimate_customer_load, load_reference_data
from amr_mapping.mapping import find_load_profile


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
