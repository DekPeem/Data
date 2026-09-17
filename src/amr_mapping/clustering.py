"""จัดกลุ่มประเภทธุรกิจตาม "รูปแบบการใช้ไฟจริง" (load-curve shape) ด้วย k-means แบบง่าย
(ไม่ใช้ไลบรารีภายนอกเลย — โปรเจกต์นี้ไม่มี numpy/pandas/sklearn เป็น dependency อยู่แล้ว และ
ข้อมูลที่มีตอนนี้มีแค่ไม่กี่ประเภทธุรกิจ ไม่คุ้มที่จะเพิ่ม dependency หนักๆ แค่เพื่อสิ่งนี้)

ใช้แก้ปัญหา: ตอนค้นหาบริษัทจากชื่อ (ดู dbd_lookup.py) แล้วเจอ TSIC code ที่ "ไม่ตรง division
เป๊ะ" กับประเภทธุรกิจใดๆ ที่มีโปรไฟล์อ้างอิงในระบบเราเลย (ปัจจุบัน web/app.py จะปล่อยให้ผู้ใช้
เลือกเองทันทีในกรณีนี้ ไม่มีคำแนะนำอัตโนมัติให้เลย) — โมดูลนี้เพิ่มชั้นการจับคู่ที่ "ยอมรับได้
มากกว่า DEFAULT เฉยๆ" โดยหาประเภทธุรกิจที่มีข้อมูลจริงซึ่ง (1) อยู่ TSIC section เดียวกัน (2)
ถ้าไม่มีเลย ใช้ประเภทธุรกิจที่เป็นตัวแทนของกลุ่มรูปแบบการใช้ไฟที่พบบ่อยที่สุด (ศูนย์กลางของ
cluster ที่ใหญ่ที่สุด) แทน — ยังคงบอกผู้ใช้อย่างชัดเจนว่าเป็นการประมาณการหยาบๆ เสมอ

รูปแบบการใช้ไฟ (shape vector) คำนวณจากเส้นโค้งรายชั่วโมง (LoadCurve.hours["all"] — ค่าเฉลี่ย
รวมทุกวัน) normalize ให้ผลรวมเป็น 1.0 เพื่อให้เทียบ "รูปแบบ" ได้โดยไม่ติดเรื่องขนาดธุรกิจ (ธุรกิจ
เล็ก/ใหญ่ที่มีรูปแบบการใช้ไฟเหมือนกันควรอยู่กลุ่มเดียวกัน)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .loader import ReferenceData
from .models import BusinessType, LoadCurve

# จำนวน cluster เริ่มต้น — ข้อมูลตอนนี้มีน้อย (หลักหน่วยถึงหลักสิบประเภทธุรกิจ) จึงไม่ควรตั้งสูง
# เกินไป (cluster จะมีสมาชิกเฉลี่ยน้อยกว่า 1 ราย ไม่มีความหมาย) 3 กลุ่มพอเห็นความต่างเชิงรูปแบบ
# กว้างๆ ได้ (เช่น "พีคกลางวัน" / "สม่ำเสมอทั้งวัน" / "พีคกลางคืน") โดยยังมีสมาชิกพอต่อ cluster
DEFAULT_K = 3

# โครงสร้าง Section/Division ของ TSIC มาตรฐาน (อิง ISIC Rev.4 ที่ TSIC ใช้เป็นฐาน) — สำเนาเดียวกับ
# TSIC_SECTIONS ใน web/static/admin.js (ใช้เดา Section จาก Division ตอนแอดมินตรวจสอบ/บันทึก
# business_types.csv) ย้ายมาไว้ฝั่ง Python ด้วยเพราะ nearest_business_type_by_tsic ต้องใช้ตอน
# ประมวลผลผลค้นหา DBD ซึ่งมีแค่รหัส TSIC/division จริง ไม่มี section ติดมาด้วย
_TSIC_SECTIONS = [
    ("A", 1, 3), ("B", 5, 9), ("C", 10, 33), ("D", 35, 35), ("E", 36, 39),
    ("F", 41, 43), ("G", 45, 47), ("H", 49, 53), ("I", 55, 56), ("J", 58, 63),
    ("K", 64, 66), ("L", 68, 68), ("M", 69, 75), ("N", 77, 82), ("O", 84, 84),
    ("P", 85, 85), ("Q", 86, 88), ("R", 90, 93), ("S", 94, 96), ("T", 97, 98),
    ("U", 99, 99),
]


def section_for_division(division_code: Optional[str]) -> Optional[str]:
    """เดา TSIC section (ตัวอักษร A-U) จาก division code (ตัวเลข 2 หลัก) ตามโครงสร้าง TSIC
    มาตรฐาน — คืน None ถ้า division_code ไม่ใช่ตัวเลข หรือไม่อยู่ในช่วงที่กำหนดเลย"""

    if not division_code or not division_code.strip().isdigit():
        return None
    n = int(division_code.strip())
    for section, lo, hi in _TSIC_SECTIONS:
        if lo <= n <= hi:
            return section
    return None


def compute_shape_vector(hours: Sequence[Optional[float]]) -> Optional[List[float]]:
    """แปลงเส้นโค้งรายชั่วโมง (24 ค่า, มี None ได้ถ้าไม่มีข้อมูลชั่วโมงนั้น) เป็น "สัดส่วนการใช้ไฟ
    ต่อชั่วโมง" ที่ผลรวมเป็น 1.0 — คืน None ถ้าข้อมูลไม่พอ (ผลรวมเป็น 0 หรือไม่มีค่าที่ใช้ได้เลย)"""

    values = [(h if h is not None else 0.0) for h in hours]
    total = sum(values)
    if total <= 0:
        return None
    return [v / total for v in values]


