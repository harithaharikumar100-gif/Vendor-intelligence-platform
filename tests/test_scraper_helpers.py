"""Tests for scraper.py's pure helper functions (no network calls)."""
import pytest

import scraper


class TestIsRecent12m:
    @pytest.mark.parametrize("date_str", ["3 days ago", "2 weeks ago", "11 months ago", "12 months ago"])
    def test_recent_relative_dates(self, date_str):
        assert scraper._is_recent_12m({"date": date_str}) is True

    @pytest.mark.parametrize("date_str", ["13 months ago", "2 years ago", "60 weeks ago"])
    def test_old_relative_dates(self, date_str):
        assert scraper._is_recent_12m({"date": date_str}) is False

    def test_current_year_absolute_date(self):
        assert scraper._is_recent_12m({"date": f"Jan 5, {scraper.CURRENT_YEAR}"}) is True

    def test_missing_date_never_assumed_recent(self):
        """No date at all must never be treated as recent — under-counting
        is the safe failure direction, not over-counting."""
        assert scraper._is_recent_12m({}) is False
        assert scraper._is_recent_12m({"date": ""}) is False

    def test_ambiguous_string_not_assumed_recent(self):
        assert scraper._is_recent_12m({"date": "some time ago"}) is False


class TestRelevant:
    def test_matches_when_vendor_name_present(self):
        hit = {"title": "Shopify announces new feature", "snippet": "", "url": "https://example.com"}
        assert scraper._relevant(hit, ["Shopify Inc.", "Shopify"]) is True

    def test_no_match_for_unrelated_result(self):
        hit = {"title": "Completely unrelated news story", "snippet": "about something else", "url": "https://example.com"}
        assert scraper._relevant(hit, ["Shopify Inc.", "Shopify"]) is False

    def test_short_words_in_variant_dont_force_match(self):
        # "of" (len 2) shouldn't count toward the match threshold on its own
        hit = {"title": "A completely unrelated headline", "snippet": "", "url": "https://x.com"}
        assert scraper._relevant(hit, ["Bank of Nova Scotia"]) is False


class TestIsDuplicateEvent:
    def test_near_identical_headline_is_duplicate(self):
        kept = [{"title": "Shopify announces record Q4 earnings beat"}]
        assert scraper._is_duplicate_event("Shopify announces record Q4 earnings beat", kept) is True

    def test_reworded_same_story_is_duplicate(self):
        kept = [{"title": "Shopify reports record fourth quarter earnings"}]
        assert scraper._is_duplicate_event("Shopify announces record fourth-quarter earnings", kept) is True

    def test_distinct_stories_not_flagged(self):
        kept = [{"title": "Shopify announces record Q4 earnings"}]
        assert scraper._is_duplicate_event("Shopify faces class action lawsuit over data breach", kept) is False

    def test_empty_title_never_matches(self):
        assert scraper._is_duplicate_event("", [{"title": "anything"}]) is False

    def test_empty_kept_list(self):
        assert scraper._is_duplicate_event("Some headline", []) is False


class TestIsTier1:
    def test_known_tier1_domain(self):
        assert scraper._is_tier1({"url": "https://www.cbc.ca/news/some-story"}) is True
        assert scraper._is_tier1({"url": "https://www.theglobeandmail.com/business/x"}) is True

    def test_unknown_domain_not_tier1(self):
        assert scraper._is_tier1({"url": "https://some-random-blog.example.com/post"}) is False

    def test_missing_url_not_tier1(self):
        assert scraper._is_tier1({}) is False


class TestDetectFrench:
    def test_clear_french_text_detected(self):
        text = "La société a été fondée dans le but de fournir des services pour les entreprises et le secteur"
        assert scraper._detect_french(text) is True

    def test_clear_english_text_not_detected(self):
        text = "The company was founded to provide services for the enterprise and technology sector"
        assert scraper._detect_french(text) is False

    def test_short_text_never_flagged(self):
        assert scraper._detect_french("Le CEO") is False

    def test_empty_text_not_flagged(self):
        assert scraper._detect_french("") is False

    def test_french_proper_noun_in_english_sentence_not_flagged(self):
        # A French company name inside an English sentence shouldn't trip this.
        text = "The company La Belle Provence announced strong results for the year"
        assert scraper._detect_french(text) is False


class TestStale:
    def test_recent_year_mention_not_stale(self):
        hit = {"date": "", "title": f"Event in {scraper.CURRENT_YEAR}", "snippet": ""}
        assert scraper._stale(hit) is False

    def test_old_year_only_is_stale(self):
        hit = {"date": "", "title": "Event in 2015", "snippet": "happened back then"}
        assert scraper._stale(hit) is True

    def test_no_year_mentioned_not_flagged_stale(self):
        hit = {"date": "", "title": "General company news", "snippet": "no dates mentioned"}
        assert scraper._stale(hit) is False
