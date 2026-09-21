"""
Tests for cyber_intel._word_match — the fix for a confirmed false-positive
bug where a vendor named "Metro" matched CVEs about an unrelated product
called "Metronome" purely via substring matching.
"""
import cyber_intel as ci


class TestWordMatch:
    def test_exact_word_matches(self):
        assert ci._word_match("Metro", "a vulnerability in Metro's checkout system") is True

    def test_substring_within_different_word_does_not_match(self):
        """The exact bug: 'metro' must not match inside 'metronome'."""
        assert ci._word_match("Metro", "plugins/mod_compression.lua in Lightwitch Metronome") is False

    def test_case_insensitive(self):
        assert ci._word_match("metro", "A vulnerability in METRO Inc systems") is True

    def test_no_match_for_unrelated_text(self):
        assert ci._word_match("Metro", "a vulnerability in Google Chrome") is False

    def test_empty_needle_never_matches(self):
        assert ci._word_match("", "any text here") is False

    def test_multi_word_needle_matches_as_phrase(self):
        assert ci._word_match("Royal Bank", "an incident affecting Royal Bank operations") is True

    def test_word_at_string_boundary_matches(self):
        assert ci._word_match("Metro", "Metro") is True
        assert ci._word_match("Metro", "issue in Metro") is True


class TestDistinctiveWords:
    def test_generic_words_excluded(self):
        """The exact bug: 'National' alone must not be usable to match an
        unrelated 'National Instruments' advisory against 'Canadian National
        Railway Company'."""
        words = ci._distinctive_words("Canadian National Railway Company")
        assert "national" not in words
        assert "canadian" not in words
        assert "company" not in words
        assert "railway" in words

    def test_falls_back_to_all_words_if_name_is_entirely_generic(self):
        assert ci._distinctive_words("National Group") == ["national", "group"]

    def test_single_distinctive_word_name_unaffected(self):
        assert ci._distinctive_words("Metro") == ["metro"]

    def test_short_words_still_dropped(self):
        assert "of" not in ci._distinctive_words("Bank of Canada")

