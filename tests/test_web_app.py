import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

import app as app_module  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as client:
        yield client


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_methodology_page_serves_html(client):
    res = client.get("/methodology")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_new_forecast_redirects_to_index(client):
    """หน้า /new-forecast แยกเดิมถูกรวมเข้าหน้าแรกเป็นแท็บแล้ว - route เก่ายังอยู่แต่แค่ redirect
    ไป "/" เผื่อมี bookmark/ลิงก์เก่าอ้างถึง"""

    res = client.get("/new-forecast", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["Location"] == "/"


def test_list_customers(client):
    res = client.get("/api/customers")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert any(c["account_no"] == "DEMO-HOTEL-001" for c in data)


def test_forecast_exact_match(client):
    res = client.get("/api/forecast/DEMO-HOTEL-001")
    assert res.status_code == 200
    data = res.get_json()
    assert data["match"]["level"] == "exact_business_and_rate"
    assert data["match"]["is_exact"] is True
    assert set(data["forecast"]["demand_kw"]) == {"P", "OP", "H"}
    assert set(data["forecast"]["energy_kwh"]) == {"P", "OP", "H"}


def test_forecast_rate_only_fallback(client):
    res = client.get("/api/forecast/DEMO-UNCLASSIFIED-001")
    assert res.status_code == 200
    data = res.get_json()
    assert data["match"]["level"] == "rate_only"
    assert data["match"]["is_exact"] is False
    assert len(data["match"]["warnings"]) > 0


def test_forecast_curve_available_from_committed_reference_data(client):
    """data/reference/load_curves.csv ที่ commit ไว้ตอนนี้มีข้อมูลจริงของ 63201/50 แล้ว (นำเข้า
    AMR จริงแบบ anonymized) — curve.available ต้องเป็น True พร้อมเส้นโค้งรายวัน ไม่เช็คค่า
    ตัวเลขตายตัวเพราะข้อมูลจริงนี้จะถูกอัปเดตเพิ่มเรื่อยๆ ตามจำนวนไซต์ที่นำเข้า"""

    res = client.get("/api/forecast/DEMO-HOTEL-001")
    assert res.status_code == 200
    data = res.get_json()
    assert data["curve"]["available"] is True
    assert data["curve"]["sample_size"] > 0
    assert "all" in data["curve"]["day_types"]


def test_forecast_curve_available_and_scaled_when_present(client, monkeypatch):
    from amr_mapping.models import LoadCurve

    original = app_module.load_reference_data()
    curve = LoadCurve(
        business_type_code="63201",
        rate_code="50",
        hours={"all": [10.0 if h == 9 else None for h in range(24)]},
        contract_kva_ref=2000.0,  # เท่ากับ contract_kva ของ DEMO-HOTEL-001 -> scale_factor เป็น 1.0
        sample_size=3,
    )
    patched = replace(original, load_curves=[curve])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res = client.get("/api/forecast/DEMO-HOTEL-001")
    data = res.get_json()
    assert data["curve"]["available"] is True
    assert data["curve"]["sample_size"] == 3
    assert data["curve"]["day_types"]["all"][9] == pytest.approx(10.0)
    assert data["curve"]["day_types"]["all"][0] is None


def test_admin_curve_returns_unscaled_curve(client, monkeypatch):
    """/api/admin/curve ใช้ scale_factor=1.0 เสมอ (ไม่ผูกกับ KVA ของลูกค้ารายใด) เพราะเป็นการ
    ดูรูปแบบกราฟดิบของกลุ่มธุรกิจ ไม่ใช่การพยากรณ์ให้ลูกค้ารายใดรายหนึ่ง"""
    from amr_mapping.models import LoadCurve

    original = app_module.load_reference_data()
    curve = LoadCurve(
        business_type_code="63201",
        rate_code="50",
        hours={"all": [10.0 if h == 9 else None for h in range(24)]},
        contract_kva_ref=2000.0,
        sample_size=3,
    )
    patched = replace(original, load_curves=[curve])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res = client.get("/api/admin/curve/63201/50")
    data = res.get_json()
    assert data["available"] is True
    assert data["sample_size"] == 3
    assert data["day_types"]["all"][9] == pytest.approx(10.0)


def test_admin_curve_not_available_for_unknown_pair(client):
    res = client.get("/api/admin/curve/NOPE/999")
    data = res.get_json()
    assert data == {"available": False, "day_types": {}, "sample_size": 0}


def test_forecast_not_found(client):
    res = client.get("/api/forecast/NOT-A-REAL-ACCOUNT")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "not_found"


def test_list_load_profile_keys_excludes_default_fallback_row(client):
    res = client.get("/api/load-profile-keys")
    assert res.status_code == 200
    data = res.get_json()
    # ไม่เช็ค sample_size ตายตัวเพราะข้อมูลจริงนี้จะถูกอัปเดตเพิ่มเรื่อยๆ ตามจำนวนไซต์ที่นำเข้า
    assert any(
        k["business_type_code"] == "63201" and k["rate_code"] == "50" and k["has_solar"] is False for k in data
    )
    # แถว DEFAULT/DEFAULT เป็นแค่ fallback ไม่ใช่ธุรกิจจริง ต้องไม่อยู่ในรายการนี้
    assert not any(k["business_type_code"] == "DEFAULT" and k["rate_code"] == "DEFAULT" for k in data)


def test_forecast_adhoc_exact_match(client):
    res = client.post("/api/forecast-adhoc", json={"business_type_code": "63201", "rate_code": "50"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["match"]["level"] == "exact_business_and_rate"
    assert "customer" not in data  # ไม่มี account_no/name จริงให้คืน — ไม่ควรมี key นี้เลย
    # 63201/50 มีเส้นโค้งจริงใน load_curves.csv ที่ commit ไว้แล้ว (ไม่เช็คค่าตายตัวเพราะจะถูก
    # อัปเดตเพิ่มเรื่อยๆ ตามจำนวนไซต์ที่นำเข้า)
    assert data["curve"]["available"] is True
    assert data["curve"]["sample_size"] > 0


def test_forecast_adhoc_with_has_solar_picks_solar_profile(client, monkeypatch):
    """ระบุ has_solar=true มาด้วย ต้องได้โปรไฟล์ที่ has_solar=True กลับมา ไม่ใช่ตัวที่ไม่ติด
    Solar ที่เป็นค่าเริ่มต้นเมื่อไม่ทราบสถานะ"""

    from amr_mapping.models import LoadProfile

    original = app_module.load_reference_data()
    non_solar = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 100, "OP": 100, "H": 100}, energy_kwh={"P": 100, "OP": 100, "H": 100},
        has_solar=False,
    )
    solar = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 40, "OP": 100, "H": 100}, energy_kwh={"P": 40, "OP": 100, "H": 100},
        has_solar=True,
    )
    patched = replace(original, load_profiles=[non_solar, solar])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res = client.post("/api/forecast-adhoc", json={"business_type_code": "63201", "rate_code": "50", "has_solar": True})
    data = res.get_json()
    assert data["match"]["level"] == "exact_business_and_rate"
    assert data["matched_profile"]["has_solar"] is True
    assert data["forecast"]["demand_kw"]["P"] == 40


def test_forecast_adhoc_defaults_to_non_solar_when_unspecified(client, monkeypatch):
    from amr_mapping.models import LoadProfile

    original = app_module.load_reference_data()
    non_solar = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 100, "OP": 100, "H": 100}, energy_kwh={"P": 100, "OP": 100, "H": 100},
        has_solar=False,
    )
    solar = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 40, "OP": 100, "H": 100}, energy_kwh={"P": 40, "OP": 100, "H": 100},
        has_solar=True,
    )
    patched = replace(original, load_profiles=[solar, non_solar])  # solar มาก่อนใน list โดยตั้งใจ
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res = client.post("/api/forecast-adhoc", json={"business_type_code": "63201", "rate_code": "50"})
    data = res.get_json()
    assert data["matched_profile"]["has_solar"] is False


