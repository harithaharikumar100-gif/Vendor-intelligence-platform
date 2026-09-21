"""
Tests for canlii_search.search_litigation's recency filtering and honest
date display.

Confirmed live bug: a search for "Royal Bank of Canada" litigation returned
Supreme Court cases from 1915, 1921, 1926, 1931, 1947, 1964, 1995, and 1997
- directly contradicting SK-VDD-001's explicit 36-month lookback window.
Root cause was compounded: (1) one of the two search queries had no year
constraint at all, and the other used hardcoded years that go stale over
time; (2) even with a query-level year hint, Serper still surfaces highly-
cited landmark cases outside it, and no client-side filter existed to catch
that; (3) the first attempt at a client-side filter used the existing
`citation` regex, which requires an ALL-CAPS court code and silently fails
to match CanLII's own internal citation format "1926 CanLII 32 (SCC)"
(mixed-case "CanLII") - exactly the format every stale case used, so
filtering on it let all of them through unfiltered; (4) cases with no
Serper-provided date were labeled "Recent" with zero evidence for that.
"""
import pytest

import canlii_search as cs


def _fake_hit(title, snippet="", link="https://www.canlii.org/en/ca/scc/doc/x"):
    return {"title": title, "snippet": snippet, "link": link, "date": ""}


@pytest.fixture(autouse=True)
def no_real_webpage_fetch(monkeypatch):
    """search_litigation fetches the top case's page for a richer summary -
    stub it out so tests never make a real network call."""
    monkeypatch.setattr(cs, "_webpage", lambda *a, **k: "")


class TestStaleCaseFiltering:
    def test_old_canlii_format_citation_is_excluded(self, monkeypatch):
        """The exact bug: 'YYYY CanLII NNNNN' format, mixed-case 'CanLII',
        which the pre-existing citation regex (ALL-CAPS court code only)
        cannot extract a year from at all."""
        old_hit = _fake_hit("1926 CanLII 32 (SCC) | Kuproski v. Royal Bank of Canada")
        monkeypatch.setattr(cs, "_serper", lambda q, n: [old_hit])
        result = cs.search_litigation("Royal Bank of Canada")
        assert result["total"] == 0

    def test_old_allcaps_citation_is_also_excluded(self, monkeypatch):
        old_hit = _fake_hit("Smith v. Acme Corp, 1998 ABCA 123")
        monkeypatch.setattr(cs, "_serper", lambda q, n: [old_hit])
        result = cs.search_litigation("Acme Corp")
        assert result["total"] == 0

    def test_recent_case_is_kept(self, monkeypatch):
        recent_hit = _fake_hit("2024 SCC 11 | Eurobank Ergasias SA v. Bombardier inc.")
        monkeypatch.setattr(cs, "_serper", lambda q, n: [recent_hit])
        result = cs.search_litigation("Bombardier")
        assert result["total"] == 1
        assert result["cases"][0]["date"] == "2024 SCC 11"

    def test_case_with_no_extractable_year_is_kept_not_dropped(self, monkeypatch):
        """No positive evidence of staleness -> kept, not excluded on a guess."""
        no_year_hit = _fake_hit("Royal Bank of Canada v. North American Life Assurance Co. - CanLII")
        monkeypatch.setattr(cs, "_serper", lambda q, n: [no_year_hit])
        result = cs.search_litigation("Royal Bank of Canada")
        assert result["total"] == 1

    def test_no_date_field_reports_unknown_not_recent(self, monkeypatch):
        """The exact bug: an empty Serper date field was fabricated into
        the claim "Recent" with zero supporting evidence."""
        hit = _fake_hit("Some Case With No Year Mentioned Anywhere In Title")
        monkeypatch.setattr(cs, "_serper", lambda q, n: [hit])
        result = cs.search_litigation("Some Vendor")
        assert result["cases"][0]["date"] == "Date unknown"


class TestSearchLitigationQueriesUseDynamicLookback:
    def test_queries_do_not_contain_hardcoded_years(self, monkeypatch):
        captured_queries = []

        def fake_serper(q, n):
            captured_queries.append(q)
            return []

        monkeypatch.setattr(cs, "_serper", fake_serper)
        cs.search_litigation("Some Vendor")
        assert len(captured_queries) == 2
        expected_clause = " OR ".join(
            str(y) for y in range(cs._MIN_LOOKBACK_YEAR, cs.datetime.utcnow().year + 1)
        )
        for q in captured_queries:
            assert expected_clause in q
            assert str(cs._MIN_LOOKBACK_YEAR) in q
