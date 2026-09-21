"""
Tests for frameworks.py — the negation-aware keyword matching is the part
most likely to silently misfire (a false "evidence_of_concern" is a serious,
reputationally damaging claim per SK-VDD-001 Section 9.3), so this covers
the exact false-positive/negative cases found and fixed during development.
"""
import pytest

import frameworks


class TestNegationDetection:
    def test_plain_negation_same_sentence(self):
        assert frameworks._is_negated("no material findings were reported", 3)

    def test_negation_word_too_far_back_different_sentence(self):
        text = "no issues here. enforcement action was taken"
        idx = text.find("enforcement action")
        # The negation is in a PRIOR sentence, must not leak across the boundary.
        assert not frameworks._is_negated(text, idx)

    def test_no_negation_present(self):
        text = "a consent order and enforcement action were issued"
        idx = text.find("enforcement action")
        assert not frameworks._is_negated(text, idx)


class TestAssessFramework:
    def test_enforcement_action_negated_reads_as_evidence_found(self):
        """The exact bug caught live: 'No recent public enforcement actions'
        must NOT be flagged as evidence_of_concern."""
        text = "no recent public enforcement actions or penalties reported"
        results = frameworks.assess_framework("osfi_e13", text)
        item = next(r for r in results if r["principle_id"] == "enforcement_history")
        assert item["status"] == "evidence_found"

    def test_genuine_enforcement_action_flagged_as_concern(self):
        text = "the regulator issued a consent order and enforcement action"
        results = frameworks.assess_framework("osfi_e13", text)
        item = next(r for r in results if r["principle_id"] == "enforcement_history")
        assert item["status"] == "evidence_of_concern"

    def test_no_evidence_reports_not_disclosed(self):
        text = "the company sells software to enterprise customers"
        results = frameworks.assess_framework("osfi_e13", text)
        for item in results:
            assert item["status"] == "not_disclosed_in_available_sources"
            assert item["matched_keyword"] is None

    def test_positive_polarity_match_is_evidence_found(self):
        text = "the board maintains an independent audit committee"
        results = frameworks.assess_framework("osfi_corporate_governance", text)
        item = next(r for r in results if r["principle_id"] == "independent_risk_committee")
        assert item["status"] == "evidence_found"

    def test_unknown_framework_id_returns_empty(self):
        assert frameworks.assess_framework("not_a_real_framework", "anything") == []

    def test_empty_corpus_never_fabricates(self):
        for principle in frameworks.assess_framework("osfi_e13", ""):
            assert principle["status"] == "not_disclosed_in_available_sources"


class TestAssessAll:
    def test_maps_to_correct_dimension(self):
        kp_result = frameworks.assess_all("key_person", "some text")
        assert len(kp_result) == 1
        assert kp_result[0]["framework_id"] == "osfi_corporate_governance"

        comp_result = frameworks.assess_all("compliance", "some text")
        comp_ids = {fw["framework_id"] for fw in comp_result}
        assert comp_ids == {"osfi_e13", "fintrac_guidance", "opc_pipeda_guidelines"}

    def test_unmapped_dimension_returns_empty(self):
        assert frameworks.assess_all("financial", "some text") == []


class TestFintracAndOpcFrameworks:
    def test_fintrac_amp_negated_reads_as_evidence_found(self):
        text = "no fintrac penalty on record for this entity"
        results = frameworks.assess_framework("fintrac_guidance", text)
        item = next(r for r in results if r["principle_id"] == "amp_history")
        assert item["status"] == "evidence_found"

    def test_fintrac_compliance_officer_found(self):
        results = frameworks.assess_framework("fintrac_guidance", "the firm has a dedicated compliance officer")
        item = next(r for r in results if r["principle_id"] == "compliance_officer_appointed")
        assert item["status"] == "evidence_found"

    def test_opc_privacy_officer_found(self):
        results = frameworks.assess_framework("opc_pipeda_guidelines", "the company appointed a chief privacy officer")
        item = next(r for r in results if r["principle_id"] == "accountability")
        assert item["status"] == "evidence_found"

    def test_opc_genuine_finding_flagged(self):
        text = "the opc finding concluded the company violated pipeda"
        results = frameworks.assess_framework("opc_pipeda_guidelines", text)
        item = next(r for r in results if r["principle_id"] == "pipeda_finding_history")
        assert item["status"] == "evidence_of_concern"
