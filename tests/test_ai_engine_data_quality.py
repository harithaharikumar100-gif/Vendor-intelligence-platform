"""
Tests for two data-quality fixes to ai_engine.py, both found via code review
during a client-readiness audit (not yet reproduced live at the time of the
fix, unlike the escalation-guard bugs in test_ai_engine_escalation_guards.py):

- _detect_recent_attrition: the prior "Recent Attrition" key-person
  escalation counted DISTINCT ATTRITION KEYWORDS present anywhere in the raw
  scraped evidence blob, with no link to a specific person and no
  time-scoping despite the escalation message claiming "12-month lookback."
  One person described two ways ("resigned ... he later said he'd stepped
  down") would false-positive a "2+ C-suite exits" escalation, and a
  departure from years ago counted identically to a recent one. This
  requires each hit to be tied to a specific named person and, if a year is
  present nearby, that it not be stale.

- _repair_truncated_urls: _reputational_prompt hard-truncates its evidence
  to 800 chars, so a URL near that cutoff can come out chopped
  (confirmed live: "https://financialpost.com/news/judge-"), and the model
  echoes the truncated string as a citation. This repairs it deterministically
  when it's an unambiguous prefix of a known full URL, otherwise clears it.
"""
import ai_engine as ae


class TestDetectRecentAttrition:
    def _year(self, years_ago):
        return ae.datetime.utcnow().year - years_ago

    def test_two_distinct_people_with_departure_language_counted(self):
        persons = [{"name": "Jane Smith"}, {"name": "Bob Jones"}]
        evidence = "Jane Smith resigned last month. Bob Jones was fired shortly after."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 2
        assert set(names) == {"Jane Smith", "Bob Jones"}

    def test_one_person_described_two_ways_counts_once(self):
        """The exact bug: same person, two different attrition keywords near
        their name, must not be double-counted as two separate exits."""
        persons = [{"name": "John Chen"}]
        evidence = "John Chen resigned as CEO; sources say he had already stepped down informally weeks earlier."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 1
        assert names == ["John Chen"]

    def test_stale_year_near_the_mention_excludes_it(self):
        stale_year = self._year(20)
        persons = [{"name": "Jane Smith"}, {"name": "Bob Jones"}]
        evidence = (
            f"Jane Smith resigned in {stale_year} after a long tenure. "
            "Bob Jones was fired last month."
        )
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 1
        assert names == ["Bob Jones"]

    def test_recent_year_near_the_mention_is_counted(self):
        recent_year = self._year(1)
        persons = [{"name": "Jane Smith"}]
        evidence = f"Jane Smith resigned in {recent_year}."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 1

    def test_no_year_present_is_kept_not_dropped(self):
        """Same 'no positive evidence of staleness -> kept' philosophy as
        the CanLII recency fix elsewhere in this codebase."""
        persons = [{"name": "Jane Smith"}]
        evidence = "Jane Smith resigned amid controversy."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 1

    def test_person_with_no_departure_language_is_not_counted(self):
        persons = [{"name": "Jane Smith"}, {"name": "Bob Jones"}]
        evidence = "Jane Smith resigned. Bob Jones continues to lead the finance team."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 1
        assert names == ["Jane Smith"]

    def test_very_short_names_are_skipped_to_avoid_false_matches(self):
        persons = [{"name": "Al"}]
        evidence = "Al resigned from the board."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 0

    def test_empty_evidence_returns_zero(self):
        persons = [{"name": "Jane Smith"}]
        count, names = ae._detect_recent_attrition(persons, "")
        assert (count, names) == (0, [])

    def test_empty_persons_list_returns_zero(self):
        count, names = ae._detect_recent_attrition([], "Someone resigned. Someone else was fired.")
        assert (count, names) == (0, [])

    def test_case_insensitive_name_matching(self):
        persons = [{"name": "Jane Smith"}]
        evidence = "jane smith resigned last week."
        count, names = ae._detect_recent_attrition(persons, evidence)
        assert count == 1


class TestRepairTruncatedUrls:
    def test_truncated_url_repaired_from_known_full_url(self):
        """The exact bug reproduced live: a URL chopped mid-path."""
        parsed = {"articles": [{"headline": "x", "url": "https://financialpost.com/news/judge-"}]}
        known = ["https://financialpost.com/news/judge-dismisses-lawsuit-blackberry-ceo"]
        result = ae._repair_truncated_urls(parsed, known)
        assert result["articles"][0]["url"] == known[0]

    def test_ambiguous_prefix_match_is_cleared_not_guessed(self):
        parsed = {"articles": [{"headline": "x", "url": "https://example.com/news-"}]}
        known = [
            "https://example.com/news-a-story",
            "https://example.com/news-another-story",
        ]
        result = ae._repair_truncated_urls(parsed, known)
        assert result["articles"][0]["url"] == ""

    def test_no_matching_known_url_is_cleared(self):
        parsed = {"articles": [{"headline": "x", "url": "https://example.com/broken-"}]}
        result = ae._repair_truncated_urls(parsed, ["https://other.com/unrelated"])
        assert result["articles"][0]["url"] == ""

    def test_well_formed_url_is_left_alone(self):
        parsed = {"articles": [{"headline": "x", "url": "https://example.com/a-complete-article"}]}
        result = ae._repair_truncated_urls(parsed, [])
        assert result["articles"][0]["url"] == "https://example.com/a-complete-article"

    def test_empty_url_is_left_alone(self):
        parsed = {"articles": [{"headline": "x", "url": ""}]}
        result = ae._repair_truncated_urls(parsed, ["https://example.com/y"])
        assert result["articles"][0]["url"] == ""

    def test_underscore_truncation_signature_is_also_repaired(self):
        parsed = {"articles": [{"headline": "x", "url": "https://example.com/story_"}]}
        known = ["https://example.com/story_part_two"]
        result = ae._repair_truncated_urls(parsed, known)
        assert result["articles"][0]["url"] == known[0]

    def test_missing_articles_key_is_a_no_op(self):
        parsed = {"score": 0}
        result = ae._repair_truncated_urls(parsed, ["https://example.com"])
        assert result == {"score": 0}

    def test_non_list_articles_does_not_crash(self):
        parsed = {"articles": "not a list"}
        result = ae._repair_truncated_urls(parsed, [])
        assert result["articles"] == "not a list"

    def test_no_known_urls_at_all_clears_truncated_url(self):
        parsed = {"articles": [{"headline": "x", "url": "https://example.com/broken-"}]}
        result = ae._repair_truncated_urls(parsed, [])
        assert result["articles"][0]["url"] == ""
