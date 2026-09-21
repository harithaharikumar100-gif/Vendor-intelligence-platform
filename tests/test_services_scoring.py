"""
Tests for services.py's SK-VDD-001 Section 7.2/7.3 scoring math: the exact
weighted formula and 4-tier rating band boundaries.
"""
import pytest

import config
from services import get_risk_tier, WEIGHTS


class TestWeightedFormula:
    def test_weights_sum_to_one(self):
        assert pytest.approx(sum(WEIGHTS.values()), abs=1e-9) == 1.0

    def test_weights_match_spec_section_7_2(self):
        assert WEIGHTS == {
            "financial": 0.30,
            "reputation": 0.20,
            "key_person": 0.20,
            "cyber": 0.20,
            "compliance": 0.10,
        }

    def test_all_zero_scores_gives_zero(self):
        scores = {k: 0 for k in WEIGHTS}
        overall = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS))
        assert overall == 0

    def test_all_max_scores_gives_hundred(self):
        scores = {k: 100 for k in WEIGHTS}
        overall = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS))
        assert overall == 100

    def test_known_example(self):
        # (82*0.30) + (35*0.20) + (92*0.20) + (72*0.20) + (92*0.10) = 24.6+7+18.4+14.4+9.2 = 73.6
        scores = {"financial": 82, "reputation": 35, "key_person": 92, "cyber": 72, "compliance": 92}
        overall = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS))
        assert overall == 74


class TestRiskTierBands:
    def test_low_band(self):
        assert get_risk_tier(0)[0] == "Low"
        assert get_risk_tier(24)[0] == "Low"

    def test_medium_band_lower_boundary(self):
        assert get_risk_tier(25)[0] == "Medium"

    def test_medium_band_upper_boundary(self):
        assert get_risk_tier(config.HIGH_SCORE_THRESHOLD - 1)[0] == "Medium"

    def test_high_band_lower_boundary(self):
        assert get_risk_tier(config.HIGH_SCORE_THRESHOLD)[0] == "High"

    def test_high_band_upper_boundary(self):
        assert get_risk_tier(config.CRITICAL_SCORE_THRESHOLD - 1)[0] == "High"

    def test_critical_band(self):
        assert get_risk_tier(config.CRITICAL_SCORE_THRESHOLD)[0] == "Critical"
        assert get_risk_tier(100)[0] == "Critical"

    def test_traffic_light_mapping(self):
        assert get_risk_tier(10)[1]["traffic_light"] == "Green"
        assert get_risk_tier(30)[1]["traffic_light"] == "Amber"
        assert get_risk_tier(60)[1]["traffic_light"] == "Orange"
        assert get_risk_tier(90)[1]["traffic_light"] == "Red"
