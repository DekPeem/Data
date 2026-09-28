import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.demand_response import simulate_midday_stoppage


# รูปทรงกราฟง่ายๆ (คงที่ 1.0 kW ทุกชั่วโมง) — ให้ scale factor คำนวณตรงไปตรงมา ตรวจสอบเลขได้ง่าย
FLAT_SHAPE = [1.0] * 24


def test_simulate_baseline_curve_scaled_to_match_input_energy():
    """baseline_curve (ก่อนหยุด) ต้องถูกสเกลให้ผลรวมพลังงานในคาบ Peak (ชม. 9-21, 13 ชม.) ตรงกับ
    energy_kwh["P"] ที่กรอกมาเป๊ะ — รูปทรงคงที่ 1.0 ทุก ชม. x scale = 130/13 = 10.0 kW ต่อ ชม."""

    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=FLAT_SHAPE,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=0,
    )

    assert result.baseline_curve[9] == pytest.approx(10.0)
    assert result.baseline_curve[21] == pytest.approx(10.0)
    # ชม. นอกคาบ Peak สเกลด้วย energy_kwh["OP"] แทน (55 / 11 ชม. off-peak = 5.0)
    assert result.baseline_curve[0] == pytest.approx(5.0)
    assert result.baseline_curve[22] == pytest.approx(5.0)


def test_simulate_zero_drop_percent_leaves_everything_unchanged():
    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=FLAT_SHAPE,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=0,
    )

    assert result.energy_kwh["P"] == pytest.approx(130, rel=1e-3)
    assert result.energy_kwh["OP"] == pytest.approx(55, rel=1e-3)
    assert result.energy_kwh["H"] == pytest.approx(20, rel=1e-3)
    assert result.reduction_ratio == pytest.approx(1.0)


def test_simulate_full_hour_stoppage_reduces_energy_by_expected_amount():
    """หยุด 100% เต็ม 1 ชม. (12:00-13:00) จากกราฟคงที่ 10 kW/ชม. ในคาบ Peak (13 ชม. รวม 130 kWh)
    ต้องเหลือ P = 120 kWh (ลด 1 ชม. เต็ม) และสัดส่วนที่ลด = 120/130"""

    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=FLAT_SHAPE,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=100,
    )

    assert result.energy_kwh["P"] == pytest.approx(120, rel=1e-3)
    assert result.adjusted_curve[12] == pytest.approx(0.0)
    assert result.energy_saved_kwh["P"] == pytest.approx(10, rel=1e-3)


def test_simulate_partial_drop_percent_reduces_proportionally():
    """หยุด 30% เต็ม 1 ชม. — ชม. 12:00 ต้องลดจาก 10 kW เหลือ 7 kW (ลด 30%)"""

    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=FLAT_SHAPE,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=30,
    )

    assert result.adjusted_curve[12] == pytest.approx(7.0)
    assert result.energy_kwh["P"] == pytest.approx(127, rel=1e-3)  # 130 - 3


def test_simulate_fractional_hour_stoppage_window():
    """ช่วงหยุด 12:30-13:00 (ครึ่ง ชม.) ลด 100% — ต้องลดแค่ครึ่งเดียวของค่าชั่วโมงนั้น
    (10 kW x 0.5 overlap x 100% = ลด 5 kW เหลือ 5 kW)"""

    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=FLAT_SHAPE,
        stop_start_hour=12.5,
        stop_end_hour=13,
        drop_percent=100,
    )

    assert result.adjusted_curve[12] == pytest.approx(5.0)


