"""
Tests for the deterministic escalation guardrails added alongside the
score-consistency fix:

- _validate_breach_flag: confirmed live on two unrelated vendors (BlackBerry,
  Shopify) that the LLM can set recent_breach_flag=true off a generic,
  undated, unsourced "X has experienced a data breach in the past" item with
  no supporting signal - which then drives a client-facing "Confirmed Data
  Breach within the Past 12 Months" Section 10.1 escalation banner with
  nothing behind it. This only ever turns the flag OFF, never on.

- _dedupe_compliance_signals: confirmed live (BlackBerry run) that the model
  can return the same regulator ("OSFI") four times while dropping others
  entirely, instead of the one-row-per-regulator breakdown the sample report
  requires. This dedupes by authority deterministically.

- _dedupe_key_person_signals: confirmed live (BlackBerry run) that the model
  can return the exact same two executives twice each in "persons" - same
  duplication failure mode as compliance, just on a different array/key.

- _dedupe_cyber_signals: confirmed live (BlackBerry run) that cyber's
  "signals" array can carry the same identical entry twice back to back,
  with no "authority"/"name" field to key a dedupe on - keys on indicator
  text instead.

- _normalize_compliance_authorities: confirmed live (BlackBerry run) that
  the model can add a seventh, off-list regulator ("Ontario Securities
  Commission") alongside the six canonical ones, duplicating what the "CSA"
  entry is already defined to cover. Folds known CSA-member aliases into
  "CSA" before dedup runs.
"""
import ai_engine as ae


class TestNormalizeSeverities:
    def test_off_enum_severity_is_normalized_to_low(self):
        """The exact bug reproduced live: the model wrote severity "False"."""
        parsed = {"signals": [{"category": "Data Breach", "indicator": "no evidence found", "severity": "False"}]}
        result = ae._normalize_severities("cyber", parsed)
        assert result["signals"][0]["severity"] == "Low"

    def test_valid_severities_are_left_alone(self):
        parsed = {"signals": [
            {"severity": "Low"}, {"severity": "Elevated"}, {"severity": "High"}, {"severity": "Critical"},
        ]}
        result = ae._normalize_severities("cyber", parsed)
        assert [s["severity"] for s in result["signals"]] == ["Low", "Elevated", "High", "Critical"]

    def test_case_insensitive_valid_value_is_left_alone(self):
        parsed = {"signals": [{"severity": "low"}]}
        result = ae._normalize_severities("cyber", parsed)
        assert result["signals"][0]["severity"] == "low"

    def test_missing_severity_is_normalized_to_low(self):
        parsed = {"signals": [{"category": "Data Breach", "indicator": "x"}]}
        result = ae._normalize_severities("cyber", parsed)
        assert result["signals"][0]["severity"] == "Low"

    def test_works_across_all_five_array_keys(self):
        for cat, key in (("financial", "signals"), ("cyber", "signals"), ("compliance", "signals"),
                          ("reputation", "articles"), ("key_person", "persons")):
            parsed = {key: [{"severity": "Maybe"}]}
            result = ae._normalize_severities(cat, parsed)
            assert result[key][0]["severity"] == "Low"

    def test_missing_array_key_is_a_no_op(self):
        parsed = {"score": 10}
        result = ae._normalize_severities("cyber", parsed)
        assert result == {"score": 10}

    def test_non_list_array_does_not_crash(self):
        parsed = {"signals": "not a list"}
        result = ae._normalize_severities("cyber", parsed)
        assert result["signals"] == "not a list"


