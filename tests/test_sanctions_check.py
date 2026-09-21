"""
Tests for sanctions_check.py. Pre-populates the module's in-memory SDN
cache directly so tests never hit the real network, and stay deterministic.
"""
import pytest

import sanctions_check as sc

FAKE_SDN_ROWS = [
    {"ent_num": "1001", "name": "ZAWAHIRI, Ayman al", "sdn_type": "individual",
     "program": "SDGT", "remarks": "aka test record"},
    {"ent_num": "1002", "name": "EXAMPLE CORRUPT HOLDINGS LTD", "sdn_type": "entity",
     "program": "MAGNIT", "remarks": ""},
]


@pytest.fixture(autouse=True)
def fake_sdn_cache(monkeypatch):
    """Ensure every test in this file uses a fixed fake list, never the network."""
    monkeypatch.setitem(sc._SDN_CACHE, "rows", FAKE_SDN_ROWS)
    monkeypatch.setitem(sc._SDN_CACHE, "fetched_at", "2026-01-01T00:00:00Z")
    yield
    sc._SDN_CACHE["rows"] = None


class TestSearchSdn:
    def test_real_match_found(self):
        matches = sc.search_sdn("Ayman al Zawahiri")
        assert len(matches) == 1
        assert matches[0]["ent_num"] == "1001"

    def test_single_common_word_does_not_match(self):
        """A person coincidentally sharing one word with a record must NOT
        be flagged — this is the false-positive case the module exists to avoid."""
        assert sc.search_sdn("David Beck") == []

    def test_single_word_query_never_matches(self):
        assert sc.search_sdn("Beck") == []

    def test_entity_name_match(self):
        matches = sc.search_sdn("Example Corrupt Holdings Ltd")
        assert len(matches) == 1
        assert matches[0]["ent_num"] == "1002"

    def test_unrelated_name_no_match(self):
        assert sc.search_sdn("Tobias Lutke") == []

    def test_empty_query(self):
        assert sc.search_sdn("") == []


class TestNormalizeName:
    def test_strips_stopwords_and_short_tokens(self):
        tokens = sc._normalize_name("The ABC Corp Inc")
        assert "the" not in tokens
        assert "corp" not in tokens
        assert "inc" not in tokens

    def test_flips_lastname_comma_firstname(self):
        tokens = sc._normalize_name("SMITH, John")
        assert "smith" in tokens
        assert "john" in tokens


class TestLoadSdnTypeParsing:
    """OFAC's raw SDN.csv uses a '-0-' placeholder for a blank type field
    (business entities, not individuals/vessels/aircraft). Confirmed live
    against the real feed: .strip("-") alone turns that into the literal
    string "0", which is truthy, so the "entity" fallback never fired and
    every entity-type record was labeled sdn_type="0" instead."""

    def test_dash_zero_dash_placeholder_becomes_entity(self, monkeypatch):
        sc._SDN_CACHE["rows"] = None

        class FakeResponse:
            status_code = 200
            text = "36,AEROCARIBBEAN AIRLINES,-0-,CUBA\n"

        monkeypatch.setattr(sc.requests, "get", lambda *a, **k: FakeResponse())
        rows = sc._load_sdn()
        assert rows[0]["sdn_type"] == "entity"

    def test_real_type_value_passes_through_unchanged(self, monkeypatch):
        sc._SDN_CACHE["rows"] = None

        class FakeResponse:
            status_code = 200
            text = "1001,ZAWAHIRI Ayman al,individual,SDGT\n"

        monkeypatch.setattr(sc.requests, "get", lambda *a, **k: FakeResponse())
        rows = sc._load_sdn()
        assert rows[0]["sdn_type"] == "individual"
