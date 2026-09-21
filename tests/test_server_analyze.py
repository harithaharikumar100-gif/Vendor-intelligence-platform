"""
Tests for /api/analyze's caching (now backed by store.KVStore instead of a
plain dict) and /api/download-pdf's cache reuse via the pdf_index secondary
lookup that replaced the old full-cache-scan (see server._find_cached_pdf).
Also covers the per-IP rate limiter, now backed by store.RateLimiter.
"""
import pytest
from fastapi.testclient import TestClient

import server
import store

client = TestClient(server.app)


def _fast_result(vendor="Test Vendor", **_):
    return {"vendor_name": vendor, "risk_scores": {"financial": 20}, "query_date": "2026-01-01"}, {}


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(server, "KV_STORE", store.InMemoryKVStore())
    monkeypatch.setattr(server, "RATE_LIMITER", store.InMemoryRateLimiter())
    monkeypatch.setattr(server.config, "API_KEYS", {})
    monkeypatch.setattr(server.config, "AUTO_GENERATE_PDF_REPORT", False)
    yield


class TestAnalyzeCaching:
    def test_second_identical_call_is_served_from_cache(self, monkeypatch):
        calls = []
        monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: (calls.append(1), _fast_result(**k))[1])

        r1 = client.post("/api/analyze", json={"vendor": "Test Vendor"})
        r2 = client.post("/api/analyze", json={"vendor": "Test Vendor"})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()
        assert len(calls) == 1  # second call served from the store, not re-run

    def test_different_vendors_are_not_conflated(self, monkeypatch):
        monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: _fast_result(**k))
        r1 = client.post("/api/analyze", json={"vendor": "Vendor A"})
        r2 = client.post("/api/analyze", json={"vendor": "Vendor B"})
        assert r1.json()["vendor_name"] == "Vendor A"
        assert r2.json()["vendor_name"] == "Vendor B"

    def test_error_result_raises_500_and_is_not_cached(self, monkeypatch):
        calls = []

        def failing(**k):
            calls.append(1)
            return {"error": "boom"}, {}

        monkeypatch.setattr(server, "get_vendor_analysis", failing)
        r1 = client.post("/api/analyze", json={"vendor": "Bad Vendor"})
        assert r1.status_code == 500
        r2 = client.post("/api/analyze", json={"vendor": "Bad Vendor"})
        assert r2.status_code == 500
        assert len(calls) == 2  # a failed run must not be cached as if it succeeded


class TestDownloadPdfReuse:
    def test_eagerly_generated_pdf_is_reused_not_regenerated(self, monkeypatch):
        monkeypatch.setattr(server.config, "AUTO_GENERATE_PDF_REPORT", True)
        monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: _fast_result(**k))

        gen_calls = []

        def fake_generate_pdf(result, filename, vendor_name):
            gen_calls.append(1)
            with open(filename, "wb") as f:
                f.write(b"%PDF-fake-bytes")

        monkeypatch.setattr(server, "generate_pdf", fake_generate_pdf)

        analyze_resp = client.post("/api/analyze", json={"vendor": "Test Vendor"})
        assert analyze_resp.status_code == 200
        result = analyze_resp.json()
        assert len(gen_calls) == 1  # generated once, eagerly, during /api/analyze

        pdf_resp = client.post("/api/download-pdf", json={"result": result, "vendor_name": "Test Vendor"})
        assert pdf_resp.status_code == 200
        assert pdf_resp.content == b"%PDF-fake-bytes"
        assert len(gen_calls) == 1  # download-pdf reused the cached bytes, didn't regenerate

    def test_no_cached_pdf_generates_on_demand(self, monkeypatch):
        gen_calls = []

        def fake_generate_pdf(result, filename, vendor_name):
            gen_calls.append(1)
            with open(filename, "wb") as f:
                f.write(b"%PDF-on-demand")

        monkeypatch.setattr(server, "generate_pdf", fake_generate_pdf)

        result = {"vendor_name": "Never Analyzed Vendor", "query_date": "2026-01-01"}
        pdf_resp = client.post("/api/download-pdf", json={"result": result, "vendor_name": "Never Analyzed Vendor"})
        assert pdf_resp.status_code == 200
        assert pdf_resp.content == b"%PDF-on-demand"
        assert len(gen_calls) == 1


class TestRateLimit:
    def test_exceeding_limit_returns_429(self, monkeypatch):
        monkeypatch.setattr(server.config, "RATE_LIMIT_MAX_REQUESTS", 2)
        monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: _fast_result(vendor=k.get("vendor", "V")))

        assert client.post("/api/analyze", json={"vendor": "V1"}).status_code == 200
        assert client.post("/api/analyze", json={"vendor": "V2"}).status_code == 200
        r3 = client.post("/api/analyze", json={"vendor": "V3"})
        assert r3.status_code == 429
