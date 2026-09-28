"""คำนวณสถิติการกระจาย (Boxplot: min/Q1/median/Q3/max) ของกราฟรายชั่วโมงต่อประเภทธุรกิจ จากเส้น
โค้งของแต่ละไซต์จริงในเครื่องนี้ (site_curves_local.csv ผ่าน loader.load_site_curves_local) —
ต่างจาก load_curves.csv ที่เก็บแค่ค่าเฉลี่ยรวม (anonymized ไม่มีชื่อบริษัท) ไฟล์
site_curves_local.csv มีเส้นโค้งแยกของแต่ละไซต์อยู่แล้ว จึงเอามาคำนวณ quartile ต่อชั่วโมงได้จริง
ยิ่งมีไซต์เยอะ (บริษัทที่ธุรกิจประเภทเดียวกันหลายราย) ยิ่งเห็นการกระจายตัวของการใช้ไฟชัดเจนขึ้น

⚠️ ใช้ได้เฉพาะประเภทธุรกิจ+has_solar เดียวกันเป๊ะเท่านั้น (ไม่รองรับ blended/synthetic profile ที่
ถัวเฉลี่ยมาจากหลายประเภทธุรกิจ เช่นชั้น SECTION_ONLY/DIVISION_ONLY — กรณีนั้นให้ผู้เรียกใช้ fallback
ไปแสดงกราฟเส้นเฉลี่ยแบบเดิมแทน) และไฟล์ site_curves_local.csv เป็นไฟล์ local-only (.gitignore) จึง
มีแค่ในเครื่องที่เคยนำเข้า AMR แบบอัตโนมัติผ่านเว็บมาก่อนเท่านั้น — เครื่องอื่นจะได้ผลว่างเปล่าเสมอ
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

# ต้องมีอย่างน้อยกี่ไซต์ถึงจะถือว่า "มีการกระจายตัวจริง" พอวาด box ได้ (น้อยกว่านี้วาดได้แค่จุดเดียว
# ซึ่งไม่มีประโยชน์เป็น boxplot — ผู้เรียก fallback ไปวาดเส้นเฉลี่ยแบบเดิมแทนได้)
MIN_SAMPLES_FOR_BOX = 2


def _percentile(sorted_values: List[float], p: float) -> float:
    """percentile แบบ linear interpolation ระหว่างจุดข้อมูล (เหมือน numpy/Excel PERCENTILE.INC
    ค่าเริ่มต้น) — sorted_values ต้องเรียงจากน้อยไปมากแล้ว และมีอย่างน้อย 1 ค่า"""

    idx = p * (len(sorted_values) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_values[int(idx)]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo)


def _box_stats(values: List[float]) -> dict:
    values = sorted(values)
    return {
        "min": round(values[0], 2),
        "q1": round(_percentile(values, 0.25), 2),
        "median": round(_percentile(values, 0.5), 2),
        "q3": round(_percentile(values, 0.75), 2),
        "max": round(values[-1], 2),
        "n": len(values),
    }


def compute_hourly_boxplot(
    site_curves: List[dict],
    business_type_code: str,
    has_solar: Optional[bool],
    scale_factor: float = 1.0,
) -> Dict[str, List[Optional[dict]]]:
    """คืน {day_type: [24 ค่า boxplot stats หรือ None ถ้าชั่วโมงนั้นมีไซต์ข้อมูลไม่ถึง
    MIN_SAMPLES_FOR_BOX]} — คืน {} เปล่าๆ ถ้าจำนวนไซต์ที่ตรง business_type_code+has_solar รวมกัน
    ไม่ถึง MIN_SAMPLES_FOR_BOX เลยตั้งแต่แรก (ไม่มีเดย์ไทป์ไหนพอวาดได้เลย)

    site_curves มาจาก loader.load_site_curves_local() — รวมเฉพาะไซต์ที่ business_type_code ตรงเป๊ะ
    (ไม่รวม alias — ดูข้อจำกัดในหัวไฟล์) และ has_solar ตรงกัน (has_solar=None = รวมทุกไซต์ไม่ว่าจะ
    ติด Solar หรือไม่) scale_factor ใช้ปรับขนาดตัวเลขให้ตรงกับ KVA ของลูกค้าที่กำลังดู เหมือนที่
    _curve_response ฝั่ง web/app.py ทำกับเส้นค่าเฉลี่ย — คูณเข้ากับทุกสถิติ (min/q1/median/q3/max)
    เท่าๆ กัน เพราะเป็นการสเกลเชิงเส้นล้วนๆ ไม่กระทบรูปทรงการกระจายตัว"""

    matching = [
        s
        for s in site_curves
        if s.get("business_type_code") == business_type_code and (has_solar is None or s.get("has_solar") == has_solar)
    ]
    if len(matching) < MIN_SAMPLES_FOR_BOX:
        return {}

    day_types = set()
    for s in matching:
        day_types.update(s.get("hours", {}).keys())

    result: Dict[str, List[Optional[dict]]] = {}
    for day_type in day_types:
        hours_stats: List[Optional[dict]] = []
        for h in range(24):
            values = [
                s["hours"][day_type][h] * scale_factor
                for s in matching
                if day_type in s.get("hours", {}) and s["hours"][day_type][h] is not None
            ]
            hours_stats.append(_box_stats(values) if len(values) >= MIN_SAMPLES_FOR_BOX else None)
        result[day_type] = hours_stats
    return result
