import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

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
