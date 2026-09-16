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
