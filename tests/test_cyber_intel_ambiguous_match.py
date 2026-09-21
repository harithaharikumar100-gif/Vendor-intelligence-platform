"""
Tests for the ambiguous_match confidence flag on CISA KEV / CCCS entries,
and the severity capping + caveat note gather_cyber_intelligence applies
when it's set.

Confirmed live bug: a vendor named "Metro" matched a CVE about Windows 8's
unrelated "Metro" UI design language, and "Canadian National Railway
Company" matched an unrelated "National Instruments" CCCS advisory purely
via the standalone word "National" (that specific word is now excluded as
generic, but the same class of coincidence remains possible for any other
distinctive-but-common word) - both were presented as Critical/High
severity findings with the same confidence as a genuine match. Full entity
resolution isn't feasible here, so instead every match that isn't backed by
a genuine multi-word phrase is surfaced (never silently dropped) but capped
at "Elevated" severity with a visible caveat.
"""
import pytest

import cyber_intel as ci

CISA_FAKE_KEV = [
    # "shield" is distinctive (not in _GENERIC_NAME_WORDS) but coincidentally
    # names an unrelated product here - exercises the single-distinctive-
    # word OR-match path, same class as "National" matching "National
    # Instruments" before that specific word was excluded as generic.
    {"vendorProject": "Acme Shield Corp", "product": "Endpoint Protection", "cveID": "CVE-2026-0001",
     "vulnerabilityName": "Buffer Overflow", "dateAdded": "2026-01-01", "knownRansomwareCampaignUse": "Unknown"},
    {"vendorProject": "Royal Bank of Canada", "product": "Online Banking Portal", "cveID": "CVE-2026-0002",
     "vulnerabilityName": "Auth Bypass", "dateAdded": "2026-01-02", "knownRansomwareCampaignUse": "Unknown"},
]

CCCS_FAKE_ENTRIES = [
    {"title": "[Control Systems] Acme Shield Corp security advisory (AV26-914)",
     "url": "https://cyber.gc.ca/x", "updated": "2026-09-11T00:00:00Z"},
    {"title": "Royal Bank of Canada phishing campaign advisory (AV26-915)",
     "url": "https://cyber.gc.ca/y", "updated": "2026-09-12T00:00:00Z"},
]


@pytest.fixture(autouse=True)
def fake_caches(monkeypatch):
    monkeypatch.setitem(ci._CISA_KEV_CACHE, "data", CISA_FAKE_KEV)
    monkeypatch.setitem(ci._CCCS_CACHE, "entries", CCCS_FAKE_ENTRIES)
    yield
    ci._CISA_KEV_CACHE["data"] = None
    ci._CCCS_CACHE["entries"] = None


class TestCisaKevAmbiguousMatch:
    def test_single_distinctive_word_match_flagged_ambiguous(self):
        """The exact bug class: 'Shield Robotics Inc' -> distinctive word
        'shield' matching an unrelated 'Acme Shield Corp' entry via the
        OR-list, with no full-phrase match. Same mechanism that let
        'National' alone match 'National Instruments' before that
        particular word was excluded as generic."""
        result = ci.query_cisa_kev("Shield Robotics Inc")
        assert result["total"] == 1
        assert result["entries"][0]["ambiguous_match"] is True

    def test_genuine_multiword_phrase_match_not_ambiguous(self):
        result = ci.query_cisa_kev("Royal Bank of Canada")
        assert result["total"] == 1
        assert result["entries"][0]["ambiguous_match"] is False

    def test_single_word_vendor_name_always_flagged(self):
        """Even a clean match is flagged when the vendor name itself is a
        single word - phrase and word matching collapse to the same weak
        signal in that case."""
        result = ci.query_cisa_kev("Shield")
        assert result["total"] == 1
        assert result["entries"][0]["ambiguous_match"] is True


class TestCccsAmbiguousMatch:
    def test_single_distinctive_word_match_flagged_ambiguous(self):
        result = ci.query_cccs_advisories("Shield Robotics Inc")
        assert result["total"] == 1
        assert result["entries"][0]["ambiguous_match"] is True

    def test_genuine_multiword_phrase_match_not_ambiguous(self):
        result = ci.query_cccs_advisories("Royal Bank of Canada")
        assert result["total"] == 1
        assert result["entries"][0]["ambiguous_match"] is False


class TestGatherCyberIntelligenceSeverityCapping:
    def test_ambiguous_match_capped_at_elevated_with_caveat(self, monkeypatch):
        monkeypatch.setattr(ci, "query_nvd_cves", lambda v, **k: {"cves": [], "total": 0})
        result = ci.gather_cyber_intelligence("Shield Robotics Inc", domain="")
        gov_signals = [s for s in result["signals"] if s["category"] == "Government Advisory"]
        assert len(gov_signals) == 2  # one CISA KEV, one CCCS
        for s in gov_signals:
            assert s["severity"] == "Elevated"
            assert "verify this is genuinely about" in s["indicator"]

    def test_confident_match_keeps_full_severity_no_caveat(self, monkeypatch):
        monkeypatch.setattr(ci, "query_nvd_cves", lambda v, **k: {"cves": [], "total": 0})
        result = ci.gather_cyber_intelligence("Royal Bank of Canada", domain="")
        gov_signals = [s for s in result["signals"] if s["category"] == "Government Advisory"]
        assert len(gov_signals) == 2
        severities = {s["severity"] for s in gov_signals}
        assert severities == {"Critical", "High"}
        for s in gov_signals:
            assert "verify this is genuinely about" not in s["indicator"]

    def test_nvd_single_word_vendor_capped_at_elevated(self, monkeypatch):
        monkeypatch.setattr(ci, "query_nvd_cves", lambda v, **k: {
            "cves": [{
                "cve_id": "CVE-2026-9999", "description": "A flaw in Metro's checkout flow.",
                "cvss_base_score": 9.8, "published": "2026-01-01",
                "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9999",
                "source": "NVD (nvd.nist.gov)", "retrieved_at": "2026-01-01T00:00:00Z",
                "ambiguous_match": True,
            }],
            "total": 1,
        })
        monkeypatch.setattr(ci, "query_cisa_kev", lambda v: {"entries": [], "total": 0})
        monkeypatch.setattr(ci, "query_cccs_advisories", lambda v: {"entries": [], "total": 0})
        result = ci.gather_cyber_intelligence("Metro", domain="")
        cve_signals = [s for s in result["signals"] if s["category"] == "CVE Exposure"]
        assert len(cve_signals) == 1
        assert cve_signals[0]["severity"] == "Elevated"
        assert "verify this is genuinely about" in cve_signals[0]["indicator"]
