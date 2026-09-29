import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from amr_mapping.forecast_shape import P_HOURS, TEMPLATE_WEEKDAY, build_curve, forecast_shape_png


def test_build_curve_hits_peak_exactly():
    curve = build_curve(P_HOURS, TEMPLATE_WEEKDAY, peak=650, energy_kwh=69500, days=22, drop_pct=43)
    assert max(curve.values()) == pytest.approx(650, rel=1e-6)


def test_build_curve_average_matches_energy():
    curve = build_curve(P_HOURS, TEMPLATE_WEEKDAY, peak=650, energy_kwh=69500, days=22, drop_pct=43)
    total_kwh = sum(curve.values()) * 22  # kW เฉลี่ยต่อชม. x 1 ชม. = kWh ของชม.นั้น x จำนวนวัน
    assert total_kwh == pytest.approx(69500, rel=1e-6)


def test_build_curve_applies_lunch_dip():
    """เทียบ drop_pct=0 กับ drop_pct=43 ที่ peak/energy ระดับเดียวกัน (load factor สูง ~85% กัน
    gamma ไม่สุดโต่งจนบิดรูปทรงธรรมชาติ) — ชม. 12 (เที่ยง) ต้องต่ำลงชัดเจนเมื่อเปิดรอยบุ๋ม ในขณะที่
    ค่าเฉลี่ยรวมยังคงตรงกับพลังงานที่กำหนดเท่าเดิม (แค่กระจายจากเที่ยงไปชั่วโมงอื่นแทน)"""

    peak, days = 650, 22
    energy = peak * 0.85 * days * len(P_HOURS)  # load factor ~85% -> gamma ไม่สุดโต่ง
    no_dip = build_curve(P_HOURS, TEMPLATE_WEEKDAY, peak=peak, energy_kwh=energy, days=days, drop_pct=0)
    with_dip = build_curve(P_HOURS, TEMPLATE_WEEKDAY, peak=peak, energy_kwh=energy, days=days, drop_pct=43)

    assert with_dip[12] < no_dip[12]
    # การกระจายพลังงานกลับมีการ clamp ไม่ให้เกิน peak (min(peak, ...)) จึงอาจไม่ conserve พลังงาน
    # เป๊ะๆ 100% แต่ต้องใกล้เคียงมาก (ไม่ใช่แค่ตัดพลังงานตอนเที่ยงทิ้งเฉยๆ โดยไม่กระจายคืน)
    assert sum(with_dip.values()) == pytest.approx(sum(no_dip.values()), rel=1e-2)


def test_build_curve_zero_days_returns_zeros():
    curve = build_curve(P_HOURS, TEMPLATE_WEEKDAY, peak=650, energy_kwh=69500, days=0, drop_pct=43)
    assert all(v == 0.0 for v in curve.values())


def test_forecast_shape_png_requires_at_least_one_peak():
    with pytest.raises(ValueError):
        forecast_shape_png()


def test_forecast_shape_png_returns_valid_png_bytes():
    png = forecast_shape_png(peak_p=650, energy_p=69500)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG file signature


def test_forecast_shape_png_skips_segments_without_peak():
    """ไม่กรอก peak_op/peak_h เลย ต้องยังพยากรณ์ได้ปกติ (แค่ P อย่างเดียว) ไม่ error"""

    png = forecast_shape_png(peak_p=500, energy_p=50000)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
