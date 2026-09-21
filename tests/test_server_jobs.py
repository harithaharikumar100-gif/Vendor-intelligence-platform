"""
Tests for the async job pattern (POST /api/jobs, GET /api/jobs/{job_id}) in
server.py — the integration surface for a caller embedding this pipeline as
a feature in another system, where blocking on the full synchronous
/api/analyze run (observed live: anywhere from ~90s to 15+ minutes) isn't
viable against that caller's own HTTP timeouts.

get_vendor_analysis is monkeypatched to return near-instantly so these tests
don't depend on real network calls or Groq's latency - they exercise the
job-lifecycle machinery itself, not the underlying pipeline (already covered
by the rest of the suite).
"""
import time

import pytest
from fastapi.testclient import TestClient

import server
import store

client = TestClient(server.app)


def _fast_result(vendor="Test Vendor", **_):
    return {"vendor_name": vendor, "risk_scores": {"financial": 20}, "query_date": "2026-01-01"}, {}


def _failing_result(**_):
    return {"error": "upstream failure"}, {}


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Every test gets a fresh (in-memory) job store, cache, and rate
    limiter, and never touches the real pipeline or a real webhook
    endpoint. Swapping in brand-new store instances rather than clearing
    the existing ones also verifies these are used purely through the
    server.KV_STORE / server.RATE_LIMITER indirection, not captured by
    reference anywhere at import time."""
    monkeypatch.setattr(server, "KV_STORE", store.InMemoryKVStore())
    monkeypatch.setattr(server, "RATE_LIMITER", store.InMemoryRateLimiter())
    monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: _fast_result(**k))
    monkeypatch.setattr(server.config, "AUTO_GENERATE_PDF_REPORT", False)
    monkeypatch.setattr(server.config, "API_KEYS", {})
    yield


def _wait_for_terminal(job_id, timeout=5, headers=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{job_id}", headers=headers)
        body = r.json()
        if body.get("status") in ("complete", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal state within {timeout}s")


class TestSubmitJob:
    def test_returns_202_with_job_id_and_poll_url(self):
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "pending"
        assert body["poll_url"] == f"/api/jobs/{body['job_id']}"

    def test_empty_vendor_rejected(self):
        r = client.post("/api/jobs", json={"vendor": "   "})
        assert r.status_code == 400

    def test_job_reaches_complete_with_result(self):
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"})
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id)
        assert final["status"] == "complete"
        assert final["result"]["vendor_name"] == "Test Vendor"
        assert final["error"] is None

    def test_failed_analysis_marks_job_failed(self, monkeypatch):
        monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: _failing_result(**k))
        r = client.post("/api/jobs", json={"vendor": "Bad Vendor"})
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id)
        assert final["status"] == "failed"
        assert "upstream failure" in final["error"]
        assert final["result"] is None

    def test_duplicate_submission_while_inflight_returns_same_job(self, monkeypatch):
        """Cheap idempotency: two submissions for the same vendor+params
        while the first is still running must not spin up parallel work."""
        started = []
        release = []

        def slow_analysis(**k):
            started.append(1)
            while not release:
                time.sleep(0.01)
            return _fast_result(**k)

        monkeypatch.setattr(server, "get_vendor_analysis", slow_analysis)

        r1 = client.post("/api/jobs", json={"vendor": "Slow Vendor"})
        job_id_1 = r1.json()["job_id"]

        deadline = time.time() + 5
        while not started and time.time() < deadline:
            time.sleep(0.01)

        r2 = client.post("/api/jobs", json={"vendor": "Slow Vendor"})
        job_id_2 = r2.json()["job_id"]

        assert job_id_1 == job_id_2
        assert len(started) == 1  # underlying pipeline only actually ran once

        release.append(1)
        _wait_for_terminal(job_id_1)

    def test_different_params_are_independent_jobs(self):
        r1 = client.post("/api/jobs", json={"vendor": "Vendor A"})
        r2 = client.post("/api/jobs", json={"vendor": "Vendor B"})
        assert r1.json()["job_id"] != r2.json()["job_id"]

    def test_response_never_leaks_internal_bookkeeping_fields(self):
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"})
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id)
        assert "cache_key" not in final
        assert "completed_at_epoch" not in final

    def test_no_auth_configured_client_field_is_none(self):
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"})
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id)
        assert final["client"] is None


class TestApiKeyAuthAndQuota:
    def test_valid_key_records_client_identity_on_job(self, monkeypatch):
        monkeypatch.setattr(server.config, "API_KEYS", {"key-a": {"client": "acme-corp", "daily_quota": None}})
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"}, headers={"X-API-Key": "key-a"})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id, headers={"X-API-Key": "key-a"})
        assert final["client"] == "acme-corp"

    def test_missing_key_rejected_when_keys_configured(self, monkeypatch):
        monkeypatch.setattr(server.config, "API_KEYS", {"key-a": {"client": "acme-corp", "daily_quota": None}})
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"})
        assert r.status_code == 401

    def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setattr(server.config, "API_KEYS", {"key-a": {"client": "acme-corp", "daily_quota": None}})
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"}, headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401

    def test_daily_quota_enforced_per_key(self, monkeypatch):
        monkeypatch.setattr(server.config, "API_KEYS", {"key-a": {"client": "acme-corp", "daily_quota": 2}})
        headers = {"X-API-Key": "key-a"}
        assert client.post("/api/jobs", json={"vendor": "Vendor 1"}, headers=headers).status_code == 202
        assert client.post("/api/jobs", json={"vendor": "Vendor 2"}, headers=headers).status_code == 202
        r = client.post("/api/jobs", json={"vendor": "Vendor 3"}, headers=headers)
        assert r.status_code == 429
        assert "quota" in r.json()["detail"].lower()

    def test_quota_is_independent_per_key(self, monkeypatch):
        monkeypatch.setattr(server.config, "API_KEYS", {
            "key-a": {"client": "acme-corp", "daily_quota": 1},
            "key-b": {"client": "globex-inc", "daily_quota": 1},
        })
        assert client.post("/api/jobs", json={"vendor": "Vendor 1"}, headers={"X-API-Key": "key-a"}).status_code == 202
        assert client.post("/api/jobs", json={"vendor": "Vendor 1"}, headers={"X-API-Key": "key-a"}).status_code == 429
        # a different key's own budget is untouched by key-a's usage
        assert client.post("/api/jobs", json={"vendor": "Vendor 2"}, headers={"X-API-Key": "key-b"}).status_code == 202


class TestGetJob:
    def test_unknown_job_id_returns_404(self):
        r = client.get("/api/jobs/does-not-exist")
        assert r.status_code == 404

    def test_pending_job_has_no_result_yet(self, monkeypatch):
        def slow_analysis(**k):
            time.sleep(1)
            return _fast_result(**k)

        monkeypatch.setattr(server, "get_vendor_analysis", slow_analysis)
        r = client.post("/api/jobs", json={"vendor": "Slow Vendor"})
        job_id = r.json()["job_id"]

        immediate = client.get(f"/api/jobs/{job_id}").json()
        assert immediate["status"] in ("pending", "running")
        assert immediate["result"] is None


class TestWebhookCallback:
    def test_callback_url_receives_completed_job(self, monkeypatch):
        received = []
        monkeypatch.setattr(server.requests, "post", lambda url, json, timeout: received.append((url, json)))

        r = client.post("/api/jobs", json={"vendor": "Test Vendor", "callback_url": "https://example.com/hook"})
        job_id = r.json()["job_id"]
        _wait_for_terminal(job_id)

        deadline = time.time() + 2
        while not received and time.time() < deadline:
            time.sleep(0.02)

        assert len(received) == 1
        url, payload = received[0]
        assert url == "https://example.com/hook"
        assert payload["job_id"] == job_id
        assert payload["status"] == "complete"

    def test_webhook_failure_does_not_affect_job_status(self, monkeypatch):
        def broken_post(*a, **k):
            raise ConnectionError("dns failure")

        monkeypatch.setattr(server.requests, "post", broken_post)
        r = client.post("/api/jobs", json={"vendor": "Test Vendor", "callback_url": "https://unreachable.example/hook"})
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id)
        assert final["status"] == "complete"
