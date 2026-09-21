"""
Runs the actual server.py endpoints (not just store.py in isolation) against
a Redis-shaped backend (fakeredis - a high-fidelity in-process fake
implementing real Redis command semantics, not a live Redis server) to
prove the whole integration works end to end: JSON round-tripping through
server.KV_STORE, TTL-backed caching, the try_claim-based in-flight dedup,
and per-key quota - not just that store.py's own unit tests pass in
isolation from how server.py actually calls it.
"""
import time

import pytest
import fakeredis
from fastapi.testclient import TestClient

import server
import store

client = TestClient(server.app)


def _fast_result(vendor="Test Vendor", **_):
    return {"vendor_name": vendor, "risk_scores": {"financial": 20}, "query_date": "2026-01-01"}, {}


@pytest.fixture(autouse=True)
def redis_backed_state(monkeypatch):
    fake_client = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(server, "KV_STORE", store.RedisKVStore(fake_client))
    monkeypatch.setattr(server, "RATE_LIMITER", store.RedisRateLimiter(fake_client))
    monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: _fast_result(**k))
    monkeypatch.setattr(server.config, "API_KEYS", {})
    monkeypatch.setattr(server.config, "AUTO_GENERATE_PDF_REPORT", False)
    yield


def _wait_for_terminal(job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body.get("status") in ("complete", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal state within {timeout}s")


class TestAnalyzeAgainstRedis:
    def test_analyze_caches_through_redis(self, monkeypatch):
        calls = []
        monkeypatch.setattr(server, "get_vendor_analysis", lambda **k: (calls.append(1), _fast_result(**k))[1])
        r1 = client.post("/api/analyze", json={"vendor": "Test Vendor"})
        r2 = client.post("/api/analyze", json={"vendor": "Test Vendor"})
        assert r1.status_code == r2.status_code == 200
        assert r1.json() == r2.json()
        assert len(calls) == 1


class TestJobsAgainstRedis:
    def test_full_job_lifecycle(self):
        r = client.post("/api/jobs", json={"vendor": "Test Vendor"})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        final = _wait_for_terminal(job_id)
        assert final["status"] == "complete"
        assert final["result"]["vendor_name"] == "Test Vendor"

    def test_inflight_dedup_through_redis(self, monkeypatch):
        """The exact race try_claim exists to close: verified here against
        the Redis-shaped SET NX code path, not just the in-memory one."""
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
        assert r2.json()["job_id"] == job_id_1
        assert len(started) == 1

        release.append(1)
        _wait_for_terminal(job_id_1)


class TestQuotaAgainstRedis:
    def test_quota_enforced_through_redis(self, monkeypatch):
        monkeypatch.setattr(server.config, "API_KEYS", {"key-a": {"client": "acme-corp", "daily_quota": 1}})
        headers = {"X-API-Key": "key-a"}
        assert client.post("/api/jobs", json={"vendor": "V1"}, headers=headers).status_code == 202
        r2 = client.post("/api/jobs", json={"vendor": "V2"}, headers=headers)
        assert r2.status_code == 429
