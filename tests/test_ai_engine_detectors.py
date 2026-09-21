"""
Tests for ai_engine.py's deterministic (not-LLM-discretion) detectors.
These guard Critical-severity claims, so the false-positive cases matter as
much as the true-positive ones.
"""
import ai_engine


class TestFinancialRedFlags:
    def test_going_concern_detected(self):
        flags = ai_engine._detect_financial_red_flags("the auditor expressed substantial doubt about going concern")
        assert flags["going_concern"] is True

    def test_material_weakness_detected(self):
        flags = ai_engine._detect_financial_red_flags("a material weakness in internal control was identified")
        assert flags["material_weakness"] is True

    def test_clean_text_no_flags(self):
        flags = ai_engine._detect_financial_red_flags("the company reported strong quarterly earnings")
        assert flags["going_concern"] is False
        assert flags["material_weakness"] is False

    def test_empty_text(self):
        flags = ai_engine._detect_financial_red_flags("")
        assert flags == {"going_concern": False, "material_weakness": False}


class TestDissolutionStatus:
    def test_dissolved_status_detected(self):
        text = "CORPORATIONS CANADA: Status=Dissolved"
        assert ai_engine._detect_dissolution_status(text) is True

    def test_receivership_detected(self):
        text = "the company was placed into receivership last year"
        assert ai_engine._detect_dissolution_status(text) is True

    def test_struck_detected(self):
        text = "the corporation was struck from the register for non-compliance"
        assert ai_engine._detect_dissolution_status(text) is True

    def test_negated_dissolution_not_flagged(self):
        """The exact false-positive class this was built to avoid — a false
        dissolution claim is as serious as a false sanctions match."""
        text = "there are no dissolution notices on file for this entity"
        assert ai_engine._detect_dissolution_status(text) is False

    def test_negated_receivership_not_flagged(self):
        text = "the company confirmed it is not in receivership"
        assert ai_engine._detect_dissolution_status(text) is False

    def test_active_status_not_flagged(self):
        text = "CORPORATIONS CANADA: Status=Active, Business Number=123456789"
        assert ai_engine._detect_dissolution_status(text) is False

    def test_empty_text_not_flagged(self):
        assert ai_engine._detect_dissolution_status("") is False
