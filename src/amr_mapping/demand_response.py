"""จำลองผลของการ "หยุดการผลิตชั่วคราว" (เช่น พักเที่ยง) ต่อกำลังไฟฟ้า/พลังงานที่ใช้ ในช่วงอัตรา
Peak (P) — ใช้ตอบคำถาม "ถ้าหยุดเครื่องจักรช่วง 12:00-13:00 แล้วกำลังไฟฟ้าลดลง 30% ของค่าที่ใช้อยู่
ช่วงนั้น ตัวเลข P/OP/H ใหม่จะเป็นเท่าไหร่"

หลักการคำนวณ:
    0. ⚠️ หน่วย/ช่วงเวลาของแต่ละตัวเลข (สำคัญมาก อย่าสลับกัน): demand_kw คือค่ากำลังไฟฟ้าสูงสุด
       (kW) ที่เกิดขึ้นจริงในรอบเดือน (ค่า snapshot ค่าเดียว ไม่ใช่ผลรวม) ส่วน energy_kwh คือ
       พลังงานไฟฟ้ารวมทั้งเดือน (kWh) — ตรงกับ P/OP/H ที่ใช้ทั่วทั้งระบบ (ดู pea_ingest.py:
       compute_monthly_profiles) ในขณะที่ shape_hours (LoadCurve.hours["all"]) เป็นรูปทรงกราฟ
       "1 วันโดยเฉลี่ย" หน่วย kW เช่นกัน — จะเทียบ/สเกลกับ demand_kw ได้ตรงๆ (หน่วย kW เหมือนกัน)
       แต่เทียบกับ energy_kwh ไม่ได้ตรงๆ เพราะ energy_kwh เป็นผลรวมทั้งเดือน (~20-30 วัน) ไม่ใช่
       ผลรวม 1 วัน ถ้าเอาไปสเกลกราฟ 1 วันตรงๆ จะได้ตัวเลขเพี้ยนสูงเกินจริงหลายสิบเท่า
    1. ปรับสเกลรูปทรงกราฟรายชั่วโมงที่มีอยู่แล้วในระบบ ให้ค่าสูงสุดในชั่วโมง 9-22 (คาบ Peak) ตรงกับ
       demand_kw["P"] ที่ผู้ใช้กรอกมาเป๊ะ (หน่วย kW ตรงกันอยู่แล้ว ไม่ต้องแปลง) — ได้กราฟรายชั่วโมง
       "ก่อนหยุด" (baseline_curve) ที่จุดสูงสุดตรงกับกำลังไฟฟ้าสูงสุดจริงของลูกค้า (สเกลชั่วโมงนอก
       คาบ Peak ด้วย demand_kw["OP"] แยกต่างหาก ไว้ใช้แสดงกราฟเต็มวันเฉยๆ)
    2. หักลดค่าในกราฟช่วงเวลาที่หยุด (stop_start_hour ถึง stop_end_hour) ลงตาม drop_percent —
       รองรับเวลาที่ไม่ใช่จำนวนเต็มชั่วโมง (เช่น 12:30) ด้วยสัดส่วนที่ซ้อนทับจริงในแต่ละชั่วโมง
    3. หา "สัดส่วนที่พลังงานในคาบ Peak ลดลง" จากกราฟ 1 วันเอง (ผลรวมหลังหัก / ผลรวมก่อนหัก ของ
       ชั่วโมงในคาบ Peak) — เป็นตัวเลขไร้หน่วย (สัดส่วน) จึงเอาไปคูณกับ energy_kwh["P"] จริง (หน่วย
       kWh ทั้งเดือน) ได้ตรงๆ โดยไม่ต้องรู้ว่าในเดือนนั้นมีกี่วัน แล้วใช้สัดส่วนเดียวกันนี้คูณ OP
       และ H (ทั้ง demand_kw และ energy_kwh) ตรงๆ ด้วย (ไม่คำนวณจากกราฟ เพราะช่วงหยุดเที่ยงอยู่ใน
       คาบ Peak เสมอ ไม่ได้แตะคาบ OP/H โดยตรง — ถือว่าการหยุดผลิตกระทบการใช้ไฟทั้งวันตามสัดส่วน
       เดียวกัน) ส่วน demand_kw["P"] ใหม่ หาตรงๆ จากค่าสูงสุดที่เหลือในกราฟหลังหักเลย (ไม่ใช้สัดส่วน
       เพราะจุดพีคจริงอาจไม่ได้อยู่ในช่วงที่หยุดเลยก็ได้ ดู test_simulate_new_demand_p_computed_directly_from_adjusted_curve)

⚠️ ข้อจำกัด: รองรับเฉพาะช่วงเวลาหยุดที่อยู่ในคาบ Peak (09:00-22:00) เท่านั้น เพราะเป็นช่วงที่พบบ่อย
ที่สุด (พักเที่ยง/หยุดกะกลางวัน) ถ้าช่วงหยุดคร่อมออกนอกคาบ Peak จะ raise ValueError ชัดเจน — ยังไม่
รองรับการหยุดข้ามคืน (คาบ OP) ในเวอร์ชันนี้
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# ช่วงชั่วโมงของคาบ Peak (P) ตาม pea_ingest.RATE_TO_PERIOD — วันทำการ 09:00-22:00 (ชม. 9..21)
PEAK_HOURS = list(range(9, 22))
ALL_HOURS = list(range(24))
OFF_PEAK_HOURS = [h for h in ALL_HOURS if h not in PEAK_HOURS]


@dataclass(frozen=True)
class DemandResponseResult:
    """ผลการจำลอง — baseline_curve/adjusted_curve มี 24 ค่า (ชม. 0-23, None = ไม่มีข้อมูลรูปทรง
    กราฟของชั่วโมงนั้นเลย) demand_kw/energy_kwh คือค่า P/OP/H ใหม่หลังหยุด"""

    baseline_curve: List[Optional[float]]
    adjusted_curve: List[Optional[float]]
    demand_kw: Dict[str, float]
    energy_kwh: Dict[str, float]
    energy_saved_kwh: Dict[str, float]
    reduction_ratio: float


def _hour_overlap_fraction(hour: int, start: float, end: float) -> float:
    """สัดส่วนของชั่วโมงที่ hour (เช่น hour=12 คือ 12:00-13:00) ที่ซ้อนทับกับช่วง [start, end)"""

    lo = max(hour, start)
    hi = min(hour + 1, end)
    return max(0.0, hi - lo)


def simulate_midday_stoppage(
    demand_kw: Dict[str, float],
    energy_kwh: Dict[str, float],
    shape_hours: List[Optional[float]],
    stop_start_hour: float,
    stop_end_hour: float,
    drop_percent: float,
) -> DemandResponseResult:
    """จำลองผลของการหยุดชั่วคราวในคาบ Peak (ดู docstring ของโมดูล) คืน DemandResponseResult

    raise ValueError ถ้า: shape_hours ไม่มี 24 ค่า, ช่วงเวลาหยุดไม่ถูกต้อง (เริ่ม >= สิ้นสุด หรือ
    นอกช่วง 0-24), ช่วงเวลาหยุดอยู่นอกคาบ Peak (09:00-22:00) บางส่วนหรือทั้งหมด, หรือ
    drop_percent ไม่อยู่ในช่วง 0-100"""

    if len(shape_hours) != 24:
        raise ValueError("shape_hours ต้องมี 24 ค่า (ราย ชม. 0-23)")
    if not (0 <= stop_start_hour < stop_end_hour <= 24):
        raise ValueError("ช่วงเวลาหยุดต้องอยู่ในช่วง 0-24 น. และเวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด")
    if stop_start_hour < PEAK_HOURS[0] or stop_end_hour > PEAK_HOURS[-1] + 1:
        raise ValueError("รองรับเฉพาะช่วงเวลาหยุดที่อยู่ในคาบ Peak (09:00-22:00) เท่านั้นในตอนนี้")
    if not (0 <= drop_percent <= 100):
        raise ValueError("เปอร์เซ็นต์ที่กำลังไฟลดลงต้องอยู่ระหว่าง 0-100")

    # สเกลด้วย demand_kw (kW) ไม่ใช่ energy_kwh (kWh ทั้งเดือน) — ดูข้อ 0 ใน docstring ของโมดูล
    # ว่าทำไมเทียบกับ energy_kwh ตรงๆ ไม่ได้ (หน่วย/ช่วงเวลาไม่ตรงกัน จะได้ตัวเลขเพี้ยนสูงเกินจริง)
    def scale_for(hours: List[int], target_peak_kw: float) -> Optional[float]:
        raw_max = max((shape_hours[h] or 0.0) for h in hours)
        return (target_peak_kw / raw_max) if raw_max > 0 else None

    p_scale = scale_for(PEAK_HOURS, demand_kw.get("P", 0.0))
    op_scale = scale_for(OFF_PEAK_HOURS, demand_kw.get("OP", 0.0))

    baseline_curve: List[Optional[float]] = []
    for h in ALL_HOURS:
        raw = shape_hours[h]
        if raw is None:
            baseline_curve.append(None)
            continue
        scale = p_scale if h in PEAK_HOURS else op_scale
        baseline_curve.append(round(raw * scale, 3) if scale is not None else None)

    adjusted_curve: List[Optional[float]] = []
    for h in ALL_HOURS:
        base = baseline_curve[h]
        if base is None:
            adjusted_curve.append(None)
            continue
        overlap = _hour_overlap_fraction(h, stop_start_hour, stop_end_hour)
        adjusted_curve.append(round(base - base * (drop_percent / 100.0) * overlap, 3))

    # สัดส่วนที่พลังงานในคาบ Peak ของ "กราฟ 1 วัน" ลดลง (ไร้หน่วย) — ไม่ใช่ตัวเลข kWh จริงของ
    # เดือนนั้น (ดูข้อ 3 ใน docstring) เอาสัดส่วนนี้ไปคูณกับ energy_kwh["P"] จริงที่กรอกมาแทน
    day_energy_p_before = sum((baseline_curve[h] or 0.0) for h in PEAK_HOURS)
    day_energy_p_after = sum((adjusted_curve[h] or 0.0) for h in PEAK_HOURS)
    reduction_ratio = round((day_energy_p_after / day_energy_p_before) if day_energy_p_before else 1.0, 6)

    old_energy_p = energy_kwh.get("P", 0.0)
    new_energy_p = round(old_energy_p * reduction_ratio, 2)
    new_energy_op = round(energy_kwh.get("OP", 0.0) * reduction_ratio, 2)
    new_energy_h = round(energy_kwh.get("H", 0.0) * reduction_ratio, 2)

    peak_values = [adjusted_curve[h] for h in PEAK_HOURS if adjusted_curve[h] is not None]
    new_demand_p = round(max(peak_values), 2) if peak_values else demand_kw.get("P", 0.0)
    new_demand_op = round(demand_kw.get("OP", 0.0) * reduction_ratio, 2)
    new_demand_h = round(demand_kw.get("H", 0.0) * reduction_ratio, 2)

    return DemandResponseResult(
        baseline_curve=baseline_curve,
        adjusted_curve=adjusted_curve,
        demand_kw={"P": new_demand_p, "OP": new_demand_op, "H": new_demand_h},
        energy_kwh={"P": new_energy_p, "OP": new_energy_op, "H": new_energy_h},
        energy_saved_kwh={
            "P": round(old_energy_p - new_energy_p, 2),
            "OP": round(energy_kwh.get("OP", 0.0) - new_energy_op, 2),
            "H": round(energy_kwh.get("H", 0.0) - new_energy_h, 2),
        },
        reduction_ratio=reduction_ratio,
    )
