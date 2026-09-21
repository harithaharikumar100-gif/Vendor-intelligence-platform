"""
Tests for fetch_financial_and_profile's field_sources output and merge
priority. Every network-touching sub-function is monkeypatched so these
never hit real APIs.

Confirmed live bug: a Serper regex match in _scrape_profile populated
"founded" before the Wikipedia/Wikidata lookup ever ran, and the merge only
filled Wikipedia data into GAPS - so a structured, deterministic Wikidata
fact could never override an already-filled lower-confidence guess, even
though it's strictly more authoritative. yfinance already got this right for
employees/headquarters/ceo; this locks in the same behavior for a Wikidata
"founded" hit.
"""
import financial_fetcher as ff


def _patch_common(monkeypatch, *, scrape=({}, {}), ceo=("", ""), wiki=({}, {}), yf=None, ticker=""):
    monkeypatch.setattr(ff, "_scrape_profile", lambda *a, **k: scrape)
    monkeypatch.setattr(ff, "_fetch_ceo", lambda *a, **k: ceo)
    monkeypatch.setattr(ff, "_wikipedia_financials", lambda *a, **k: wiki)
    monkeypatch.setattr(ff, "_find_ticker", lambda *a, **k: ticker)
    monkeypatch.setattr(ff, "_yfinance", lambda *a, **k: yf or {})


class TestFieldSourcesMergePriority:
    def test_wikidata_founded_overrides_earlier_web_scrape_value(self, monkeypatch):
        _patch_common(
            monkeypatch,
            scrape=({"founded": "1922"}, {"founded": "web_scrape"}),
            wiki=({"founded": "1919"}, {"founded": "wikidata"}),
        )
        _, profile, sources = ff.fetch_financial_and_profile("Canadian National Railway Company")
        assert profile["founded"] == "1919"
        assert sources["founded"] == "wikidata"

    def test_wikipedia_extract_does_not_override_existing_scrape_value(self, monkeypatch):
        """Two similarly-weak text matches - first one in should stay, since
        neither is more authoritative than the other."""
        _patch_common(
            monkeypatch,
            scrape=({"headquarters": "Toronto, Canada"}, {"headquarters": "web_scrape"}),
            wiki=({"headquarters": "Montreal, QC"}, {"headquarters": "wikipedia_extract"}),
        )
        _, profile, sources = ff.fetch_financial_and_profile("Some Vendor")
        assert profile["headquarters"] == "Toronto, Canada"
        assert sources["headquarters"] == "web_scrape"

    def test_wikipedia_fills_a_genuine_gap(self, monkeypatch):
        _patch_common(
            monkeypatch,
            scrape=({}, {}),
            wiki=({"founder": "William Mackenzie"}, {"founder": "wikipedia_extract"}),
        )
        _, profile, sources = ff.fetch_financial_and_profile("Some Vendor")
        assert profile["founder"] == "William Mackenzie"
        assert sources["founder"] == "wikipedia_extract"

    def test_yfinance_overrides_scrape_and_wikipedia_for_employees_hq_ceo(self, monkeypatch):
        _patch_common(
            monkeypatch,
            scrape=({"employees": "50", "headquarters": "Toronto, Canada"}, {"employees": "web_scrape", "headquarters": "web_scrape"}),
            wiki=({"employees": "10000"}, {"employees": "wikipedia_extract"}),
            ticker="CNR.TO",
            yf={"employees": "23,825", "headquarters": "Montreal, QC, Canada", "ceo": "Tracy A. Robinson"},
        )
        _, profile, sources = ff.fetch_financial_and_profile("Canadian National Railway Company", ticker="CNR.TO")
        assert profile["employees"] == "23,825"
        assert sources["employees"] == "yfinance"
        assert profile["headquarters"] == "Montreal, QC, Canada"
        assert sources["headquarters"] == "yfinance"
        assert profile["ceo"] == "Tracy A. Robinson"
        assert sources["ceo"] == "yfinance"

    def test_ceo_from_dedicated_fetcher_is_tagged(self, monkeypatch):
        _patch_common(monkeypatch, ceo=("Tobias Lütke", "llm_estimate"))
        _, profile, sources = ff.fetch_financial_and_profile("Shopify")
        assert profile["ceo"] == "Tobias Lütke"
        assert sources["ceo"] == "llm_estimate"

    def test_llm_estimate_from_scrape_fallback_is_tagged(self, monkeypatch):
        _patch_common(
            monkeypatch,
            scrape=({"founded": "1999"}, {"founded": "llm_estimate"}),
        )
        _, profile, sources = ff.fetch_financial_and_profile("Some Vendor")
        assert profile["founded"] == "1999"
        assert sources["founded"] == "llm_estimate"