class TestValidateBreachFlag:
    def test_false_flag_is_left_alone(self):
        parsed = {"recent_breach_flag": False, "signals": []}
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False

    def test_true_flag_with_no_signals_is_cleared(self):
        """The exact bug: flag true, nothing backing it up."""
        parsed = {"recent_breach_flag": True, "signals": []}
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False

    def test_true_flag_with_unsourced_high_severity_breach_is_cleared(self):
        """The exact bug reproduced live: generic claim, no source."""
        parsed = {
            "recent_breach_flag": True,
            "signals": [
                {"category": "Data Breach", "indicator": "X has experienced a data breach in the past", "severity": "High", "sources": []},
            ],
        }
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False

    def test_true_flag_with_sourced_high_severity_breach_is_kept(self):
        parsed = {
            "recent_breach_flag": True,
            "signals": [
                {"category": "Data Breach", "indicator": "Named breach disclosed March 2026", "severity": "High", "sources": ["https://example.com/breach-notice"]},
            ],
        }
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is True

    def test_true_flag_with_sourced_critical_severity_breach_is_kept(self):
        parsed = {
            "recent_breach_flag": True,
            "signals": [
                {"category": "Data Breach", "indicator": "Named breach disclosed", "severity": "Critical", "sources": ["https://example.com/breach"]},
            ],
        }
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is True

    def test_true_flag_with_sourced_low_severity_breach_is_cleared(self):
        """Severity too low to justify the escalation, even if sourced."""
        parsed = {
            "recent_breach_flag": True,
            "signals": [
                {"category": "Data Breach", "indicator": "Minor historical incident", "severity": "Low", "sources": ["https://example.com/x"]},
            ],
        }
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False

    def test_true_flag_with_other_category_signal_is_cleared(self):
        """A sourced High CVE item doesn't itself justify the breach flag."""
        parsed = {
            "recent_breach_flag": True,
            "signals": [
                {"category": "CVE Exposure", "indicator": "CVE-2025-1234", "severity": "High", "sources": ["https://nvd.nist.gov/vuln/detail/CVE-2025-1234"]},
            ],
        }
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False

    def test_missing_signals_key_is_cleared(self):
        parsed = {"recent_breach_flag": True}
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False

    def test_non_list_signals_does_not_crash(self):
        parsed = {"recent_breach_flag": True, "signals": "not a list"}
        result = ae._validate_breach_flag(parsed)
        assert result["recent_breach_flag"] is False


class TestDedupeComplianceSignals:
    def test_duplicate_authorities_collapsed_to_one(self):
        """The exact bug reproduced live: OSFI returned four times."""
        parsed = {
            "signals": [
                {"authority": "OSFI", "action": "No findings", "severity": "Low"},
                {"authority": "OSFI", "action": "No findings", "severity": "Low"},
                {"authority": "OSFI", "action": "No findings", "severity": "Low"},
                {"authority": "FINTRAC", "action": "No findings", "severity": "Low"},
            ]
        }
        result = ae._dedupe_compliance_signals(parsed)
        authorities = [s["authority"] for s in result["signals"]]
        assert authorities == ["OSFI", "FINTRAC"]

    def test_case_and_whitespace_insensitive(self):
        parsed = {
            "signals": [
                {"authority": "osfi", "action": "a", "severity": "Low"},
                {"authority": " OSFI ", "action": "b", "severity": "Low"},
            ]
        }
        result = ae._dedupe_compliance_signals(parsed)
        assert len(result["signals"]) == 1

    def test_prefers_entry_with_sources_over_unsourced_duplicate(self):
        parsed = {
            "signals": [
                {"authority": "OSFI", "action": "No findings", "severity": "Low", "sources": []},
                {"authority": "OSFI", "action": "Clean AMP register search", "severity": "Low", "sources": ["https://osfi-bsif.gc.ca/x"]},
            ]
        }
        result = ae._dedupe_compliance_signals(parsed)
        assert len(result["signals"]) == 1
        assert result["signals"][0]["sources"] == ["https://osfi-bsif.gc.ca/x"]

    def test_preserves_order_of_first_appearance(self):
        parsed = {
            "signals": [
                {"authority": "CRTC", "action": "a", "severity": "Low"},
                {"authority": "OSFI", "action": "b", "severity": "Low"},
                {"authority": "CRTC", "action": "c", "severity": "Low"},
            ]
        }
        result = ae._dedupe_compliance_signals(parsed)
        authorities = [s["authority"] for s in result["signals"]]
        assert authorities == ["CRTC", "OSFI"]

    def test_no_regulator_duplication_across_six_named_authorities(self):
        parsed = {
            "signals": [
                {"authority": a, "action": "No findings", "severity": "Low"}
                for a in ["OSFI", "FINTRAC", "CSA", "OPC", "CRTC", "Competition Bureau"]
            ]
        }
        result = ae._dedupe_compliance_signals(parsed)
        assert len(result["signals"]) == 6

    def test_missing_signals_key_is_a_no_op(self):
        parsed = {"score": 0}
        result = ae._dedupe_compliance_signals(parsed)
        assert result == {"score": 0}

    def test_non_list_signals_does_not_crash(self):
        parsed = {"signals": "not a list"}
        result = ae._dedupe_compliance_signals(parsed)
        assert result["signals"] == "not a list"

    def test_entries_missing_authority_are_preserved_unmerged(self):
        parsed = {
            "signals": [
                {"action": "no authority given", "severity": "Low"},
                {"action": "also none", "severity": "Low"},
            ]
        }
        result = ae._dedupe_compliance_signals(parsed)
        assert len(result["signals"]) == 2


