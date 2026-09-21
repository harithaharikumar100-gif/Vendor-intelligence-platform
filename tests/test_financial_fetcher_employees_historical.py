"""
Tests for the employee-count regex's historical-context exclusion and
largest-of-matches selection, in both _scrape_profile and
_wikipedia_financials.

Confirmed live bug: for McCain Foods (~20,000 employees today), the only
"X employees" mention findable in real scraped Wikipedia/search text was
"in their first year of production, the company hired 30 employees" - a
real sentence, but describing the 1957 founding year, not current headcount.
Reporting "30" as the vendor's employee count was confidently wrong by
roughly three orders of magnitude.
"""
import financial_fetcher as ff


class TestScrapeProfileEmployeesHistoricalContext:
    def test_founding_era_mention_excluded_when_no_alternative(self, monkeypatch):
        monkeypatch.setattr(ff, "_webpage", lambda *a, **k: (
            "McCain Foods Limited is a Canadian multinational frozen food company. "
            "In their first year of production, the company hired 30 employees "
            "and grossed over $150,000 in sales."
        ))
        monkeypatch.setattr(ff, "_serper", lambda *a, **k: [])
        monkeypatch.setattr(ff, "_groq", lambda *a, **k: "")
        p, src = ff._scrape_profile("McCain Foods Limited")
        assert "employees" not in p
        assert "employees" not in src

    def test_current_mention_preferred_over_founding_era_mention(self, monkeypatch):
        monkeypatch.setattr(ff, "_webpage", lambda *a, **k: (
            "McCain Foods Limited is a Canadian multinational frozen food company. "
            "In their first year of production, the company hired 30 employees. "
            "Today the company employs approximately 20000 employees worldwide."
        ))
        monkeypatch.setattr(ff, "_serper", lambda *a, **k: [])
        monkeypatch.setattr(ff, "_groq", lambda *a, **k: "")
        p, src = ff._scrape_profile("McCain Foods Limited")
        assert p.get("employees") == "20000"
        assert src.get("employees") == "web_scrape"

    def test_clean_current_mention_still_works(self, monkeypatch):
        monkeypatch.setattr(ff, "_webpage", lambda *a, **k: (
            "Some Vendor is a company. The company employs 7600 employees across its global operations."
        ))
        monkeypatch.setattr(ff, "_serper", lambda *a, **k: [])
        monkeypatch.setattr(ff, "_groq", lambda *a, **k: "")
        p, src = ff._scrape_profile("Some Vendor")
        assert p.get("employees") == "7600"
        assert src.get("employees") == "web_scrape"


class TestWikipediaFinancialsEmployeesHistoricalContext:
    def test_founding_era_mention_excluded(self, monkeypatch):
        def fake_get(url, **kwargs):
            class R:
                status_code = 200
                def json(self):
                    return {
                        "title": "Test Co",
                        "extract": "Initially the firm had just 12 employees before rapid growth.",
                        "wikibase_item": "",
                    }
            return R()
        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Test Co")
        assert "employees" not in result
        assert "employees" not in sources