def _euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _farthest_first_init(vectors: List[List[float]], k: int) -> List[List[float]]:
    """เลือกจุดเริ่มต้น k จุดแบบ "farthest-first traversal" (เลือกจุดแรกเป็นจุดแรกในลิสต์ แล้ว
    เลือกจุดถัดไปที่ไกลจากจุดที่เลือกไว้แล้วที่สุดเรื่อยๆ) แทน random init — ข้อมูลมีน้อยมาก
    (มักไม่เกินหลักสิบจุด) การ init แบบสุ่มจะให้ผลลัพธ์ไม่คงที่ระหว่างการรันแต่ละครั้งโดยไม่จำเป็น
    ส่วนวิธีนี้ deterministic (รันซ้ำได้ผลเดิมเสมอ) และกระจายจุดเริ่มต้นได้ดีพอสำหรับ k เล็กๆ"""

    centers = [vectors[0]]
    while len(centers) < k and len(centers) < len(vectors):
        best_vec, best_dist = None, -1.0
        for v in vectors:
            dist = min(_euclidean(v, c) for c in centers)
            if dist > best_dist:
                best_vec, best_dist = v, dist
        centers.append(best_vec)
    return centers


def kmeans(vectors: List[List[float]], k: int, max_iter: int = 50) -> List[int]:
    """k-means อย่างง่าย (Lloyd's algorithm) — คืน list ของ cluster id (0..k-1) ตำแหน่งเดียวกับ
    vectors ที่ส่งเข้ามา ถ้า k >= จำนวนจุด จะคืนแต่ละจุดเป็นกลุ่มของตัวเอง (ไม่มีอะไรให้จัดกลุ่ม)"""

    n = len(vectors)
    if n == 0:
        return []
    k = max(1, min(k, n))
    if k == n:
        return list(range(n))

    centers = _farthest_first_init(vectors, k)
    assignments = [0] * n

    for _ in range(max_iter):
        new_assignments = [
            min(range(len(centers)), key=lambda ci: _euclidean(v, centers[ci])) for v in vectors
        ]
        if new_assignments == assignments and _ > 0:
            break
        assignments = new_assignments

        new_centers = []
        for ci in range(len(centers)):
            members = [vectors[i] for i in range(n) if assignments[i] == ci]
            if not members:
                new_centers.append(centers[ci])  # cluster ว่าง — คงจุดศูนย์กลางเดิมไว้
                continue
            dim = len(members[0])
            new_centers.append([sum(m[d] for m in members) / len(members) for d in range(dim)])
        centers = new_centers

    return assignments


# ช่วงชั่วโมงที่ถือว่าเป็น "กลางวัน" (เวลาทำการทั่วไป) กับ "กลางคืน" — ใช้แค่ให้ label
# อ่านง่ายสำหรับคนดู ไม่ได้มีผลต่อการคำนวณ cluster จริง (นั่นดูจากรูปแบบเต็ม 24 ชม.)
_DAYTIME_HOURS = range(8, 18)  # 08:00-17:59
_NIGHT_HOURS = list(range(0, 6)) + list(range(22, 24))  # 22:00-05:59


