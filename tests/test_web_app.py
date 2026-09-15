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


def test_forecast_curve_not_available_by_default(client):
    """data/reference/load_curves.csv ที่ commit ไว้ยังไม่มีข้อมูลจริง (ต้องนำเข้า AMR ใหม่
    ก่อนถึงจะมี) — curve.available ต้องเป็น False ไม่ใช่ error"""

    res = client.get("/api/forecast/DEMO-HOTEL-001")
    assert res.status_code == 200
    data = res.get_json()
    assert data["curve"] == {"available": False, "day_types": {}, "sample_size": 0}


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


def test_forecast_not_found(client):
    res = client.get("/api/forecast/NOT-A-REAL-ACCOUNT")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "not_found"


def test_list_load_profile_keys_excludes_default_fallback_row(client):
    res = client.get("/api/load-profile-keys")
    assert res.status_code == 200
    data = res.get_json()
    assert {"business_type_code": "63201", "rate_code": "50", "sample_size": 12} in data
    # แถว DEFAULT/DEFAULT เป็นแค่ fallback ไม่ใช่ธุรกิจจริง ต้องไม่อยู่ในรายการนี้
    assert not any(k["business_type_code"] == "DEFAULT" and k["rate_code"] == "DEFAULT" for k in data)


def test_forecast_adhoc_exact_match(client):
    res = client.post("/api/forecast-adhoc", json={"business_type_code": "63201", "rate_code": "50"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["match"]["level"] == "exact_business_and_rate"
    assert "customer" not in data  # ไม่มี account_no/name จริงให้คืน — ไม่ควรมี key นี้เลย
    assert data["curve"] == {"available": False, "day_types": {}, "sample_size": 0}


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