def test_simulate_applies_same_reduction_ratio_to_op_and_h():
    """OP และ H ต้องถูกลดด้วยสัดส่วนเดียวกับที่ P ลดลง (ไม่ใช่คำนวณจากกราฟ OP/H โดยตรง เพราะช่วง
    หยุดเที่ยงไม่ได้แตะคาบนั้นเลย) — ทดสอบด้วยสัดส่วนที่คำนวณได้ชัดเจน (ลด 1 ใน 13 ของ P)"""

    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=FLAT_SHAPE,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=100,
    )

    expected_ratio = 120 / 130
    assert result.reduction_ratio == pytest.approx(expected_ratio, rel=1e-3)
    assert result.energy_kwh["OP"] == pytest.approx(55 * expected_ratio, rel=1e-3)
    assert result.energy_kwh["H"] == pytest.approx(20 * expected_ratio, rel=1e-3)
    assert result.demand_kw["OP"] == pytest.approx(5 * expected_ratio, rel=1e-3)
    assert result.demand_kw["H"] == pytest.approx(3 * expected_ratio, rel=1e-3)


def test_simulate_new_demand_p_computed_directly_from_adjusted_curve():
    """demand_kw["P"] ใหม่ ต้องเป็นค่าสูงสุดที่เหลือในกราฟหลังหักแล้วจริงๆ ไม่ใช่แค่ถ่วงสัดส่วน"""

    shape = [1.0] * 24
    shape[15] = 2.0  # จุดพีคจริงอยู่ที่ 15:00 (นอกช่วงที่หยุด)
    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 140, "OP": 55, "H": 20},
        shape_hours=shape,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=100,
    )

    # พีคใหม่ต้องยังคงอยู่ที่ 15:00 (ไม่ถูกหยุดกระทบ) ไม่ใช่ลดตามสัดส่วนแบบ OP/H
    assert result.demand_kw["P"] == pytest.approx(result.adjusted_curve[15])


def test_simulate_rejects_stop_window_outside_peak_hours():
    with pytest.raises(ValueError, match="คาบ Peak"):
        simulate_midday_stoppage(
            demand_kw={"P": 10, "OP": 5, "H": 3},
            energy_kwh={"P": 130, "OP": 55, "H": 20},
            shape_hours=FLAT_SHAPE,
            stop_start_hour=6,
            stop_end_hour=7,
            drop_percent=50,
        )


def test_simulate_rejects_start_not_before_end():
    with pytest.raises(ValueError, match="ช่วงเวลาหยุด"):
        simulate_midday_stoppage(
            demand_kw={"P": 10, "OP": 5, "H": 3},
            energy_kwh={"P": 130, "OP": 55, "H": 20},
            shape_hours=FLAT_SHAPE,
            stop_start_hour=13,
            stop_end_hour=12,
            drop_percent=50,
        )


def test_simulate_rejects_invalid_drop_percent():
    with pytest.raises(ValueError, match="เปอร์เซ็นต์"):
        simulate_midday_stoppage(
            demand_kw={"P": 10, "OP": 5, "H": 3},
            energy_kwh={"P": 130, "OP": 55, "H": 20},
            shape_hours=FLAT_SHAPE,
            stop_start_hour=12,
            stop_end_hour=13,
            drop_percent=150,
        )


def test_simulate_rejects_shape_without_24_hours():
    with pytest.raises(ValueError, match="24 ค่า"):
        simulate_midday_stoppage(
            demand_kw={"P": 10, "OP": 5, "H": 3},
            energy_kwh={"P": 130, "OP": 55, "H": 20},
            shape_hours=[1.0] * 10,
            stop_start_hour=12,
            stop_end_hour=13,
            drop_percent=50,
        )


def test_simulate_handles_missing_hours_in_shape_as_none():
    """ชั่วโมงที่ไม่มีข้อมูลรูปทรงกราฟเลย (None) ต้องคงเป็น None ทั้ง baseline/adjusted ไม่ error"""

    shape = [1.0] * 24
    shape[3] = None
    result = simulate_midday_stoppage(
        demand_kw={"P": 10, "OP": 5, "H": 3},
        energy_kwh={"P": 130, "OP": 55, "H": 20},
        shape_hours=shape,
        stop_start_hour=12,
        stop_end_hour=13,
        drop_percent=50,
    )

    assert result.baseline_curve[3] is None
    assert result.adjusted_curve[3] is None