def describe_shape(vector: Sequence[float]) -> str:
    """สรุปรูปแบบการใช้ไฟเป็นข้อความสั้นๆ อ่านง่าย จาก shape vector (24 ค่า สัดส่วนรวม 1.0) —
    ไม่ใช่ตรรกะที่มีผลต่อการจัดกลุ่ม แค่ช่วยให้คนอ่านผลลัพธ์เข้าใจว่ากลุ่มนี้ใช้ไฟตอนไหนเป็นหลัก"""

    if len(vector) != 24:
        return "ไม่ทราบรูปแบบ (ข้อมูลชั่วโมงไม่ครบ 24 ค่า)"

    daytime_share = sum(vector[h] for h in _DAYTIME_HOURS)
    night_share = sum(vector[h] for h in _NIGHT_HOURS)
    peak_hour = max(range(24), key=lambda h: vector[h])

    if daytime_share >= 0.55:
        return f"ใช้ไฟช่วงกลางวันเป็นหลัก (08:00-18:00 รวม {daytime_share*100:.0f}% ของทั้งวัน, พีคสุด {peak_hour:02d}:00)"
    if night_share >= 0.35:
        return f"ใช้ไฟช่วงกลางคืน/นอกเวลาทำการค่อนข้างสูง ({night_share*100:.0f}% ของทั้งวัน, พีคสุด {peak_hour:02d}:00)"
    return f"ใช้ไฟค่อนข้างสม่ำเสมอตลอดวัน (พีคสุด {peak_hour:02d}:00)"


@dataclass(frozen=True)
class BusinessTypeCluster:
    """ผลการจัดกลุ่ม 1 ประเภทธุรกิจ (business_type_code + rate_code คู่แรกที่เจอ — ถ้ามีหลาย
    อัตราของธุรกิจเดียวกัน ใช้แค่คู่แรกเป็นตัวแทน เพราะ rate ไม่ใช่ตัวกำหนดรูปแบบการใช้ไฟหลัก)"""

    business_type_code: str
    rate_code: str
    cluster_id: int
    shape_vector: List[float]
    shape_label: str


def cluster_business_types(reference: ReferenceData, k: int = DEFAULT_K) -> List[BusinessTypeCluster]:
    """จัดกลุ่มทุกประเภทธุรกิจที่มีเส้นโค้งรายชั่วโมงจริง (LoadCurve, day_type="all") ตามรูปแบบ
    การใช้ไฟ — ข้ามประเภทที่มีแค่ค่าประมาณ/placeholder (ไม่มี LoadCurve เพราะยังไม่เคยนำเข้า AMR
    จริง) เพราะ shape ของ placeholder เป็นแค่ค่าคาดเดา ไม่ควรเอามาปนกับข้อมูลจริงตอนจัดกลุ่ม"""

    # ธุรกิจเดียวกันอาจมีหลายอัตรา (rate_code) — ใช้คู่แรกที่เจอเป็นตัวแทนของธุรกิจนั้น (ดู
    # docstring ของ BusinessTypeCluster)
    seen_business_codes: set = set()
    representative_curves: List[LoadCurve] = []
    for curve in reference.load_curves:
        if curve.business_type_code in seen_business_codes:
            continue
        if "all" not in curve.hours:
            continue
        seen_business_codes.add(curve.business_type_code)
        representative_curves.append(curve)

    shape_by_curve: Dict[int, List[float]] = {}
    valid_curves: List[LoadCurve] = []
    for curve in representative_curves:
        shape = compute_shape_vector(curve.hours["all"])
        if shape is None:
            continue
        shape_by_curve[len(valid_curves)] = shape
        valid_curves.append(curve)

    if not valid_curves:
        return []

    vectors = [shape_by_curve[i] for i in range(len(valid_curves))]
    assignments = kmeans(vectors, k)

    return [
        BusinessTypeCluster(
            business_type_code=curve.business_type_code,
            rate_code=curve.rate_code,
            cluster_id=assignments[i],
            shape_vector=vectors[i],
            shape_label=describe_shape(vectors[i]),
        )
        for i, curve in enumerate(valid_curves)
    ]


@dataclass(frozen=True)
class NearestBusinessTypeMatch:
    """ผลการหาประเภทธุรกิจที่ "ใกล้เคียงที่สุด" ให้กับ TSIC code เป้าหมายที่ยังไม่มีโปรไฟล์
    อ้างอิงตรงๆ ในระบบ — match_basis อธิบายว่าใช้เกณฑ์อะไรจับคู่ (โปร่งใสต่อผู้ใช้เสมอ ไม่ auto
    เนียนว่าเป็นข้อมูลจริงของธุรกิจนั้น)"""

    business_type_code: str
    match_basis: str  # "same_section" หรือ "common_usage_pattern"
    explanation_th: str


