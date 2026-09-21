"""
Tests for financial_fetcher._wikipedia_financials' founding-year extraction
and its companion source-confidence tags.

Confirmed live bug: the Wikipedia REST summary endpoint's "extract" is just
the lead paragraph, which frequently never states a founding year at all
(e.g. Canadian National Railway's real extract has none). When the regex
missed, the pipeline fell through to an LLM free-recall guess, which produced
two different answers (1919, then 1922 - only one correct) across two
otherwise-identical live runs of the same vendor. The fix queries Wikidata's
structured P571 ("inception") property via the wikibase_item id the same
summary response already returns, before ever falling back to regex/LLM, and
tags the result "wikidata" vs. "wikipedia_extract" so callers can tell a
structured fact apart from a text-pattern match.
"""
import financial_fetcher as ff


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


def _summary_response(extract="", wikibase_item="Q624798"):
    return _FakeResponse(200, {
        "title": "Canadian National Railway",
        "extract": extract,
        "wikibase_item": wikibase_item,
    })


def _wikidata_response(qid="Q624798", year="+1919-06-06T00:00:00Z"):
    return _FakeResponse(200, {
        "entities": {qid: {"claims": {"P571": [
            {"mainsnak": {"datavalue": {"value": {"time": year}}}}
        ]}}}
    })


class TestFoundedYearFromWikidata:
    def test_wikidata_inception_used_when_extract_has_no_founding_year(self, monkeypatch):
        """The exact bug: a lead paragraph with zero founding-year language
        must still resolve a correct, deterministic founded year via Wikidata,
        tagged as such."""
        def fake_get(url, **kwargs):
            if "wikidata.org" in url:
                return _wikidata_response()
            return _summary_response(extract="A Canadian Class I freight railway headquartered in Montreal.")

        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Canadian National Railway Company")
        assert result.get("founded") == "1919"
        assert sources.get("founded") == "wikidata"

    def test_wikidata_takes_priority_over_extract_regex(self, monkeypatch):
        """Even when the extract DOES contain a (possibly wrong/ambiguous)
        founding phrase, the structured Wikidata value should win."""
        def fake_get(url, **kwargs):
            if "wikidata.org" in url:
                return _wikidata_response(year="+1919-06-06T00:00:00Z")
            return _summary_response(extract="Founded in 1922 as a Crown corporation.")

        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Canadian National Railway Company")
        assert result.get("founded") == "1919"
        assert sources.get("founded") == "wikidata"

    def test_falls_back_to_extract_regex_when_no_wikibase_item(self, monkeypatch):
        def fake_get(url, **kwargs):
            return _summary_response(extract="Founded in 2006 in Ottawa.", wikibase_item="")

        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Shopify")
        assert result.get("founded") == "2006"
        assert sources.get("founded") == "wikipedia_extract"

    def test_falls_back_to_extract_regex_when_wikidata_lookup_fails(self, monkeypatch):
        def fake_get(url, **kwargs):
            if "wikidata.org" in url:
                return _FakeResponse(500, {})
            return _summary_response(extract="Established in 2010 in Toronto.")

        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Some Vendor")
        assert result.get("founded") == "2010"
        assert sources.get("founded") == "wikipedia_extract"

    def test_no_founded_key_when_nothing_available_and_no_crash(self, monkeypatch):
        def fake_get(url, **kwargs):
            if "wikidata.org" in url:
                return _FakeResponse(404, {})
            return _summary_response(extract="A company with no dates mentioned.", wikibase_item="")

        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Nonexistent Vendor")
        assert "founded" not in result
        assert "founded" not in sources

    def test_malformed_wikidata_response_does_not_crash(self, monkeypatch):
        def fake_get(url, **kwargs):
            if "wikidata.org" in url:
                return _FakeResponse(200, {"entities": {}})
            return _summary_response(extract="No founding info here.")

        monkeypatch.setattr(ff.requests, "get", fake_get)
        result, sources = ff._wikipedia_financials("Canadian National Railway Company")
        assert "founded" not in result
        assert "founded" not in sources
