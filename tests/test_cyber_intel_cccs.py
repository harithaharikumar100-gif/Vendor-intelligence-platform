"""
Tests for cyber_intel.py's CCCS advisory matching logic. Pre-populates the
module's in-memory cache directly so tests never hit the real network.
"""
import pytest

import cyber_intel as ci

FAKE_ENTRIES = [
    {"title": "[Control systems] ABB security advisory (AV26-942)",
     "url": "https://cyber.gc.ca/en/alerts-advisories/control-systems-abb-security-advisory-av26-942",
     "updated": "2026-09-18T17:52:31Z"},
    {"title": "SolarWinds security advisory (AV26-941)",
     "url": "https://cyber.gc.ca/en/alerts-advisories/solarwinds-security-advisory-av26-941",
     "updated": "2026-09-18T17:40:52Z"},
]


@pytest.fixture(autouse=True)
def fake_cccs_cache(monkeypatch):
    monkeypatch.setitem(ci._CCCS_CACHE, "entries", FAKE_ENTRIES)
    monkeypatch.setitem(ci._CCCS_CACHE, "fetched_at", "2026-09-18T18:00:00Z")
    yield
    ci._CCCS_CACHE["entries"] = None


class TestQueryCccsAdvisories:
    def test_matches_named_vendor(self):
        result = ci.query_cccs_advisories("SolarWinds")
        assert result["total"] == 1
        assert result["entries"][0]["title"] == "SolarWinds security advisory (AV26-941)"

    def test_matches_case_insensitively(self):
        result = ci.query_cccs_advisories("abb")
        assert result["total"] == 1

    def test_unrelated_vendor_no_match(self):
        result = ci.query_cccs_advisories("Shopify")
        assert result["total"] == 0
        assert result["entries"] == []

    def test_short_query_returns_empty_without_matching(self):
        result = ci.query_cccs_advisories("ab")
        assert result == {"entries": [], "total": 0, "source": "CCCS (cyber.gc.ca)", "retrieved_at": result["retrieved_at"]}

    def test_result_carries_source_attribution(self):
        result = ci.query_cccs_advisories("SolarWinds")
        entry = result["entries"][0]
        assert entry["source"] == "CCCS (cyber.gc.ca)"
        assert entry["url"].startswith("https://cyber.gc.ca/")
        assert entry["retrieved_at"]


class TestGatherCyberIntelligenceIncludesCccs:
    def test_cccs_signal_included_in_aggregate(self, monkeypatch):
        # Avoid real network calls for NVD/CISA/HIBP in this aggregate test.
        monkeypatch.setattr(ci, "query_nvd_cves", lambda v, **k: {"cves": [], "total": 0})
        monkeypatch.setattr(ci, "query_cisa_kev", lambda v: {"entries": [], "total": 0})
        result = ci.gather_cyber_intelligence("SolarWinds", domain="")
        assert result["cccs_count"] == 1
        cccs_signals = [s for s in result["signals"] if s["category"] == "Government Advisory" and "CCCS" in s["indicator"]]
        assert len(cccs_signals) == 1
