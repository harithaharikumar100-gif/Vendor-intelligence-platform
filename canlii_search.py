"""
canlii_search.py - CanLII Direct Litigation Search (SK-VDD-001 Section 6.2)
---------------------------------------------------------------------------
Provides real CanLII case law search beyond generic Google snippets:
- Searches CanLII (canlii.org) for vendor-related litigation
- Fetches top case pages for structured case data
- Extracts: case name, citation, date, court, summary

All calls are defensive — never raises; returns empty dict on any failure.
"""

import re
from datetime import datetime
from financial_fetcher import _serper, _webpage
import config

# Same lookback computation as scraper.py's _YEARS_CLAUSE, duplicated here
# (not imported - no circular-import risk, but these are genuinely just two
# small derived constants, not worth coupling this module to scraper.py for).
# Confirmed live: without ANY recency constraint here, a search for "Royal
# Bank of Canada" litigation returned Supreme Court cases from 1915, 1921,
# 1926, 1931, 1947, 1964, 1995, and 1997 - directly contradicting the SK-
# VDD-001 spec's explicit 36-month lookback window (Section 2.2/11), and
# silently corrupting the reputation dimension's evidence with irrelevant
# century-old case law a landmark-precedent-weighted search engine surfaces
# for any long-established institution.
_LOOKBACK_YEARS = max(1, config.LOOKBACK_MONTHS // 12)
_MIN_LOOKBACK_YEAR = datetime.utcnow().year - _LOOKBACK_YEARS


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        pass


# CanLII court code mapping extracted from URL paths
COURT_CODES = {
    "scc": "Supreme Court of Canada",
    "fct": "Federal Court",
    "fca": "Federal Court of Appeal",
    "onsc": "Ontario Superior Court",
    "onscdc": "Ontario Divisional Court",
    "onca": "Ontario Court of Appeal",
    "qccs": "Quebec Superior Court",
    "qcca": "Quebec Court of Appeal",
    "bcca": "BC Court of Appeal",
    "bcsc": "BC Supreme Court",
    "abca": "Alberta Court of Appeal",
    "abqb": "Alberta Court of King's Bench",
}


def search_litigation(vendor: str) -> dict:
    """Search CanLII for litigation involving the vendor."""
    results = {"cases": [], "total": 0, "source": "CanLII (canlii.org)"}
    try:
        years_clause = " OR ".join(str(y) for y in range(_MIN_LOOKBACK_YEAR, datetime.utcnow().year + 1))
        queries = [
            f'"{vendor}" site:canlii.org (lawsuit OR litigation OR "class action" OR "court" OR "tribunal") {years_clause}',
            f'"{vendor}" site:canlii.org (settlement OR "enforcement" OR "penalty" OR "injunction" OR "judgment") {years_clause}',
        ]

        hits = []
        seen_urls = set()
        for q in queries:
            for h in _serper(q, 8):
                url = h.get("link", "")
                if url and url not in seen_urls and "canlii.org" in url:
                    seen_urls.add(url)
                    hits.append(h)

        if not hits:
            _safe_print(f"  [~] CanLII: no litigation results for {vendor}")
            return results

        cases = []
        skipped_stale = 0
        for h in hits[:15]:
            title = h.get("title", "")
            snippet = h.get("snippet", "")
            url = h.get("link", "")
            date = h.get("date", "")

            # Extract court level from URL path
            court = ""
            m = re.search(r'/en/(?:ca/)?(\w+)/', url)
            if m:
                court = COURT_CODES.get(m.group(1), m.group(1).upper())

            # Extract citation from title (e.g. "2024 FC 123" or "2023 ONSC 4567")
            citation = ""
            m = re.search(r'(\d{4}\s+[A-Z]+\s+\d+)', title)
            if m:
                citation = m.group(1)

            # The query-level year hint above is a search-engine RANKING
            # signal, not a hard filter - Serper still returns highly-cited
            # landmark cases outside it for any long-established institution
            # (confirmed live: Royal Bank of Canada cases from 1915-1997).
            # A case's citation year is a real, structured fact, so it's
            # used as a deterministic filter here rather than trusting the
            # search query alone. This intentionally does NOT reuse the
            # `citation` field above - that regex requires an ALL-CAPS court
            # code (e.g. "SCC", "ONSC") and silently fails to match CanLII's
            # own internal citation format "1926 CanLII 32 (SCC)" (mixed-
            # case "CanLII"), which is exactly the format every stale case
            # in the confirmed live test used - so filtering only on
            # `citation` being non-empty missed every one of them. A case
            # with no extractable year at all is kept rather than dropped -
            # excluding only on a positive, confirmed "this is stale" signal.
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
            if year_match and int(year_match.group(1)) < _MIN_LOOKBACK_YEAR:
                skipped_stale += 1
                continue

            # Determine severity from snippet keywords
            sev = "Low"
            sev_text = (snippet + " " + title).lower()
            if any(k in sev_text for k in ["class action", "fraud", "criminal", "penalty", "injunction", "fine"]):
                sev = "High"
            elif any(k in sev_text for k in ["settlement", "violation", "enforcement", "sanction"]):
                sev = "Elevated"

            # "Recent" was a fabricated claim whenever Serper simply didn't
            # return a date field (common) - a real extracted year, when
            # available, is preferred; otherwise say plainly that it's
            # unknown rather than asserting recency with no evidence.
            display_date = date or citation or (year_match.group(1) if year_match else "") or "Date unknown"

            cases.append({
                "case_name": title[:200],
                "citation": citation,
                "court": court,
                "date": display_date,
                "summary": snippet[:300],
                "severity": sev,
                "url": url,
            })

        if skipped_stale:
            _safe_print(f"  [~] CanLII: excluded {skipped_stale} case(s) older than the {_LOOKBACK_YEARS}-year lookback window for {vendor}")

        results["cases"] = cases
        results["total"] = len(cases)

        # Fetch the top case page for a richer summary (limit to 1 to conserve API quota)
        if cases and cases[0]["url"]:
            page_text = _webpage(cases[0]["url"], 5000)
            if page_text and len(page_text) > 500:
                m = re.search(
                    r'(?:HEADNOTE|Summary|HELD|Overview)[:\s]*([^\n]{50,500})',
                    page_text, re.I,
                )
                if m:
                    cases[0]["detailed_summary"] = m.group(1).strip()[:400]

        _safe_print(f"  [✓] CanLII: {len(cases)} case(s) found for {vendor}")
    except Exception as e:
        _safe_print(f"  [!] CanLII search failed: {e}")
        results["error"] = str(e)[:100]

    return results