class TestDedupeKeyPersonSignals:
    def test_duplicate_persons_collapsed_to_one_each(self):
        """The exact bug reproduced live: John Chen and Richard Stiennon
        each listed twice, in the same order, back to back."""
        parsed = {
            "persons": [
                {"name": "John Chen", "role": "CEO", "flags": ["No OFAC/OSFI sanctions match found"]},
                {"name": "Richard Stiennon", "role": "Chairman", "flags": ["No OFAC/OSFI sanctions match found"]},
                {"name": "John Chen", "role": "CEO", "flags": ["No OFAC/OSFI sanctions match found"]},
                {"name": "Richard Stiennon", "role": "Chairman", "flags": ["No OFAC/OSFI sanctions match found"]},
            ]
        }
        result = ae._dedupe_key_person_signals(parsed)
        names = [p["name"] for p in result["persons"]]
        assert names == ["John Chen", "Richard Stiennon"]

    def test_case_and_whitespace_insensitive(self):
        parsed = {
            "persons": [
                {"name": "john chen", "flags": []},
                {"name": " John Chen ", "flags": []},
            ]
        }
        result = ae._dedupe_key_person_signals(parsed)
        assert len(result["persons"]) == 1

    def test_prefers_richer_entry_over_sparser_duplicate(self):
        parsed = {
            "persons": [
                {"name": "John Chen", "role": "CEO", "flags": [], "sources": []},
                {"name": "John Chen", "role": "CEO", "flags": ["No OFAC/OSFI sanctions match found"], "sources": ["https://example.com"]},
            ]
        }
        result = ae._dedupe_key_person_signals(parsed)
        assert len(result["persons"]) == 1
        assert result["persons"][0]["sources"] == ["https://example.com"]

    def test_preserves_order_of_first_appearance(self):
        parsed = {
            "persons": [
                {"name": "Richard Stiennon", "flags": []},
                {"name": "John Chen", "flags": []},
                {"name": "Richard Stiennon", "flags": []},
            ]
        }
        result = ae._dedupe_key_person_signals(parsed)
        names = [p["name"] for p in result["persons"]]
        assert names == ["Richard Stiennon", "John Chen"]

    def test_missing_persons_key_is_a_no_op(self):
        parsed = {"score": 0}
        result = ae._dedupe_key_person_signals(parsed)
        assert result == {"score": 0}

    def test_non_list_persons_does_not_crash(self):
        parsed = {"persons": "not a list"}
        result = ae._dedupe_key_person_signals(parsed)
        assert result["persons"] == "not a list"

    def test_entries_missing_name_are_preserved_unmerged(self):
        parsed = {
            "persons": [
                {"role": "no name given", "flags": []},
                {"role": "also none", "flags": []},
            ]
        }
        result = ae._dedupe_key_person_signals(parsed)
        assert len(result["persons"]) == 2


