import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import amr_mapping.wikipedia_lookup as wikipedia_lookup
from amr_mapping.wikipedia_lookup import search_wikipedia_company


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_search_wikipedia_company_returns_summary_on_success(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        if "list=search" in request.full_url:
            body = {"query": {"search": [{"title": "ซีพี ออลล์"}]}}
        else:
            body = {"query": {"pages": {"123": {"extract": "ซีพี ออลล์ เป็นบริษัทค้าปลีก..."}}}}
        return _FakeResponse(__import__("json").dumps(body).encode("utf-8"))

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    result = search_wikipedia_company("ซีพี ออลล์")

    assert result is not None
    assert result.title == "ซีพี ออลล์"
    assert result.summary == "ซีพี ออลล์ เป็นบริษัทค้าปลีก..."
    assert result.url == "https://th.wikipedia.org/wiki/%E0%B8%8B%E0%B8%B5%E0%B8%9E%E0%B8%B5%20%E0%B8%AD%E0%B8%AD%E0%B8%A5%E0%B8%A5%E0%B9%8C"
    assert len(calls) == 2  # search แล้วค่อย extract


def test_search_wikipedia_company_returns_none_when_no_search_results(monkeypatch):
    def fake_urlopen(request, timeout=None):
        body = {"query": {"search": []}}
        return _FakeResponse(__import__("json").dumps(body).encode("utf-8"))

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    logs = []
    result = search_wikipedia_company("บริษัทที่ไม่มีใครรู้จักเลย", log=logs.append)

    assert result is None
    assert any("ไม่พบหน้า Wikipedia" in m for m in logs)


def test_search_wikipedia_company_returns_none_when_extract_missing(monkeypatch):
    def fake_urlopen(request, timeout=None):
        if "list=search" in request.full_url:
            body = {"query": {"search": [{"title": "หน้าเปล่า"}]}}
        else:
            body = {"query": {"pages": {"1": {}}}}  # ไม่มี extract เลย
        return _FakeResponse(__import__("json").dumps(body).encode("utf-8"))

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    result = search_wikipedia_company("หน้าเปล่า")
    assert result is None


def test_search_wikipedia_company_truncates_long_summary(monkeypatch):
    long_text = "ก" * 800

    def fake_urlopen(request, timeout=None):
        if "list=search" in request.full_url:
            body = {"query": {"search": [{"title": "บริษัทยาว"}]}}
        else:
            body = {"query": {"pages": {"1": {"extract": long_text}}}}
        return _FakeResponse(__import__("json").dumps(body).encode("utf-8"))

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    result = search_wikipedia_company("บริษัทยาว")
    assert result is not None
    assert len(result.summary) <= 501  # 500 + "…"
    assert result.summary.endswith("…")


def test_search_wikipedia_company_returns_none_on_http_error(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen(request, timeout=None):
        raise HTTPError(request.full_url, 500, "Internal Server Error", {}, None)

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    logs = []
    result = search_wikipedia_company("ทดสอบ", log=logs.append)
    assert result is None
    assert any("HTTP 500" in m for m in logs)


def test_search_wikipedia_company_returns_none_on_url_error(monkeypatch):
    from urllib.error import URLError

    def fake_urlopen(request, timeout=None):
        raise URLError("จำลอง network error")

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    logs = []
    result = search_wikipedia_company("ทดสอบ", log=logs.append)
    assert result is None
    assert any("เชื่อมต่อ Wikipedia API ไม่สำเร็จ" in m for m in logs)


def test_search_wikipedia_company_returns_none_on_invalid_json(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse(b"not json at all")

    monkeypatch.setattr(wikipedia_lookup, "urlopen", fake_urlopen)

    result = search_wikipedia_company("ทดสอบ")
    assert result is None
