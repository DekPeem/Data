import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.curve_stats import compute_hourly_boxplot


def _site(business_type_code="31212", has_solar=False, h09=100.0):
    return {
        "business_type_code": business_type_code,
        "has_solar": has_solar,
        "hours": {"all": [None] * 9 + [h09] + [None] * 14},
    }


def test_returns_empty_dict_when_fewer_than_2_matching_sites():
    site_curves = [_site(h09=100.0)]
    assert compute_hourly_boxplot(site_curves, "31212", has_solar=False) == {}


def test_computes_quartiles_across_matching_sites():
    site_curves = [_site(h09=v) for v in (10.0, 20.0, 30.0, 40.0)]
    result = compute_hourly_boxplot(site_curves, "31212", has_solar=False)
    stats = result["all"][9]
    assert stats["min"] == 10.0
    assert stats["max"] == 40.0
    assert stats["median"] == 25.0
    assert stats["n"] == 4


def test_hour_with_insufficient_data_is_none():
    site_curves = [_site(h09=10.0), _site(h09=20.0)]
    result = compute_hourly_boxplot(site_curves, "31212", has_solar=False)
    assert result["all"][9] is not None
    assert result["all"][8] is None  # ไม่มีไซต์ไหนมีค่าชั่วโมง 8 เลย


def test_ignores_sites_of_other_business_type():
    site_curves = [_site(business_type_code="31212", h09=10.0), _site(business_type_code="31212", h09=20.0), _site(business_type_code="99999", h09=999.0)]
    result = compute_hourly_boxplot(site_curves, "31212", has_solar=False)
    assert result["all"][9]["n"] == 2
    assert result["all"][9]["max"] == 20.0


def test_has_solar_filter_excludes_mismatched_sites():
    site_curves = [_site(has_solar=False, h09=10.0), _site(has_solar=False, h09=20.0), _site(has_solar=True, h09=500.0)]
    result = compute_hourly_boxplot(site_curves, "31212", has_solar=False)
    assert result["all"][9]["n"] == 2


def test_has_solar_none_includes_all_sites_regardless_of_solar():
    site_curves = [_site(has_solar=False, h09=10.0), _site(has_solar=True, h09=20.0)]
    result = compute_hourly_boxplot(site_curves, "31212", has_solar=None)
    assert result["all"][9]["n"] == 2


def test_scale_factor_applies_to_all_stats():
    site_curves = [_site(h09=10.0), _site(h09=20.0)]
    result = compute_hourly_boxplot(site_curves, "31212", has_solar=False, scale_factor=2.0)
    stats = result["all"][9]
    assert stats["min"] == 20.0
    assert stats["max"] == 40.0
    assert stats["median"] == 30.0