class TestDedupeCyberSignals:
    def test_duplicate_indicators_collapsed_to_one(self):
        """The exact bug reproduced live: the identical entry twice in a row."""
        parsed = {
            "signals": [
                {"category": "Cybersecurity Posture", "indicator": "BlackBerry has a strong cybersecurity posture", "severity": "Low"},
                {"category": "Cybersecurity Posture", "indicator": "BlackBerry has a strong cybersecurity posture", "severity": "Low"},
            ]
        }
        result = ae._dedupe_cyber_signals(parsed)
        assert len(result["signals"]) == 1

    def test_distinct_cves_are_never_collapsed(self):
        """Real CVE items must never be deduped away just for sharing a
        category - each has a unique CVE ID in its indicator text."""
        parsed = {
            "signals": [
                {"category": "CVE Exposure", "indicator": "CVE-2005-2341 (CVSS 7.5): some overflow"},
                {"category": "CVE Exposure", "indicator": "CVE-2005-2342 (CVSS 7.8): a different issue"},
            ]
        }
        result = ae._dedupe_cyber_signals(parsed)
        assert len(result["signals"]) == 2

    def test_case_and_whitespace_insensitive(self):
        parsed = {
            "signals": [
                {"indicator": "no evidence found"},
                {"indicator": " No Evidence Found "},
            ]
        }
        result = ae._dedupe_cyber_signals(parsed)
        assert len(result["signals"]) == 1

    def test_preserves_order_of_first_appearance(self):
        parsed = {
            "signals": [
                {"indicator": "b"},
                {"indicator": "a"},
                {"indicator": "b"},
            ]
        }
        result = ae._dedupe_cyber_signals(parsed)
        assert [s["indicator"] for s in result["signals"]] == ["b", "a"]

    def test_missing_signals_key_is_a_no_op(self):
        parsed = {"score": 0}
        result = ae._dedupe_cyber_signals(parsed)
        assert result == {"score": 0}

    def test_non_list_signals_does_not_crash(self):
        parsed = {"signals": "not a list"}
        result = ae._dedupe_cyber_signals(parsed)
        assert result["signals"] == "not a list"

    def test_entries_missing_indicator_are_preserved_unmerged(self):
        parsed = {"signals": [{"category": "a"}, {"category": "b"}]}
        result = ae._dedupe_cyber_signals(parsed)
        assert len(result["signals"]) == 2


class TestNormalizeComplianceAuthorities:
    def test_osc_is_folded_into_csa(self):
        """The exact bug reproduced live: a seventh 'Ontario Securities
        Commission' row alongside the six canonical regulators."""
        parsed = {"signals": [{"authority": "Ontario Securities Commission", "action": "x", "severity": "Low"}]}
        result = ae._normalize_compliance_authorities(parsed)
        assert result["signals"][0]["authority"] == "CSA"

    def test_known_csa_member_aliases_are_folded(self):
        for alias in ["OSC", "osc", "BCSC", "AMF", "British Columbia Securities Commission"]:
            parsed = {"signals": [{"authority": alias, "action": "x", "severity": "Low"}]}
            result = ae._normalize_compliance_authorities(parsed)
            assert result["signals"][0]["authority"] == "CSA", f"failed for alias {alias!r}"

    def test_canonical_authorities_are_left_alone(self):
        parsed = {"signals": [{"authority": a} for a in ["OSFI", "FINTRAC", "CSA", "OPC", "CRTC", "Competition Bureau"]]}
        result = ae._normalize_compliance_authorities(parsed)
        assert [s["authority"] for s in result["signals"]] == ["OSFI", "FINTRAC", "CSA", "OPC", "CRTC", "Competition Bureau"]

    def test_unrecognized_authority_is_left_alone(self):
        parsed = {"signals": [{"authority": "Some Other Regulator"}]}
        result = ae._normalize_compliance_authorities(parsed)
        assert result["signals"][0]["authority"] == "Some Other Regulator"

    def test_composes_with_dedupe_to_collapse_into_existing_csa_row(self):
        """End-to-end: an off-list OSC row and a canonical CSA row must
        collapse into a single CSA entry once both fixes run in sequence."""
        parsed = {
            "signals": [
                {"authority": "CSA", "action": "No findings", "severity": "Low", "sources": []},
                {"authority": "Ontario Securities Commission", "action": "No findings", "severity": "Low", "sources": ["https://osc.ca/x"]},
            ]
        }
        result = ae._dedupe_compliance_signals(ae._normalize_compliance_authorities(parsed))
        assert len(result["signals"]) == 1
        assert result["signals"][0]["authority"] == "CSA"

    def test_missing_signals_key_is_a_no_op(self):
        parsed = {"score": 0}
        result = ae._normalize_compliance_authorities(parsed)
        assert result == {"score": 0}

    def test_non_list_signals_does_not_crash(self):
        parsed = {"signals": "not a list"}
        result = ae._normalize_compliance_authorities(parsed)
        assert result["signals"] == "not a list"