def test_admin_curve_selects_by_has_solar_query_param(client, monkeypatch):
    from amr_mapping.models import LoadCurve

    original = app_module.load_reference_data()
    curves = [
        LoadCurve(business_type_code="63201", rate_code="50", hours={"all": [10.0] * 24}, has_solar=False),
        LoadCurve(business_type_code="63201", rate_code="50", hours={"all": [4.0] * 24}, has_solar=True),
    ]
    patched = replace(original, load_curves=curves)
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res_solar = client.get("/api/admin/curve/63201/50?has_solar=true")
    assert res_solar.get_json()["day_types"]["all"][0] == 4.0

    res_non_solar = client.get("/api/admin/curve/63201/50?has_solar=false")
    assert res_non_solar.get_json()["day_types"]["all"][0] == 10.0

    res_unspecified = client.get("/api/admin/curve/63201/50")
    assert res_unspecified.get_json()["day_types"]["all"][0] == 10.0


def test_delete_load_profile_removes_matching_profile_and_curve(client, monkeypatch, tmp_path):
    """ลบโปรไฟล์+เส้นโค้งของคู่ (business_type_code, rate_code, has_solar) หนึ่งคู่ — ใช้ตอนนำเข้า
    ผิดบัญชี/ผิดประเภทธุรกิจไปแล้ว ต้องไม่กระทบคู่อื่นที่ไม่เกี่ยวข้องเลย"""
    from amr_mapping.loader import _load_load_curves, _load_load_profiles
    from amr_mapping.models import LoadCurve, LoadProfile

    original = app_module.load_reference_data()
    kept_profile = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1}, sample_size=1,
    )
    target_profile = LoadProfile(
        business_type_code="32909", rate_code="UNKNOWN", billing_method="TOU",
        demand_kw={"P": 2, "OP": 2, "H": 2}, energy_kwh={"P": 2, "OP": 2, "H": 2}, sample_size=1,
    )
    kept_curve = LoadCurve(business_type_code="63201", rate_code="50", hours={"all": [1.0] * 24}, sample_size=1)
    target_curve = LoadCurve(business_type_code="32909", rate_code="UNKNOWN", hours={"all": [2.0] * 24}, sample_size=1)
    patched = replace(original, load_profiles=[kept_profile, target_profile], load_curves=[kept_curve, target_curve])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)

    res = client.delete("/api/admin/load-profile/32909/UNKNOWN")
    assert res.status_code == 200
    assert res.get_json() == {"ok": True}

    remaining_profiles = _load_load_profiles(tmp_path / "load_profiles.csv")
    assert [p.key() for p in remaining_profiles] == [("63201", "50", False)]

    remaining_curves = _load_load_curves(tmp_path / "load_curves.csv")
    assert [c.key() for c in remaining_curves] == [("63201", "50", False)]


def test_delete_load_profile_respects_has_solar_query_param(client, monkeypatch, tmp_path):
    from amr_mapping.loader import _load_load_profiles
    from amr_mapping.models import LoadProfile

    original = app_module.load_reference_data()
    non_solar = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1}, sample_size=1, has_solar=False,
    )
    solar = LoadProfile(
        business_type_code="63201", rate_code="50", billing_method="TOU",
        demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1}, sample_size=1, has_solar=True,
    )
    patched = replace(original, load_profiles=[non_solar, solar], load_curves=[])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)

    res = client.delete("/api/admin/load-profile/63201/50?has_solar=true")
    assert res.status_code == 200

    remaining = _load_load_profiles(tmp_path / "load_profiles.csv")
    assert [p.key() for p in remaining] == [("63201", "50", False)]


