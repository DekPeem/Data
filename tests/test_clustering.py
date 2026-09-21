import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import load_reference_data
from amr_mapping.clustering import (
    BusinessTypeCluster,
    cluster_business_types,
    compute_shape_vector,
    describe_shape,
    kmeans,
    nearest_business_type_by_tsic,
    rank_business_types_by_tsic,
    section_for_division,
)
from amr_mapping.loader import ReferenceData
from amr_mapping.models import BusinessType, LoadCurve, LoadProfile


def test_compute_shape_vector_normalizes_to_sum_one():
    hours = [10.0] * 24
    shape = compute_shape_vector(hours)
    assert shape is not None
    assert len(shape) == 24
    assert all(v == pytest.approx(1 / 24) for v in shape)
    assert sum(shape) == pytest.approx(1.0)


def test_compute_shape_vector_treats_none_as_zero():
    hours = [None] * 12 + [10.0] * 12
    shape = compute_shape_vector(hours)
    assert shape is not None
    assert shape[0] == 0.0
    assert shape[12] == pytest.approx(1 / 12)


def test_compute_shape_vector_returns_none_when_all_zero():
    assert compute_shape_vector([0.0] * 24) is None
    assert compute_shape_vector([None] * 24) is None


def test_kmeans_groups_obviously_separated_points_together():
    # 2 กลุ่มที่ห่างกันชัดเจน (ใกล้ 0 กับใกล้ 10 ในทุกมิติ) — ต้องถูกแยกเป็น 2 cluster ถูกต้อง
    low = [[0.0, 0.0], [0.1, 0.1], [0.0, 0.2]]
    high = [[10.0, 10.0], [10.1, 9.9], [9.8, 10.2]]
    vectors = low + high

    assignments = kmeans(vectors, k=2)

    assert len(assignments) == 6
    low_labels = set(assignments[:3])
    high_labels = set(assignments[3:])
    assert len(low_labels) == 1, "จุดในกลุ่มใกล้ 0 ต้องอยู่ cluster เดียวกันหมด"
    assert len(high_labels) == 1, "จุดในกลุ่มใกล้ 10 ต้องอยู่ cluster เดียวกันหมด"
    assert low_labels != high_labels, "สองกลุ่มที่ห่างกันชัดเจนต้องไม่ถูกจัดรวม cluster เดียวกัน"


def test_kmeans_handles_k_greater_than_or_equal_to_points():
    vectors = [[1.0, 2.0], [3.0, 4.0]]
    assignments = kmeans(vectors, k=5)
    assert len(assignments) == 2
    assert len(set(assignments)) == 2  # แต่ละจุดเป็นกลุ่มของตัวเอง


def test_kmeans_empty_input_returns_empty():
    assert kmeans([], k=3) == []


def test_describe_shape_labels_daytime_heavy_pattern():
    vector = [0.005] * 24
    for h in range(8, 18):
        vector[h] = 0.05
    total = sum(vector)
    vector = [v / total for v in vector]  # normalize ให้ผลรวมเป็น 1 พอดี

    label = describe_shape(vector)
    assert "กลางวัน" in label


def test_describe_shape_labels_wrong_length_as_unknown():
    assert "ไม่ทราบรูปแบบ" in describe_shape([1.0, 2.0, 3.0])


def _make_reference(business_types, load_profiles, load_curves):
    return ReferenceData(
        business_types={bt.code: bt for bt in business_types},
        rate_schedules={},
        load_profiles=load_profiles,
        load_curves=load_curves,
        customers=[],
    )


def _flat_hours(value: float):
    return {"all": [value] * 24}


