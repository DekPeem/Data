import sys
import time
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


def test_forecast_not_found(client):
    res = client.get("/api/forecast/NOT-A-REAL-ACCOUNT")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "not_found"


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
