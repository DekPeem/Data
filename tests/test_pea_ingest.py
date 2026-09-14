import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.pea_ingest import (
    MonthlyRegisterReading,
    average_profiles,
    compute_meter_multiplier,
    compute_monthly_profiles,
)


def test_compute_meter_multiplier():
    # CT 50:5 -> 10, VT 22000:110 -> 200, รวม = 2000 (ตรงกับตัวอย่างมิเตอร์จริง)
    assert compute_meter_multiplier("50:5 A.", "22000:110 V.") == pytest.approx(2000.0)


def test_compute_monthly_profiles_diff_and_scale():
    readings = [
        MonthlyRegisterReading(
            month="07/2026",
            kwh_total_raw=100.0,
            kwh_a_raw=10.0,
            kwh_b_raw=20.0,
            kwh_c_raw=30.0,
            demand_a_raw=0.300,
            demand_b_raw=0.280,
            demand_c_raw=0.290,
        ),
        MonthlyRegisterReading(
            month="08/2026",
            kwh_total_raw=150.0,
            kwh_a_raw=15.0,  # +5
            kwh_b_raw=28.0,  # +8
            kwh_c_raw=45.0,  # +15
            demand_a_raw=0.320,
            demand_b_raw=0.300,
            demand_c_raw=0.328,
        ),
    ]

    profiles = compute_monthly_profiles(readings, multiplier=2000)
    assert len(profiles) == 1  # เดือนแรกไม่มีเดือนก่อนหน้าให้หักลบ จึงถูกข้าม

    p = profiles[0]
    assert p.month == "08/2026"
    assert p.energy_kwh == {"P": 10000.0, "OP": 16000.0, "H": 30000.0}
    assert p.demand_kw == {"P": 640.0, "OP": 600.0, "H": 656.0}


def test_average_profiles():
    readings = [
        MonthlyRegisterReading("06/2026", 0, 0, 0, 0, 0.30, 0.30, 0.30),
        MonthlyRegisterReading("07/2026", 0, 10, 10, 10, 0.30, 0.30, 0.30),
        MonthlyRegisterReading("08/2026", 0, 20, 30, 40, 0.40, 0.20, 0.10),
    ]
    profiles = compute_monthly_profiles(readings, multiplier=1)
    agg = average_profiles(profiles)
    assert agg["n_months"] == 2
    # เดือน 07: energy P=10 OP=10 H=10 ; เดือน 08: energy P=10 OP=20 H=30 -> เฉลี่ย
    assert agg["energy_kwh"] == {"P": 10.0, "OP": 15.0, "H": 20.0}
    # demand เป็นค่าที่อ่านได้ตรงๆ ของแต่ละเดือน (ไม่ใช่ผลต่าง) -> เฉลี่ยของ 0.30/0.40 และ 0.30/0.20 และ 0.30/0.10
    assert agg["demand_kw"] == pytest.approx({"P": 0.35, "OP": 0.25, "H": 0.20})


def test_average_profiles_empty_raises():
    with pytest.raises(ValueError):
        average_profiles([])
