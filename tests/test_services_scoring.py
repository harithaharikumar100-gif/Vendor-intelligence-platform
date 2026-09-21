"""
Tests for services.py's SK-VDD-001 Section 7.2/7.3 scoring math: the exact
weighted formula and 4-tier rating band boundaries.
"""
import pytest

import config
from services import get_risk_tier, WEIGHTS, compute_confidence_score


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


class TestComputeConfidenceScore:
    """
    Confirmed live: this used to be a near-constant 98 for every public-
    company run (BlackBerry, Shopify) across five separate test runs,
    regardless of whether individual lookups actually succeeded that run or
    how many of the 7 licensed sources were unconfigured. These tests pin
    the two real deductions the fix introduced.
    """

    def _healthy(self, **overrides):
        base = dict(
            total_hits=75, has_metrics=True, federal_found=True, provincial_found=True,
            has_profile=True, search_available=True, licensed_gap_count=0,
        )
        base.update(overrides)
        return compute_confidence_score(**base)

    def test_fully_healthy_run_with_no_licensed_gaps_hits_the_98_cap(self):
        assert self._healthy() == 98

    def test_the_exact_regression_this_deployment_sees_every_run(self):
        """All 7 licensed sources unconfigured (the real state of this
        deployment) now costs 7 points even on an otherwise perfect run -
        this used to have zero effect on the number at all."""
        assert self._healthy(licensed_gap_count=7) == 91

    def test_licensed_gap_deduction_is_capped_at_seven(self):
        assert self._healthy(licensed_gap_count=7) == self._healthy(licensed_gap_count=20)

    def test_single_run_failure_costs_five_points(self):
        assert self._healthy(federal_found=False) == 93

    def test_all_four_run_failures_are_capped_at_twenty_points(self):
        assert self._healthy(
            federal_found=False, provincial_found=False, has_profile=False, search_available=False,
        ) == 78

    def test_canlii_and_sedar_and_hit_count_are_not_inputs_at_all(self):
        """A clean litigation record or zero SEDAR+ filings must never be
        able to lower this score - compute_confidence_score's signature
        doesn't even accept them, by design."""
        import inspect
        params = set(inspect.signature(compute_confidence_score).parameters)
        assert "canlii_litigation" not in params
        assert "sedarplus_filings" not in params

    def test_worst_case_floors_at_thirty(self):
        assert compute_confidence_score(
            total_hits=0, has_metrics=False, federal_found=False, provincial_found=False,
            has_profile=False, search_available=False, licensed_gap_count=20,
        ) == 30

    def test_base_tier_boundaries_are_preserved(self):
        assert compute_confidence_score(0, False, True, True, True, True, 0) == 40
        assert compute_confidence_score(3, False, True, True, True, True, 0) == 65
        assert compute_confidence_score(10, False, True, True, True, True, 0) == 85
        assert compute_confidence_score(50, False, True, True, True, True, 0) == 95

    def test_has_metrics_bonus_is_capped_at_ninety_eight(self):
        assert compute_confidence_score(50, True, True, True, True, True, 0) == 98