def test_delete_load_profile_returns_404_when_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.delete("/api/admin/load-profile/NOPE/999")
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_forecast_adhoc_missing_both_fields(client):
    res = client.post("/api/forecast-adhoc", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_forecast_adhoc_never_receives_a_name_field(client):
    """ยืนยันว่า endpoint นี้ใช้งานได้ปกติแม้ไม่ส่ง name มาเลย (ไม่มี parameter นี้อยู่จริง) —
    ส่ง name มาด้วยก็ต้องถูกเพิกเฉย ไม่มีทางไปโผล่ในคำตอบหรือถูกใช้คำนวณอะไรทั้งสิ้น"""

    res = client.post(
        "/api/forecast-adhoc",
        json={"business_type_code": "63201", "rate_code": "50", "name": "ชื่อบริษัทที่ไม่ควรถูกใช้เลย"},
    )
    assert res.status_code == 200
    assert "ชื่อบริษัทที่ไม่ควรถูกใช้เลย" not in res.get_data(as_text=True)


def test_admin_page_serves_html(client):
    res = client.get("/admin")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_list_business_types(client):
    res = client.get("/api/business-types")
    assert res.status_code == 200
    data = res.get_json()
    assert any(bt["code"] == "63201" for bt in data)


def test_list_business_types_full_includes_hierarchy_and_profiles(client):
    res = client.get("/api/business-types-full")
    assert res.status_code == 200
    data = res.get_json()

    paper = next(bt for bt in data if bt["code"] == "34111")
    assert paper["section_code"] == "C"
    assert paper["division_code"] == "17"
    profile = next(p for p in paper["profiles"] if p["rate_code"] == "40")
    assert profile["sample_size"] == 12
    assert profile["has_curve"] is True  # มีข้อมูล load_curves.csv จริงสำหรับคู่นี้


def test_list_business_types_full_marks_placeholder_profiles_as_no_curve(client):
    """แถว load_profiles.csv แบบ placeholder (ตัวเลขประมาณการ ไม่มีข้อมูลรายชั่วโมงจริง) ต้องได้
    has_curve เป็น False เพื่อให้หน้า Admin กรองออกได้ ต่างจากโปรไฟล์ที่มาจาก AMR จริง"""

    res = client.get("/api/business-types-full")
    data = res.get_json()

    hospital = next(bt for bt in data if bt["code"] == "86101")
    profile = next(p for p in hospital["profiles"] if p["rate_code"] == "50")
    assert profile["has_curve"] is False

    # ตัวที่ยังไม่เคยตรวจสอบ TSIC เลย ต้องเป็น None ไม่ใช่ error
    office = next(bt for bt in data if bt["code"] == "68100")
    assert office["division_code"] is None
    assert office["profiles"] == []  # 68100 ยังไม่มีโปรไฟล์อ้างอิงเลย


def test_import_log_local_empty_when_file_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.get("/api/import-log-local")
    assert res.status_code == 200
    assert res.get_json() == []


def test_import_log_local_returns_newest_first(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    (tmp_path / "import_log_local.csv").write_text(
        "imported_at,business_type_code,rate_code,company_name,account_no\n"
        "2026-01-01T00:00:00+00:00,34111,40,บริษัท เอ จำกัด,111\n"
        "2026-02-01T00:00:00+00:00,34120,30,บริษัท บี จำกัด,222\n",
        encoding="utf-8",
    )
    res = client.get("/api/import-log-local")
    data = res.get_json()
    assert len(data) == 2
    assert data[0]["company_name"] == "บริษัท บี จำกัด"  # ใหม่สุดขึ้นก่อน


def test_delete_import_log_local_entry_removes_matching_row(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    (tmp_path / "import_log_local.csv").write_text(
        "imported_at,business_type_code,rate_code,company_name,account_no\n"
        "2026-01-01T00:00:00+00:00,34111,40,บริษัท เอ จำกัด,111\n"
        "2026-02-01T00:00:00+00:00,34120,30,บริษัท บี จำกัด,222\n",
        encoding="utf-8",
    )

    res = client.delete(
        "/api/admin/import-log-local",
        json={"imported_at": "2026-01-01T00:00:00+00:00", "account_no": "111"},
    )
    assert res.status_code == 200
    assert res.get_json() == {"ok": True}

    remaining = client.get("/api/import-log-local").get_json()
    assert len(remaining) == 1
    assert remaining[0]["account_no"] == "222"


def test_delete_import_log_local_entry_returns_404_when_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.delete(
        "/api/admin/import-log-local",
        json={"imported_at": "2026-01-01T00:00:00+00:00", "account_no": "999"},
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_delete_import_log_local_entry_requires_both_fields(client):
    res = client.delete("/api/admin/import-log-local", json={"imported_at": "2026-01-01T00:00:00+00:00"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_get_site_curve_not_found_returns_no_curve_not_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    # ไม่มีไฟล์ site_curves_local.csv เลย (เช่น ยังไม่เคยนำเข้าแบบ auto มาก่อน)
    res = client.get("/api/admin/site-curve/NOT-A-SITE")
    assert res.status_code == 200
    assert res.get_json() == {"available": False, "day_types": {}, "sample_size": 0}


def test_get_site_curve_returns_that_sites_own_curve(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    (tmp_path / "site_curves_local.csv").write_text(
        "company_name,account_no,business_type_code,rate_code,has_solar,day_type,contract_kva_ref,"
        "sample_size,notes," + ",".join(f"h{h:02d}" for h in range(24)) + "\n"
        "บริษัท เอ จำกัด,019900000001,34111,40,false,all,1000,12,ทดสอบ,"
        + ",".join(["5.0" if h == 9 else "" for h in range(24)]) + "\n",
        encoding="utf-8",
    )

    res = client.get("/api/admin/site-curve/019900000001")
    data = res.get_json()
    assert data["available"] is True
    assert data["sample_size"] == 12
    assert data["day_types"]["all"][9] == pytest.approx(5.0)
    # ใช้แสดงเป็นหัวข้อเล็กๆ เหนือกราฟในหน้า Admin เวลาเปิดดูหลายไซต์พร้อมกัน (แยกไม่ออกว่ากราฟ
    # ไหนเป็นของใคร ถ้าไม่มีชื่อกำกับ)
    assert data["company_name"] == "บริษัท เอ จำกัด"


def test_business_type_hierarchy_update_success(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR, _load_business_types

    # คัดลอกไฟล์จริงไปไว้ที่ tmp ก่อน กัน test เขียนทับ business_types.csv จริงในการทดสอบนี้
    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post(
        "/api/business-types/68100/hierarchy",
        json={
            "section_code": "L",
            "section_name_th": "กิจกรรมด้านอสังหาริมทรัพย์",
            "division_code": "68",
            "division_name_th": "กิจกรรมด้านอสังหาริมทรัพย์",
        },
    )
    assert res.status_code == 200
    assert res.get_json()["division_code"] == "68"

    updated_bts = _load_business_types(tmp_data_dir / "business_types.csv")
    assert updated_bts["68100"].division_code == "68"
    assert updated_bts["68100"].section_name_th == "กิจกรรมด้านอสังหาริมทรัพย์"
    # ต้องไม่กระทบประเภทธุรกิจอื่นที่มีอยู่แล้ว (34111 ต้องยัง verified เหมือนเดิม)
    assert updated_bts["34111"].division_code == "17"


def test_business_type_hierarchy_update_unknown_code_404(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post("/api/business-types/NOPE/hierarchy", json={"division_code": "99"})
    assert res.status_code == 404


def test_start_import_missing_credentials(client, monkeypatch):
    monkeypatch.delenv("PEA_AMR_USERNAME", raising=False)
    monkeypatch.delenv("PEA_AMR_PASSWORD", raising=False)

    res = client.post(
        "/api/admin/import",
        json={
            "accounts": "TEST-001",
            "business_type_code": "63201",
            "rate_code": "50",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_credentials"


def test_start_import_credentials_from_form_without_env(client, monkeypatch):
    """หลายบัญชีคนละ username/password กัน ต้องกรอกในฟอร์มได้โดยไม่ต้องตั้ง env var"""
    monkeypatch.delenv("PEA_AMR_USERNAME", raising=False)
    monkeypatch.delenv("PEA_AMR_PASSWORD", raising=False)

    received = {}

    def fake_import_amr_for_business(**kwargs):
        received["username"] = kwargs["username"]
        received["password"] = kwargs["password"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"],
            billing_method="TOU", demand_kw={"P": 0, "OP": 0, "H": 0},
            energy_kwh={"P": 0, "OP": 0, "H": 0}, contract_kva_ref=None,
            sample_size=1, notes="fake",
        )

    monkeypatch.setattr(app_module, "import_amr_for_business", fake_import_amr_for_business)

    res = client.post(
        "/api/admin/import",
        json={
            "username": "form-user",
            "password": "form-pass",
            "accounts": "TEST-001",
            "business_type_code": "63201",
            "rate_code": "50",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert received["username"] == "form-user"
    assert received["password"] == "form-pass"
    # password ต้องไม่หลุดเข้าไปใน job logs ที่ client เห็นได้
    assert "form-pass" not in " ".join(status["logs"])


def test_start_import_invalid_request(client, monkeypatch):
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    res = client.post("/api/admin/import", json={"accounts": "TEST-001"})  # ขาดฟิลด์ที่จำเป็น
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_start_import_rejects_implausible_year(client, monkeypatch):
    """เคยเจอเคสจริง: ผู้ใช้พิมพ์ปีในช่อง date picker ไม่ครบ 4 หลัก (เช่น "25" แทน "2025")
    ทำให้ได้วันที่ปี 0025 ส่งไปเปิด Selenium session จริงแล้วทำให้ ChromeDriver พัง — ต้องเช็ค
    และ error ตั้งแต่ต้นทางก่อนเปิด session เลย ไม่ใช่ปล่อยผ่านไปพังทีหลัง"""
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    res = client.post(
        "/api/admin/import",
        json={"start_date": "0025-10-01", "end_date": "0025-10-31"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"
    assert "ปี" in res.get_json()["message"]


def test_start_import_rejects_start_date_after_end_date(client, monkeypatch):
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    res = client.post(
        "/api/admin/import",
        json={"start_date": "2026-08-31", "end_date": "2026-08-01"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_start_import_and_poll_job_success(client, monkeypatch):
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    def fake_import_amr_for_business(**kwargs):
        assert kwargs["username"] == "u"
        assert kwargs["password"] == "p"
        assert kwargs["accounts"] == ["TEST-001", "TEST-002"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"],
            rate_code=kwargs["rate_code"],
            billing_method="TOU",
            demand_kw={"P": 1.0, "OP": 2.0, "H": 3.0},
            energy_kwh={"P": 10.0, "OP": 20.0, "H": 30.0},
            contract_kva_ref=kwargs.get("contract_kva"),
            sample_size=2,
            notes="fake",
        )

    monkeypatch.setattr(app_module, "import_amr_for_business", fake_import_amr_for_business)

    res = client.post(
        "/api/admin/import",
        json={
            "accounts": "TEST-001, TEST-002",
            "business_type_code": "86101",
            "rate_code": "50",
            "start_date": "2026-01-01",
            "end_date": "2026-02-28",
        },
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status_res = client.get(f"/api/admin/import/{job_id}")
        status = status_res.get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["business_type_code"] == "86101"
    assert status["result"]["demand_kw"] == {"P": 1.0, "OP": 2.0, "H": 3.0}


def test_start_import_passes_has_solar_checkbox_through(client, monkeypatch):
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    received = {}

    def fake_import_amr_for_business(**kwargs):
        received["has_solar"] = kwargs["has_solar"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"], billing_method="TOU",
            demand_kw={"P": 1.0, "OP": 2.0, "H": 3.0}, energy_kwh={"P": 10.0, "OP": 20.0, "H": 30.0},
            has_solar=kwargs["has_solar"],
        )

    monkeypatch.setattr(app_module, "import_amr_for_business", fake_import_amr_for_business)

    res = client.post(
        "/api/admin/import",
        json={
            "accounts": "TEST-001", "business_type_code": "86101", "rate_code": "50",
            "start_date": "2026-01-01", "end_date": "2026-02-28", "has_solar": True,
        },
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert received["has_solar"] is True
    assert status["result"]["has_solar"] is True


def test_import_job_not_found(client):
    res = client.get("/api/admin/import/does-not-exist")
    assert res.status_code == 404


# ── โหมดแนบไฟล์ที่มีอยู่แล้ว (ไม่ต้อง login เว็บ PEA เลย — /api/admin/import-file) ──


def test_start_import_file_does_not_require_business_type_or_rate_code(client, monkeypatch, tmp_path):
    """business_type_code/rate_code ไม่บังคับกรอกแล้ว (ตามที่ผู้ใช้ขอ: แนบแค่ไฟล์ก็พอ) — ต้อง
    เริ่ม job ได้แม้ไม่ระบุมาเลย (ปล่อยให้ import_amr_from_files เป็นคนหาให้เองจากทะเบียนลูกค้า)"""
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received["business_type_code"] = kwargs["business_type_code"]
        received["rate_code"] = kwargs["rate_code"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code="63201", rate_code="50", billing_method="TOU",
            demand_kw={"P": 0, "OP": 0, "H": 0}, energy_kwh={"P": 0, "OP": 0, "H": 0},
            contract_kva_ref=None, sample_size=1, notes="fake",
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (io.BytesIO(b"<html></html>"), "a.xls")},  # ไม่มี business_type_code/rate_code เลย
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    # ค่าว่างเปล่า (ไม่ใช่ None) ต้องถูกส่งต่อไปให้ import_amr_from_files เป็นคนตัดสินใจเอง
    assert received["business_type_code"] == ""
    assert received["rate_code"] == ""


def test_start_import_file_invalid_request_when_no_files(client):
    res = client.post(
        "/api/admin/import-file",
        data={"business_type_code": "63201", "rate_code": "50"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_start_import_file_success(client, monkeypatch, tmp_path):
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received["file_paths"] = kwargs["file_paths"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"],
            billing_method="TOU", demand_kw={"P": 1, "OP": 1, "H": 1},
            energy_kwh={"P": 1, "OP": 1, "H": 1}, contract_kva_ref=kwargs["contract_kva"],
            sample_size=2, notes="fake", has_solar=kwargs["has_solar"],
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={
            "files": [
                (io.BytesIO("<html>เดือนที่ 1</html>".encode("utf-8")), "amr_2026_07.xls"),
                (io.BytesIO("<html>เดือนที่ 2</html>".encode("utf-8")), "amr_2026_08.xls"),
            ],
            "business_type_code": "63201",
            "rate_code": "50",
            "contract_kva": "1000",
            "source_label": "unit test upload",
            "has_solar": "true",
        },
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["business_type_code"] == "63201"
    assert status["result"]["has_solar"] is True

    # ไฟล์ที่แนบมาต้องถูกบันทึกลงดิสก์จริง (คนละไฟล์กัน) ก่อนส่งต่อ path ไปประมวลผล
    assert len(received["file_paths"]) == 2
    for path in received["file_paths"]:
        assert Path(path).exists()
    contents = {Path(p).read_text(encoding="utf-8") for p in received["file_paths"]}
    assert contents == {"<html>เดือนที่ 1</html>", "<html>เดือนที่ 2</html>"}


def test_start_import_file_passes_site_label_through(client, monkeypatch, tmp_path):
    """site_label (ไม่บังคับ — ใช้แยกกรณีบริษัทเดียวกันมีหลายมิเตอร์) ต้องถูกส่งต่อไปให้
    import_amr_from_files ด้วย"""
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received["site_label"] = kwargs["site_label"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"],
            billing_method="TOU", demand_kw={"P": 1, "OP": 1, "H": 1},
            energy_kwh={"P": 1, "OP": 1, "H": 1}, sample_size=1, notes="fake", has_solar=False,
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={
            "files": (io.BytesIO(b"<html>fake</html>"), "amr.xls"),
            "business_type_code": "63201",
            "rate_code": "50",
            "site_label": "YMLC4",
        },
        content_type="multipart/form-data",
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert received["site_label"] == "YMLC4"


def test_start_import_file_error_from_import_surfaces_in_job_status(client, monkeypatch, tmp_path):
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    def fake_import_amr_from_files(**kwargs):
        raise RuntimeError("ไม่สามารถอ่านข้อมูลจากไฟล์ที่ดาวน์โหลดมาได้เลย")

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={
            "files": (io.BytesIO(b"not real data"), "bad.xls"),
            "business_type_code": "63201",
            "rate_code": "50",
        },
        content_type="multipart/form-data",
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert "ไม่สามารถอ่านข้อมูล" in status["error"]


def test_start_import_file_extracts_amr_files_from_zip(client, monkeypatch, tmp_path):
    """แนบไฟล์ .zip ที่รวมไฟล์ AMR หลายไฟล์ไว้ — ต้องแตกไฟล์ออกมาแล้วส่งไป import_amr_from_files
    เหมือนแนบไฟล์ .xls/.html ตรงๆ ทุกอย่าง (ผู้ใช้ไม่ต้องแตกไฟล์เองก่อนแนบ)"""
    import io
    import zipfile

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received["file_paths"] = kwargs["file_paths"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code="63201", rate_code="50", billing_method="TOU",
            demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1},
            contract_kva_ref=None, sample_size=2, notes="fake",
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("2026-07/amr_2026_07.xls", "<html>เดือนที่ 1</html>")
        zf.writestr("2026-08/amr_2026_08.xls", "<html>เดือนที่ 2</html>")
        zf.writestr("__MACOSX/._amr_2026_07.xls", "junk")  # ไฟล์ระบบที่ macOS แถมมาเวลาซิป — ต้องข้าม
        zf.writestr("readme.txt", "not an AMR file")  # นามสกุลไม่รองรับ — ต้องข้ามเหมือนกัน
    zip_buffer.seek(0)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (zip_buffer, "amr_bundle.zip")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert len(received["file_paths"]) == 2  # แค่ 2 ไฟล์ .xls จริง ไม่รวม __MACOSX/readme.txt
    contents = {Path(p).read_text(encoding="utf-8") for p in received["file_paths"]}
    assert contents == {"<html>เดือนที่ 1</html>", "<html>เดือนที่ 2</html>"}


def test_start_import_file_neutralizes_zip_slip_path_traversal(client, monkeypatch, tmp_path):
    """ไฟล์ในซิปที่มีชื่อพยายาม path traversal ออกนอกโฟลเดอร์ upload (เช่น "../../evil.xls")
    ต้องถูกตัด path ย่อยทิ้งแล้วเขียนอยู่ใต้ upload_dir เท่านั้น ไม่มีทางหลุดออกไปเขียนไฟล์นอก
    โฟลเดอร์ที่ตั้งใจไว้ได้เลย (zip slip vulnerability)"""
    import io
    import zipfile

    download_dir = tmp_path / "amr_downloads"
    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", download_dir)

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received["file_paths"] = kwargs["file_paths"]
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code="63201", rate_code="50", billing_method="TOU",
            demand_kw={"P": 1, "OP": 1, "H": 1}, energy_kwh={"P": 1, "OP": 1, "H": 1},
            contract_kva_ref=None, sample_size=1, notes="fake",
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../../../tmp/evil.xls", "<html>ไม่ควรหลุดออกไปนอก upload_dir</html>")
    zip_buffer.seek(0)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (zip_buffer, "traversal.zip")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert len(received["file_paths"]) == 1
    extracted_path = Path(received["file_paths"][0]).resolve()
    # ไฟล์ที่แตกออกมาต้องอยู่ใต้ download_dir เท่านั้น (ตัด "../" ทิ้งหมดแล้ว) ไม่ใช่ /tmp/evil.xls
    assert download_dir.resolve() in extracted_path.parents
    assert extracted_path.name != "evil.xls" or extracted_path.parent != Path("/tmp")


def test_start_import_file_rejects_corrupt_zip(client, monkeypatch, tmp_path):
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    res = client.post(
        "/api/admin/import-file",
        data={"files": (io.BytesIO(b"not actually a zip file"), "broken.zip")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_start_import_file_rejects_zip_with_no_amr_files_inside(client, monkeypatch, tmp_path):
    import io
    import zipfile

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("readme.txt", "not an AMR file")
    zip_buffer.seek(0)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (zip_buffer, "empty_of_amr.zip")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_start_import_auto_mode_when_business_type_and_rate_omitted(client, monkeypatch):
    """ไม่กรอกประเภทธุรกิจ/อัตรา -> ต้องเรียก import_amr_auto (ตรวจจับอัตโนมัติ) แทน
    import_amr_for_business และไม่ต้องมี accounts ก็ยังผ่าน validation ได้"""
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    received = {}

    def fake_import_amr_auto(**kwargs):
        received.update(kwargs)
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code="34111", rate_code="40", billing_method="TOU",
            demand_kw={"P": 1.0, "OP": 2.0, "H": 3.0},
            energy_kwh={"P": 10.0, "OP": 20.0, "H": 30.0},
            contract_kva_ref=15000.0, sample_size=2, notes="fake-auto",
        )

    def fail_if_called(**kwargs):
        raise AssertionError("ไม่ควรเรียก import_amr_for_business ในโหมด auto")

    monkeypatch.setattr(app_module, "import_amr_auto", fake_import_amr_auto)
    monkeypatch.setattr(app_module, "import_amr_for_business", fail_if_called)

    res = client.post(
        "/api/admin/import",
        json={"start_date": "2026-01-01", "end_date": "2026-02-28"},  # ไม่มี business_type_code/rate_code/accounts เลย
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["business_type_code"] == "34111"
    assert received["username"] == "u"
    assert "accounts" not in received  # import_amr_auto ไม่รับพารามิเตอร์นี้


def test_start_import_auto_mode_surfaces_scraped_customer_name(client, monkeypatch):
    """ชื่อบริษัทจริงที่ scrape มาได้ตอนโหมดอัตโนมัติ ต้องถูกส่งกลับมาในสถานะ job (ผ่าน
    on_profile callback) ให้หน้า Admin แสดงผลได้ — อยู่ใน memory ของ job นี้เท่านั้น"""

    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    def fake_import_amr_auto(**kwargs):
        on_profile = kwargs.get("on_profile")
        if on_profile:
            on_profile({"name": "บริษัท ทดสอบ เว็บแอป จำกัด", "account_no": "019900000099", "meter_no": "33333333"})

        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code="34111", rate_code="40", billing_method="TOU",
            demand_kw={"P": 1.0, "OP": 2.0, "H": 3.0},
            energy_kwh={"P": 10.0, "OP": 20.0, "H": 30.0},
            contract_kva_ref=15000.0, sample_size=2, notes="fake-auto",
        )

    monkeypatch.setattr(app_module, "import_amr_auto", fake_import_amr_auto)

    res = client.post(
        "/api/admin/import",
        json={"start_date": "2026-01-01", "end_date": "2026-02-28"},
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["customer_profile"]["name"] == "บริษัท ทดสอบ เว็บแอป จำกัด"
    assert status["customer_profile"]["account_no"] == "019900000099"


def test_business_type_lookup_missing_company_name(client):
    res = client.post("/api/business-type-lookup", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_business_type_lookup_success_suggests_matching_business_type(client, monkeypatch):
    """DBD คืนรหัส TSIC "17099" (division "17" เหมือน 34111 ในระบบเรา ที่ยืนยัน division ไว้
    แล้ว) — ต้องแนะนำ suggested_business_type_code เป็น "34111" ให้"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        log(f"ค้นหา {company_name}")
        return [
            CompanyBusinessInfo(
                registration_no="0105544000157",
                juristic_name="บริษัท ทดสอบกระดาษ จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="17099",
                tsic_name_th="การผลิตผลิตภัณฑ์กระดาษอื่นๆ",
            )
        ]

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบกระดาษ จำกัด"})
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    candidates = status["result"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["tsic_code"] == "17099"
    assert candidates[0]["tsic_division_code"] == "17"
    assert candidates[0]["suggested_business_type_code"] == "34111"
    # ชื่อที่ค้นหาตรงเป๊ะกับผลลัพธ์เดียวที่เจอ -> ต้องรายงาน exact_match_index
    assert status["result"]["exact_match_index"] == 0


def test_business_type_lookup_auto_forecasts_when_match_is_unambiguous(client, monkeypatch):
    """ถ้าส่ง rate_code มาพร้อมชื่อบริษัท (ในฟอร์มเดียวกัน) และจับคู่ประเภทธุรกิจได้แบบไม่กำกวม
    (exact match เดียว) ต้องพยากรณ์ให้อัตโนมัติทันทีในผล job เลย (primary_index/forecast) —
    ผู้ใช้จึงไม่ต้องกดยืนยัน/เลือกประเภทธุรกิจเองอีกขั้นตอนหนึ่งถ้าจับคู่ได้ชัดเจน"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        return [
            CompanyBusinessInfo(
                registration_no="0105544000157",
                juristic_name="บริษัท ทดสอบกระดาษ จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="17099",
                tsic_name_th="การผลิตผลิตภัณฑ์กระดาษอื่นๆ",
            )
        ]

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post(
        "/api/business-type-lookup",
        json={"company_name": "บริษัท ทดสอบกระดาษ จำกัด", "rate_code": "40", "contract_kva": 14900},
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    assert result["primary_index"] == 0
    assert result["primary_is_ambiguous"] is False
    assert result["forecast"] is not None
    assert result["forecast"]["matched_profile"]["business_type_code"] == "34111"
    assert result["forecast"]["matched_profile"]["rate_code"] == "40"


def test_business_type_lookup_start_accepts_optional_forecast_params(client):
    """/api/business-type-lookup ต้องรับ rate_code/contract_kva/has_solar เสริม (ไม่บังคับ) และ
    validate contract_kva เป็นตัวเลข — คืน 400 ถ้าไม่ใช่ตัวเลข"""

    res = client.post(
        "/api/business-type-lookup",
        json={"company_name": "บริษัท ทดสอบ จำกัด", "contract_kva": "ไม่ใช่ตัวเลข"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_business_type_lookup_suggests_approximate_match_when_no_exact_division(client, monkeypatch):
    """DBD คืนรหัส TSIC ที่ division ไม่ตรงกับธุรกิจไหนในระบบเราตรงๆ เลย (division "71" —
    ไม่มีธุรกิจไหนยืนยัน division นี้ไว้ในข้อมูลอ้างอิงจริงตอนนี้) — ต้องยัง fallback ไปแนะนำ
    ธุรกิจที่ใกล้เคียงที่สุด (same section หรือ cluster ที่พบบ่อยสุด) แทนที่จะปล่อยว่างเฉยๆ
    และต้องรายงานว่าเป็นการประมาณการ (suggested_is_approximate=True) พร้อมคำอธิบาย"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        return [
            CompanyBusinessInfo(
                registration_no="0105544000999",
                juristic_name="บริษัท ทดสอบวิศวกรรม จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="71100",
                tsic_name_th="กิจกรรมงานสถาปัตยกรรม",
            )
        ]

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบวิศวกรรม จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    candidate = status["result"]["candidates"][0]
    assert candidate["tsic_division_code"] == "71"
    assert candidate["suggested_business_type_code"], "ต้องแนะนำธุรกิจที่ใกล้เคียงที่สุดแทนที่จะปล่อยว่าง"
    assert candidate["suggested_is_approximate"] is True
    assert candidate["suggested_explanation"]


def test_business_type_lookup_handles_selenium_error_gracefully(client, monkeypatch):
    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise RuntimeError("เปิด Chrome ไม่สำเร็จ (จำลอง error)")

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert "เปิด Chrome ไม่สำเร็จ" in status["error"]


def test_business_type_lookup_falls_back_to_dataforthai_when_dbd_blocked(client, monkeypatch):
    """ยืนยันจากผู้ใช้จริง: DBD บล็อกการเข้าถึงอัตโนมัติ (Incapsula) — ต้อง fallback ไปลองหา
    ข้อมูลที่ dataforthai.com แทน (เว็บบุคคลที่สาม) และคืนผลเป็น status "success" (ไม่ใช่ "error")
    พร้อม blocked=True และข้อมูล fallback ที่ดึงมาได้ แทนที่จะทำให้ทั้ง job ดูเหมือนพังไปเลย"""

    from amr_mapping.dataforthai_lookup import CompanySuggestion
    from amr_mapping.dbd_lookup import BlockedByAntiBot

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 123-456")

    def fake_suggest(company_name, log=lambda m: None, timeout=10.0):
        return [CompanySuggestion(label="บริษัท ทดสอบ จำกัด (มหาชน)", value="ทดสอบ")]

    def fake_category(driver, company_name, log=lambda m: None, timeout=20.0):
        log("✅ พบหมวดธุรกิจ: ร้านสะดวกซื้อ/มินิมาร์ท")
        return "ร้านสะดวกซื้อ/มินิมาร์ท"

    class _FakeDriver:
        def quit(self):
            pass

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(app_module, "suggest_companies_with_fallback", fake_suggest)
    monkeypatch.setattr(app_module, "lookup_business_category", fake_category)
    monkeypatch.setattr(app_module, "setup_dataforthai_driver", lambda headless=True: _FakeDriver())
    monkeypatch.setattr(app_module, "search_wikipedia_company", lambda company_name, log=lambda m: None: None)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ จำกัด (มหาชน)"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    assert result["blocked"] is True
    assert "Incapsula" in result["blocked_message"]
    assert result["candidates"] == []
    assert result["fallback"]["source"] == "dataforthai"
    assert result["fallback"]["business_category"] == "ร้านสะดวกซื้อ/มินิมาร์ท"
    assert result["fallback"]["candidates"][0]["label"] == "บริษัท ทดสอบ จำกัด (มหาชน)"
    assert result["dbd_opendata_available"] is False
    assert result["dbd_opendata_matches"] == []
    assert result["wikipedia_result"] is None


def test_business_type_lookup_includes_wikipedia_result_when_found(client, monkeypatch):
    """เสริมช่องทางฟรี Wikipedia (ดู wikipedia_lookup.py) — ตอน DBD บล็อก ต้องลองค้น Wikipedia
    ด้วย แล้วใส่ผลลัพธ์ (แค่ข้อความอิสระประกอบการตัดสินใจ ไม่ใช่รหัส TSIC) กลับไปในผล job"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot
    from amr_mapping.wikipedia_lookup import WikipediaCompanyInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 111")

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(app_module, "setup_dataforthai_driver", lambda headless=True: (_ for _ in ()).throw(Exception("no chrome")))
    monkeypatch.setattr(app_module, "suggest_companies_with_fallback", lambda *a, **k: [])
    monkeypatch.setattr(
        app_module,
        "search_wikipedia_company",
        lambda company_name, log=lambda m: None: WikipediaCompanyInfo(
            title="ซีพี ออลล์", summary="ซีพี ออลล์ เป็นบริษัทค้าปลีก...", url="https://th.wikipedia.org/wiki/ซีพี_ออลล์"
        ),
    )

    res = client.post("/api/business-type-lookup", json={"company_name": "ซีพี ออลล์"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    assert result["wikipedia_result"]["title"] == "ซีพี ออลล์"
    assert result["wikipedia_result"]["summary"] == "ซีพี ออลล์ เป็นบริษัทค้าปลีก..."
    # "ค้าปลีก" เจอ แต่ไม่มีธุรกิจค้าปลีกที่มีโปรไฟล์จริงตรงในระบบทดสอบ -> เป็นแค่การประมาณการ
    # (is_approximate) จึงต้อง "ไม่" auto-apply แบบเงียบๆ (suggested_business_type_code เป็น None)
    # และต้องมีรายการอันดับให้เลือกเองแทน
    assert result["wikipedia_result"]["guessed_keyword"] == "ค้าปลีก"
    assert result["wikipedia_result"]["suggested_is_approximate"] is True
    assert result["wikipedia_result"]["suggested_business_type_code"] is None
    assert len(result["wikipedia_result"]["ranked_candidates"]) >= 1
    assert result["wikipedia_result"]["ranked_candidates"][0]["business_type_code"]


def test_business_type_lookup_guesses_business_type_from_wikipedia_keyword(client, monkeypatch):
    """ถ้าข้อความสรุปจาก Wikipedia มีคำสำคัญที่รู้จัก (ดู keyword_classify.py) เช่น "โรงแรม" ต้อง
    เดาประเภทธุรกิจให้ (พร้อมบอกคำที่ใช้เดาชัดเจน — ไม่ใช่รหัส TSIC จริง) เพื่อให้พิมพ์ชื่อบริษัท
    ครั้งเดียวแล้วได้ผลพยากรณ์เลยแม้ตอน DBD DataWarehouse บล็อกอยู่"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot
    from amr_mapping.wikipedia_lookup import WikipediaCompanyInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 222")

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(app_module, "setup_dataforthai_driver", lambda headless=True: (_ for _ in ()).throw(Exception("no chrome")))
    monkeypatch.setattr(app_module, "suggest_companies_with_fallback", lambda *a, **k: [])
    monkeypatch.setattr(
        app_module,
        "search_wikipedia_company",
        lambda company_name, log=lambda m: None: WikipediaCompanyInfo(
            title="บริษัท ทดสอบ จำกัด",
            summary="บริษัท ทดสอบ จำกัด เป็นเจ้าของโรงแรมหลายแห่งในประเทศไทย",
            url="https://th.wikipedia.org/wiki/ทดสอบ",
        ),
    )

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    wp_result = status["result"]["wikipedia_result"]
    assert wp_result["guessed_keyword"] == "โรงแรม"
    assert wp_result["suggested_business_type_code"] == "63201"
    assert wp_result["suggested_is_approximate"] is False
    # มั่นใจพอ (ไม่ใช่แค่ประมาณการ) -> ไม่ต้องมีรายการอันดับให้เลือก auto-apply ไปเลยพอ
    assert "ranked_candidates" not in wp_result


def test_business_type_lookup_includes_local_dbd_opendata_matches_when_available(client, monkeypatch):
    """ถ้าเคยดึงฐานข้อมูล DBD Open Data มาเก็บในเครื่องไว้แล้ว (ดู dbd_opendata.py) ตอน DBD
    DataWarehouse บล็อก ต้องลองค้นจากฐานข้อมูลนี้ด้วย (ค้นออฟไลน์ เร็วกว่า) แล้วใส่ผลลัพธ์กลับมา"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 789")

    def fake_category(driver, company_name, log=lambda m: None, timeout=20.0):
        return None

    class _FakeDriver:
        def quit(self):
            pass

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(app_module, "setup_dataforthai_driver", lambda headless=True: _FakeDriver())
    monkeypatch.setattr(app_module, "lookup_business_category", fake_category)
    monkeypatch.setattr(app_module, "suggest_companies_with_fallback", lambda company_name, log=lambda m: None, timeout=10.0: [])
    monkeypatch.setattr(app_module, "dbd_opendata_is_available", lambda: True)
    monkeypatch.setattr(
        app_module, "search_juristic_person",
        lambda name_query, limit=10: [{"reg_id": "0105544000157", "name": "บริษัท ทดสอบ เก่า จำกัด", "status": "registration"}],
    )
    monkeypatch.setattr(app_module, "search_wikipedia_company", lambda company_name, log=lambda m: None: None)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ เก่า จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    assert result["dbd_opendata_available"] is True
    assert len(result["dbd_opendata_matches"]) == 1
    assert result["dbd_opendata_matches"][0]["name"] == "บริษัท ทดสอบ เก่า จำกัด"
    # ชื่อตรงเป๊ะกับคำค้น (case/เว้นวรรคเหมือนกัน) แต่ mock ไม่มี purpose_code เลยไม่มีข้อเสนอ
    # ประเภทธุรกิจให้ — ยังต้อง mark ว่าตรงเป๊ะไว้ (ให้ UI auto-apply ได้ แม้จะไม่มีโปรไฟล์ก็ตาม)
    assert result["dbd_opendata_exact_match_index"] == 0
    assert result["dbd_opendata_matches"][0]["suggested_business_type_code"] is None


def test_business_type_lookup_suggests_business_type_from_dbd_opendata_purpose_code(client, monkeypatch):
    """ข้อมูล DBD Open Data มี "รหัสวัตถุประสงค์" (TSIC-like 5 หลัก) ติดมาด้วย — ต้องใช้จับคู่
    ประเภทธุรกิจในระบบเราได้แบบเดียวกับผลจาก DBD DataWarehouse โดยตรง เพื่อพยากรณ์อัตโนมัติได้แม้
    ตอน DBD DataWarehouse บล็อกอยู่ (ดู _suggest_business_type_for_division ใน web/app.py)"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 999")

    class _FakeDriver:
        def quit(self):
            pass

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(app_module, "setup_dataforthai_driver", lambda headless=True: _FakeDriver())
    monkeypatch.setattr(app_module, "lookup_business_category", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "suggest_companies_with_fallback", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "dbd_opendata_is_available", lambda: True)
    monkeypatch.setattr(
        app_module, "search_juristic_person",
        lambda name_query, limit=10: [
            {
                "reg_id": "0105544000199",
                "name": "โรงแรม ทดสอบ จำกัด",
                "status": "registration",
                "purpose_code": "55101",
                "purpose": "กิจการโรงแรม",
            }
        ],
    )
    monkeypatch.setattr(app_module, "search_wikipedia_company", lambda company_name, log=lambda m: None: None)

    res = client.post("/api/business-type-lookup", json={"company_name": "โรงแรม ทดสอบ จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    match = result["dbd_opendata_matches"][0]
    assert match["tsic_code"] == "55101"
    assert match["tsic_name_th"] == "กิจการโรงแรม"
    assert match["suggested_business_type_code"] == "63201"  # หมวดโรงแรม (division 55) มีโปรไฟล์จริงรองรับ
    assert match["suggested_is_approximate"] is False
    assert result["dbd_opendata_exact_match_index"] == 0


def test_dbd_opendata_status_reports_unavailable_by_default(client):
    res = client.get("/api/admin/dbd-opendata/status")
    assert res.status_code == 200
    assert res.get_json() == {"available": False}


def test_dbd_opendata_fetch_starts_background_job(client, monkeypatch):
    def fake_fetch(start_year=2020, start_month=1, log=lambda m: None):
        log("📥 ดึง registration 2024-01 ...")
        log("🏁 เสร็จสิ้น รวมทั้งหมด 5 แถว")
        return {"total_rows": 5, "months_with_data": 1, "months_tried": 2, "db_path": "/tmp/fake.db"}

    monkeypatch.setattr(app_module, "fetch_dbd_opendata", fake_fetch)

    res = client.post("/api/admin/dbd-opendata/fetch", json={"start_year": 2024, "start_month": 1})
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/dbd-opendata/fetch/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["total_rows"] == 5
    assert any("เสร็จสิ้น" in m for m in status["logs"])


def test_dbd_opendata_fetch_rejects_non_numeric_year(client):
    res = client.post("/api/admin/dbd-opendata/fetch", json={"start_year": "ไม่ใช่ตัวเลข"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_business_type_lookup_reports_blocked_even_when_dataforthai_fallback_fails(client, monkeypatch):
    """fallback เองก็ล้มเหลวได้ (เช่น dataforthai.com ก็ใช้งานไม่ได้ตอนนั้น) — ต้องไม่ทำให้ job
    กลายเป็น status "error" ไปด้วย แค่ fallback เป็น None แทน (blocked=True ยังอยู่ ผู้ใช้จะได้รู้
    ว่า DBD บล็อก ไม่ใช่แค่ error กำกวม)"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 999")

    def fake_category(driver, company_name, log=lambda m: None, timeout=20.0):
        return None  # Selenium ก็หาหมวดธุรกิจไม่เจอเช่นกัน (จำลอง)

    def fake_suggest(company_name, log=lambda m: None, timeout=10.0):
        raise RuntimeError("dataforthai.com ก็ล่มด้วย (จำลอง)")

    class _FakeDriver:
        def quit(self):
            pass

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(app_module, "setup_dataforthai_driver", lambda headless=True: _FakeDriver())
    monkeypatch.setattr(app_module, "lookup_business_category", fake_category)
    monkeypatch.setattr(app_module, "suggest_companies_with_fallback", fake_suggest)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["blocked"] is True
    assert status["result"]["fallback"] is None


def test_start_import_manual_mode_when_only_business_type_given(client, monkeypatch):
    """ระบุ business_type_code มาแม้จะไม่มี rate_code -> ต้องถือเป็นโหมดกรอกเอง (manual)
    ไม่ใช่ auto จึงต้อง validate ครบทุกฟิลด์ตามเดิม (จะ error เพราะ rate_code หาย)"""
    monkeypatch.setenv("PEA_AMR_USERNAME", "u")
    monkeypatch.setenv("PEA_AMR_PASSWORD", "p")

    res = client.post(
        "/api/admin/import",
        json={
            "accounts": "TEST-001",
            "business_type_code": "86101",
            "start_date": "2026-01-01",
            "end_date": "2026-02-28",
        },
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"
    assert "rate_code" in res.get_json()["message"]


def test_pending_amr_page_serves_html(client):
    res = client.get("/pending-amr")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_start_import_file_saves_pending_entry_when_business_type_and_rate_unknown(client, monkeypatch, tmp_path):
    """โหมดแนบไฟล์: อ่านเลขบัญชีจากไฟล์ได้ แต่หาประเภทธุรกิจ/รหัสอัตราไม่เจอในทะเบียนลูกค้า — แทนที่
    จะทิ้ง error เฉยๆ ต้องบันทึกไว้เป็นรายการ "รอทราบอัตรา" (pending_amr_local.csv) เพื่อกรอกย้อนหลัง
    ได้ทีหลังโดยไม่ต้องอัปโหลดไฟล์ใหม่"""
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")
    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    def fake_import_amr_from_files(**kwargs):
        kwargs["on_profile"]({"name": "บริษัท ทดสอบ จำกัด", "account_no": "019900000099", "meter_no": "MT-9"})
        raise RuntimeError(
            "ไม่ทราบประเภทธุรกิจ/รหัสอัตราของบัญชีนี้ (พบบัญชี 019900000099 ในไฟล์ "
            "แต่ไม่พบในทะเบียนลูกค้า) — กรุณากรอกประเภทธุรกิจและรหัสอัตราเอง"
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (io.BytesIO(b"<html>fake</html>"), "amr.xls")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "pending_rate"
    assert status["pending_id"]

    from amr_mapping.loader import load_pending_amr_local

    entries = load_pending_amr_local(pending_path)
    assert len(entries) == 1
    assert entries[0]["pending_id"] == status["pending_id"]
    assert entries[0]["account_no"] == "019900000099"
    assert entries[0]["company_name"] == "บริษัท ทดสอบ จำกัด"
    assert entries[0]["meter_no"] == "MT-9"
    assert len(entries[0]["file_paths"].split("|")) == 1


def test_start_import_file_does_not_save_pending_entry_for_unrelated_errors(client, monkeypatch, tmp_path):
    """error อื่นๆ ที่ไม่ใช่ "ไม่ทราบประเภทธุรกิจ/รหัสอัตรา" (เช่นไฟล์เสียหาย) ต้องรายงาน error ตรงๆ
    เหมือนเดิม ไม่ใช่ไปบันทึกเป็นรายการรอทราบอัตรา (resolve ไปก็ไม่มีประโยชน์อะไร)"""
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")
    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    def fake_import_amr_from_files(**kwargs):
        kwargs["on_profile"]({"name": "", "account_no": "019900000099", "meter_no": ""})
        raise RuntimeError("ไม่สามารถอ่านข้อมูลจากไฟล์ที่แนบมาได้เลย")

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (io.BytesIO(b"not real data"), "bad.xls")},
        content_type="multipart/form-data",
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert not pending_path.exists()


def test_start_import_file_no_pending_entry_when_account_no_unknown(client, monkeypatch, tmp_path):
    """อ่านเลขบัญชีจากไฟล์ไม่ได้เลย (on_profile ไม่ถูกเรียก หรือ account_no ว่าง) — ไม่มีข้อมูลพอจะ
    ให้ resolve ย้อนหลังได้ จึงต้องรายงาน error ตรงๆ ไม่บันทึกเป็นรายการรอทราบอัตรา"""
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DOWNLOAD_DIR", tmp_path / "amr_downloads")
    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    def fake_import_amr_from_files(**kwargs):
        raise RuntimeError("ไม่ทราบประเภทธุรกิจ/รหัสอัตราของบัญชีนี้ — กรุณากรอกประเภทธุรกิจและรหัสอัตราเอง")

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/import-file",
        data={"files": (io.BytesIO(b"<html>fake</html>"), "amr.xls")},
        content_type="multipart/form-data",
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/import/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert not pending_path.exists()


def test_list_pending_amr_returns_newest_first(client, monkeypatch, tmp_path):
    from amr_mapping.loader import append_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    append_pending_amr_local(
        {
            "pending_id": "old1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "OLD",
            "company_name": "", "meter_no": "", "file_paths": "/tmp/a.xls",
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )
    append_pending_amr_local(
        {
            "pending_id": "new1",
            "created_at": "2026-02-01T00:00:00+00:00",
            "account_no": "NEW",
            "company_name": "", "meter_no": "", "file_paths": "/tmp/b.xls",
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )

    res = client.get("/api/admin/pending-amr")
    assert res.status_code == 200
    entries = res.get_json()["entries"]
    assert [e["pending_id"] for e in entries] == ["new1", "old1"]


def test_list_pending_amr_empty_when_file_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", tmp_path / "no_such_file.csv")
    res = client.get("/api/admin/pending-amr")
    assert res.status_code == 200
    assert res.get_json()["entries"] == []


def test_delete_pending_amr_removes_entry(client, monkeypatch, tmp_path):
    from amr_mapping.loader import append_pending_amr_local, load_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)
    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "", "meter_no": "", "file_paths": "/tmp/a.xls",
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )

    res = client.delete("/api/admin/pending-amr/abc123")
    assert res.status_code == 200
    assert load_pending_amr_local(pending_path) == []


def test_delete_pending_amr_returns_404_when_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", tmp_path / "pending_amr_local.csv")
    res = client.delete("/api/admin/pending-amr/not-found")
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_resolve_pending_amr_success_reimports_and_removes_entry(client, monkeypatch, tmp_path):
    from amr_mapping.loader import append_pending_amr_local, load_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    saved_file = tmp_path / "amr_downloads" / "uploaded" / "job1" / "amr.xls"
    saved_file.parent.mkdir(parents=True)
    saved_file.write_text("<html>fake</html>", encoding="utf-8")

    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "บริษัท ทดสอบ จำกัด",
            "meter_no": "MT-9",
            "file_paths": str(saved_file),
            "contract_kva": "1000",
            "has_solar": "false",
            "source_label": "",
        },
        pending_path,
    )

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received.update(kwargs)
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"],
            billing_method="TOU", demand_kw={"P": 1, "OP": 1, "H": 1},
            energy_kwh={"P": 1, "OP": 1, "H": 1}, contract_kva_ref=kwargs["contract_kva"],
            sample_size=1, notes="fake", has_solar=kwargs["has_solar"],
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/pending-amr/abc123/resolve",
        json={"business_type_code": "63201", "rate_code": "50", "has_solar": True},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["result"]["business_type_code"] == "63201"
    assert data["result"]["rate_code"] == "50"
    assert data["result"]["has_solar"] is True

    assert received["file_paths"] == [str(saved_file)]
    assert received["business_type_code"] == "63201"
    assert received["rate_code"] == "50"
    assert received["contract_kva"] == 1000.0  # เก็บค่าเดิมจากตอนบันทึก pending ไว้ (ไม่ได้ระบุมาใหม่)

    assert load_pending_amr_local(pending_path) == []


def test_resolve_pending_amr_passes_site_label_through(client, monkeypatch, tmp_path):
    """site_label (ไม่บังคับ — ใช้แยกกรณีบริษัทเดียวกันมีหลายมิเตอร์) ต้องถูกส่งต่อไปให้
    import_amr_from_files ด้วย"""
    from amr_mapping.loader import append_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    saved_file = tmp_path / "amr_downloads" / "uploaded" / "job1" / "amr.xls"
    saved_file.parent.mkdir(parents=True)
    saved_file.write_text("<html>fake</html>", encoding="utf-8")

    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "บริษัท ทดสอบ จำกัด",
            "meter_no": "", "file_paths": str(saved_file),
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received.update(kwargs)
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"],
            billing_method="TOU", demand_kw={"P": 1, "OP": 1, "H": 1},
            energy_kwh={"P": 1, "OP": 1, "H": 1}, sample_size=1, notes="fake", has_solar=kwargs["has_solar"],
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    res = client.post(
        "/api/admin/pending-amr/abc123/resolve",
        json={"business_type_code": "63201", "rate_code": "50", "site_label": "YMLC4"},
    )
    assert res.status_code == 200
    assert received["site_label"] == "YMLC4"


def test_resolve_pending_amr_with_rate_code_unknown_uses_sentinel(client, monkeypatch, tmp_path):
    """ติ๊ก "ไม่ทราบรหัสอัตรา" มา (rate_code_unknown=True) — ต้องนำเข้าได้โดยไม่ต้องกรอกรหัสอัตรา
    จริง ใช้ค่า sentinel UNKNOWN_RATE_CODE แทน (ยังใช้ประโยชน์ได้ที่ชั้น BUSINESS_ONLY)"""
    from amr_mapping import UNKNOWN_RATE_CODE
    from amr_mapping.loader import append_pending_amr_local, load_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)

    saved_file = tmp_path / "amr_downloads" / "uploaded" / "job1" / "amr.xls"
    saved_file.parent.mkdir(parents=True)
    saved_file.write_text("<html>fake</html>", encoding="utf-8")

    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "บริษัท ทดสอบ จำกัด",
            "meter_no": "",
            "file_paths": str(saved_file),
            "contract_kva": "",
            "has_solar": "false",
            "source_label": "",
        },
        pending_path,
    )

    received = {}

    def fake_import_amr_from_files(**kwargs):
        received.update(kwargs)
        from amr_mapping.models import LoadProfile

        return LoadProfile(
            business_type_code=kwargs["business_type_code"], rate_code=kwargs["rate_code"],
            billing_method="TOU", demand_kw={"P": 1, "OP": 1, "H": 1},
            energy_kwh={"P": 1, "OP": 1, "H": 1}, contract_kva_ref=kwargs["contract_kva"],
            sample_size=1, notes="fake", has_solar=kwargs["has_solar"],
        )

    monkeypatch.setattr(app_module, "import_amr_from_files", fake_import_amr_from_files)

    # ส่ง rate_code เป็นค่าว่างมาด้วย (เหมือนช่องถูกปิดไว้ฝั่ง UI) — rate_code_unknown ต้องชนะเสมอ
    res = client.post(
        "/api/admin/pending-amr/abc123/resolve",
        json={"business_type_code": "63201", "rate_code": "", "rate_code_unknown": True},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["result"]["rate_code"] == UNKNOWN_RATE_CODE
    assert received["rate_code"] == UNKNOWN_RATE_CODE
    assert load_pending_amr_local(pending_path) == []


def test_resolve_pending_amr_rate_code_unknown_still_requires_business_type(client, monkeypatch, tmp_path):
    from amr_mapping.loader import append_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)
    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "", "meter_no": "", "file_paths": "/tmp/a.xls",
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )

    res = client.post(
        "/api/admin/pending-amr/abc123/resolve",
        json={"business_type_code": "", "rate_code_unknown": True},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_resolve_pending_amr_missing_business_type_or_rate_returns_400(client, monkeypatch, tmp_path):
    from amr_mapping.loader import append_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)
    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "", "meter_no": "", "file_paths": "/tmp/a.xls",
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )

    res = client.post("/api/admin/pending-amr/abc123/resolve", json={"business_type_code": "63201", "rate_code": ""})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_resolve_pending_amr_returns_404_when_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", tmp_path / "pending_amr_local.csv")
    res = client.post("/api/admin/pending-amr/not-found/resolve", json={"business_type_code": "63201", "rate_code": "50"})
    assert res.status_code == 404


def test_resolve_pending_amr_returns_400_when_saved_files_are_gone(client, monkeypatch, tmp_path):
    from amr_mapping.loader import append_pending_amr_local

    pending_path = tmp_path / "pending_amr_local.csv"
    monkeypatch.setattr(app_module, "PENDING_AMR_LOCAL_PATH", pending_path)
    append_pending_amr_local(
        {
            "pending_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_no": "019900000099",
            "company_name": "", "meter_no": "",
            "file_paths": str(tmp_path / "amr_downloads" / "uploaded" / "job1" / "gone.xls"),
            "contract_kva": "", "has_solar": "false", "source_label": "",
        },
        pending_path,
    )

    res = client.post(
        "/api/admin/pending-amr/abc123/resolve",
        json={"business_type_code": "63201", "rate_code": "50"},
    )
    assert res.status_code == 400
    assert "ไม่พบไฟล์" in res.get_json()["message"]