def nearest_business_type_by_tsic(
    target_section_code: Optional[str],
    target_division_code: Optional[str],
    reference: ReferenceData,
    clusters: Optional[List[BusinessTypeCluster]] = None,
) -> Optional[NearestBusinessTypeMatch]:
    """หาประเภทธุรกิจที่มีโปรไฟล์อ้างอิงอยู่แล้วซึ่ง "ใกล้เคียงที่สุด" กับ TSIC section/division
    เป้าหมาย (เช่น จากผลค้นหา DBD ของบริษัทที่ยังไม่มีข้อมูล AMR ของตัวเอง) — ใช้ก่อนตกไปที่
    DEFAULT ล้วนๆ (ดู mapping.find_load_profile ชั้น DIVISION_ONLY ซึ่งต้อง division ตรงเป๊ะ
    เท่านั้น ฟังก์ชันนี้ผ่อนลงมาอีกขั้น):

    1. ถ้ามีธุรกิจที่มีโปรไฟล์จริงอยู่ section เดียวกัน (แม้ division ไม่ตรง) เลือกตัวที่ division
       ใกล้เคียงที่สุด (ตัวเลขห่างกันน้อยสุด)
    2. ถ้าไม่มีธุรกิจใน section เดียวกันเลย ใช้ตัวแทนของ cluster รูปแบบการใช้ไฟที่มีสมาชิกเยอะสุด
       (ดู cluster_business_types) เป็นค่าประมาณสุดท้ายก่อน DEFAULT — เลือกตัวที่ sample_size
       (จำนวนตัวอย่างจริงที่ใช้คำนวณค่าเฉลี่ย) สูงสุดในกลุ่มนั้น เพื่อความน่าเชื่อถือ

    คืน None ถ้าไม่มีธุรกิจใดในระบบมีโปรไฟล์จริงเลย (ควรไม่เกิดขึ้นถ้ามี DEFAULT อยู่เสมอ แต่
    ฟังก์ชันนี้ไม่ fallback ไป DEFAULT เอง — ปล่อยให้ผู้เรียกตัดสินใจ)"""

    if target_section_code is None:
        target_section_code = section_for_division(target_division_code)

    business_types = reference.business_types
    profiled_codes = {p.business_type_code for p in reference.load_profiles}

    def bt_of(code: str) -> Optional[BusinessType]:
        return business_types.get(code)

    if target_section_code:
        same_section: List[tuple] = []
        for code in profiled_codes:
            bt = bt_of(code)
            if bt and bt.section_code == target_section_code:
                same_section.append((code, bt))
        if same_section:
            if target_division_code and target_division_code.isdigit():
                target_div = int(target_division_code)

                def division_distance(item: tuple) -> float:
                    _, bt = item
                    if bt.division_code and bt.division_code.isdigit():
                        return abs(int(bt.division_code) - target_div)
                    return math.inf

                same_section.sort(key=division_distance)
            chosen_code, chosen_bt = same_section[0]
            return NearestBusinessTypeMatch(
                business_type_code=chosen_code,
                match_basis="same_section",
                explanation_th=(
                    f"ไม่พบธุรกิจที่ตรง TSIC division {target_division_code or '?'} เป๊ะ แต่พบธุรกิจ "
                    f'"{chosen_bt.name_th}" ที่อยู่ TSIC section {target_section_code} เดียวกัน '
                    "จึงใช้รูปแบบการใช้ไฟของธุรกิจนี้แทนแบบประมาณการ"
                ),
            )

    if clusters:
        counts: Dict[int, int] = {}
        for c in clusters:
            counts[c.cluster_id] = counts.get(c.cluster_id, 0) + 1
        if counts:
            largest_cluster_id = max(counts, key=lambda cid: counts[cid])
            members = [c for c in clusters if c.cluster_id == largest_cluster_id]

            def sample_size_of(c: BusinessTypeCluster) -> int:
                profile = next(
                    (
                        p
                        for p in reference.load_profiles
                        if p.business_type_code == c.business_type_code and p.rate_code == c.rate_code
                    ),
                    None,
                )
                return profile.sample_size if profile else 0

            members.sort(key=sample_size_of, reverse=True)
            best = members[0]
            bt = bt_of(best.business_type_code)
            name = bt.name_th if bt else best.business_type_code
            return NearestBusinessTypeMatch(
                business_type_code=best.business_type_code,
                match_basis="common_usage_pattern",
                explanation_th=(
                    f"ไม่พบธุรกิจใน TSIC section {target_section_code or '?'} เลย จึงใช้รูปแบบการใช้ไฟ"
                    f'ของ "{name}" ซึ่งเป็นตัวแทนของกลุ่มรูปแบบการใช้ไฟที่พบบ่อยที่สุดในระบบแทน '
                    f"({best.shape_label}) — เป็นค่าประมาณการคร่าวๆ เท่านั้น"
                ),
            )

    return None
