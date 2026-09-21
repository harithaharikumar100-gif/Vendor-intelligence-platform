"""
Tests for ai_engine._clamp_score_to_evidence - the deterministic backstop on
top of the score-consistency prompt fix (signals/persons/articles listed
before score, plus an explicit consistency instruction).

Confirmed live: even with that prompt fix, an LLM occasionally still returns
a score that doesn't match the severities it just listed - a real compliance
run scored 80 while every signal was Low/non-material, and a cyber run
scored 40 while every signal was Low, on otherwise-identical evidence that
correctly scored low on other attempts. This clamp caps the score at the
ceiling implied by the single worst severity actually reported, so a
residual LLM misfire can't produce an incoherent result - it only ever
lowers a score, never raises one.
"""
import ai_engine as ae


class TestClampScoreToEvidence:
    def test_all_low_severity_clamps_high_score_down(self):
        """The exact bug: score=80 with every signal Low severity."""
        parsed = {
            "score": 80,
            "signals": [
                {"authority": "OSFI", "severity": "Low"},
                {"authority": "FINTRAC", "severity": "Low"},
            ],
        }
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 24

    def test_score_already_within_ceiling_is_unchanged(self):
        parsed = {"score": 10, "signals": [{"severity": "Low"}]}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 10

    def test_one_critical_signal_allows_high_score(self):
        parsed = {
            "score": 95,
            "signals": [{"severity": "Low"}, {"severity": "Critical"}],
        }
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 95  # unchanged - Critical justifies it

    def test_elevated_severity_caps_at_49(self):
        parsed = {"score": 90, "signals": [{"severity": "Elevated"}]}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 49

    def test_high_severity_caps_at_74(self):
        parsed = {"score": 100, "signals": [{"severity": "High"}]}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 74

    def test_no_signals_leaves_score_untouched(self):
        parsed = {"score": 80, "signals": []}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 80

    def test_missing_array_key_leaves_score_untouched(self):
        parsed = {"score": 80}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 80

    def test_unrecognized_severity_values_are_ignored(self):
        parsed = {"score": 80, "signals": [{"severity": "Unknown"}, {"severity": ""}]}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == 80  # nothing usable to clamp against

    def test_works_for_reputation_articles_field(self):
        parsed = {"score": 90, "articles": [{"severity": "Low"}]}
        result = ae._clamp_score_to_evidence("reputation", parsed)
        assert result["score"] == 24

    def test_works_for_key_person_persons_field(self):
        parsed = {"score": 90, "persons": [{"severity": "Low"}]}
        result = ae._clamp_score_to_evidence("key_person", parsed)
        assert result["score"] == 24

    def test_works_for_cyber_signals_field(self):
        """The exact second bug: cyber scored 40 with every signal Low."""
        parsed = {"score": 40, "signals": [{"severity": "Low"}, {"severity": "Low"}]}
        result = ae._clamp_score_to_evidence("cyber", parsed)
        assert result["score"] == 24

    def test_works_for_financial_signals_field(self):
        parsed = {"score": 90, "signals": [{"severity": "Low"}]}
        result = ae._clamp_score_to_evidence("financial", parsed)
        assert result["score"] == 24

    def test_non_numeric_score_is_left_untouched(self):
        parsed = {"score": "not a number", "signals": [{"severity": "Low"}]}
        result = ae._clamp_score_to_evidence("compliance", parsed)
        assert result["score"] == "not a number"