def test_cluster_business_types_skips_types_without_real_curves():
    # ธุรกิจ B ไม่มี LoadCurve เลย (แค่ placeholder ใน load_profiles) — ต้องไม่ถูกจัดกลุ่ม
    bt_a = BusinessType(code="A", name_th="ธุรกิจ A", category="auto")
    bt_b = BusinessType(code="B", name_th="ธุรกิจ B (placeholder)", category="auto")
    reference = _make_reference(
        business_types=[bt_a, bt_b],
        load_profiles=[
            LoadProfile("A", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
            LoadProfile("B", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
        ],
        load_curves=[LoadCurve("A", "50", _flat_hours(5.0))],
    )

    clusters = cluster_business_types(reference, k=2)

    codes = {c.business_type_code for c in clusters}
    assert codes == {"A"}


def test_cluster_business_types_uses_first_rate_per_business_as_representative():
    bt_a = BusinessType(code="A", name_th="ธุรกิจ A", category="auto")
    reference = _make_reference(
        business_types=[bt_a],
        load_profiles=[],
        load_curves=[
            LoadCurve("A", "50", _flat_hours(5.0)),
            LoadCurve("A", "9999", _flat_hours(999.0)),  # ต้องไม่ถูกใช้ (ไม่ใช่คู่แรก)
        ],
    )

    clusters = cluster_business_types(reference, k=1)

    assert len(clusters) == 1
    assert clusters[0].rate_code == "50"


def test_nearest_business_type_by_tsic_prefers_same_section_over_cluster_fallback():
    target_section, target_division = "C", "17"
    bt_same_section = BusinessType(
        code="X", name_th="ธุรกิจใน section เดียวกัน", category="auto",
        section_code="C", division_code="19",
    )
    bt_other_section = BusinessType(
        code="Y", name_th="ธุรกิจ section อื่น", category="auto",
        section_code="G", division_code="47",
    )
    reference = _make_reference(
        business_types=[bt_same_section, bt_other_section],
        load_profiles=[
            LoadProfile("X", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
            LoadProfile("Y", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
        ],
        load_curves=[],
    )

    match = nearest_business_type_by_tsic(target_section, target_division, reference)

    assert match is not None
    assert match.business_type_code == "X"
    assert match.match_basis == "same_section"


def test_nearest_business_type_by_tsic_picks_closest_division_within_section():
    bt_near = BusinessType(code="NEAR", name_th="Division ใกล้", category="auto", section_code="C", division_code="18")
    bt_far = BusinessType(code="FAR", name_th="Division ไกล", category="auto", section_code="C", division_code="33")
    reference = _make_reference(
        business_types=[bt_near, bt_far],
        load_profiles=[
            LoadProfile("NEAR", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
            LoadProfile("FAR", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
        ],
        load_curves=[],
    )

    match = nearest_business_type_by_tsic("C", "17", reference)

    assert match is not None
    assert match.business_type_code == "NEAR"


def test_nearest_business_type_by_tsic_falls_back_to_common_cluster_when_no_section_match():
    bt_a = BusinessType(code="A", name_th="ธุรกิจ A", category="auto", section_code="G", division_code="47")
    reference = _make_reference(
        business_types=[bt_a],
        load_profiles=[LoadProfile("A", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}, sample_size=5)],
        load_curves=[LoadCurve("A", "50", _flat_hours(5.0))],
    )
    clusters = cluster_business_types(reference, k=1)

    match = nearest_business_type_by_tsic("Z", "99", reference, clusters=clusters)

    assert match is not None
    assert match.business_type_code == "A"
    assert match.match_basis == "common_usage_pattern"


def test_nearest_business_type_by_tsic_returns_none_when_nothing_available():
    reference = _make_reference(business_types=[], load_profiles=[], load_curves=[])
    assert nearest_business_type_by_tsic("C", "17", reference, clusters=[]) is None


def test_section_for_division_matches_known_ranges():
    assert section_for_division("17") == "C"  # การผลิต
    assert section_for_division("71") == "M"  # กิจกรรมทางวิชาชีพ วิทยาศาสตร์ และเทคนิค
    assert section_for_division("47") == "G"  # ขายส่ง/ขายปลีก
    assert section_for_division("01") == "A"
    assert section_for_division("99") == "U"


def test_section_for_division_returns_none_for_invalid_input():
    assert section_for_division(None) is None
    assert section_for_division("") is None
    assert section_for_division("ไม่ใช่ตัวเลข") is None
    assert section_for_division("00") is None  # ไม่อยู่ในช่วงไหนเลย (ต่ำกว่า A ที่เริ่มจาก 1)


def test_nearest_business_type_by_tsic_derives_section_from_division_when_not_given():
    # ธุรกิจ X อยู่ section C (การผลิต) — target division "20" ก็อยู่ section C เหมือนกัน แม้ไม่ได้
    # ส่ง target_section_code มาตรงๆ เลย ต้องยัง derive section จาก division แล้วจับคู่ได้
    bt_x = BusinessType(code="X", name_th="ธุรกิจ X", category="auto", section_code="C", division_code="19")
    reference = _make_reference(
        business_types=[bt_x],
        load_profiles=[LoadProfile("X", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1})],
        load_curves=[],
    )

    match = nearest_business_type_by_tsic(None, "20", reference)

    assert match is not None
    assert match.business_type_code == "X"
    assert match.match_basis == "same_section"


def test_rank_business_types_by_tsic_ranks_same_section_by_division_distance():
    bt_near = BusinessType(code="NEAR", name_th="Division ใกล้", category="auto", section_code="C", division_code="18")
    bt_far = BusinessType(code="FAR", name_th="Division ไกล", category="auto", section_code="C", division_code="33")
    reference = _make_reference(
        business_types=[bt_near, bt_far],
        load_profiles=[
            LoadProfile("NEAR", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
            LoadProfile("FAR", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}),
        ],
        load_curves=[],
    )

    ranked = rank_business_types_by_tsic("C", "17", reference, limit=3)

    assert [m.business_type_code for m in ranked] == ["NEAR", "FAR"]
    assert all(m.match_basis == "same_section" for m in ranked)


def test_rank_business_types_by_tsic_respects_limit():
    bts = [
        BusinessType(code=f"BT{i}", name_th=f"ธุรกิจ {i}", category="auto", section_code="C", division_code=str(18 + i))
        for i in range(5)
    ]
    reference = _make_reference(
        business_types=bts,
        load_profiles=[
            LoadProfile(f"BT{i}", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}) for i in range(5)
        ],
        load_curves=[],
    )

    ranked = rank_business_types_by_tsic("C", "17", reference, limit=2)

    assert len(ranked) == 2


def test_rank_business_types_by_tsic_fills_remaining_with_cluster_representatives():
    # ไม่มีธุรกิจ section เดียวกันเลย (section "Z" ไม่มีอยู่จริง) — ต้องเติมด้วยตัวแทนแต่ละ cluster
    bt_a = BusinessType(code="A", name_th="ธุรกิจ A", category="auto", section_code="G", division_code="47")
    bt_b = BusinessType(code="B", name_th="ธุรกิจ B", category="auto", section_code="I", division_code="55")
    reference = _make_reference(
        business_types=[bt_a, bt_b],
        load_profiles=[
            LoadProfile("A", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}, sample_size=5),
            LoadProfile("B", "50", "TOU", {"P": 1, "OP": 1, "H": 1}, {"P": 1, "OP": 1, "H": 1}, sample_size=3),
        ],
        load_curves=[LoadCurve("A", "50", _flat_hours(5.0)), LoadCurve("B", "50", _flat_hours(9.0))],
    )
    clusters = cluster_business_types(reference, k=2)

    ranked = rank_business_types_by_tsic("Z", "00", reference, clusters=clusters, limit=3)

    assert len(ranked) == 2
    assert {m.business_type_code for m in ranked} == {"A", "B"}
    assert all(m.match_basis == "common_usage_pattern" for m in ranked)


def test_rank_business_types_by_tsic_returns_empty_when_nothing_available():
    reference = _make_reference(business_types=[], load_profiles=[], load_curves=[])
    assert rank_business_types_by_tsic("C", "17", reference, clusters=[]) == []


# ── เทสต์ integration กับข้อมูลจริงใน data/reference/ (ยืนยันว่าใช้งานกับข้อมูลจริงได้ ไม่ error) ──


@pytest.fixture(scope="module")
def reference():
    return load_reference_data()


def test_cluster_business_types_runs_against_real_reference_data(reference):
    clusters = cluster_business_types(reference)
    # ข้อมูลจริงตอนนี้มีธุรกิจที่มี LoadCurve จริงอยู่ 5 ประเภท (31212/34111/34120/63201/71919)
    assert len(clusters) >= 1
    assert all(isinstance(c, BusinessTypeCluster) for c in clusters)
    assert all(c.shape_label for c in clusters)


def test_nearest_business_type_by_tsic_runs_against_real_reference_data(reference):
    clusters = cluster_business_types(reference)
    # section/division ที่ไม่น่าจะมีธุรกิจไหนตรงเป๊ะในข้อมูลจริงตอนนี้เลย (U = องค์การระหว่างประเทศ)
    match = nearest_business_type_by_tsic("U", "99", reference, clusters=clusters)
    assert match is None or match.business_type_code in reference.business_types


def test_rank_business_types_by_tsic_runs_against_real_reference_data(reference):
    clusters = cluster_business_types(reference)
    ranked = rank_business_types_by_tsic("U", "99", reference, clusters=clusters, limit=3)
    assert len(ranked) <= 3
    assert all(m.business_type_code in reference.business_types for m in ranked)
    assert len(ranked) == len({m.business_type_code for m in ranked})  # ไม่มีซ้ำ
