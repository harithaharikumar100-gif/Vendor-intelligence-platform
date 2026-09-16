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
from financial_fetcher import _serper, _webpage


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
        queries = [
            f'"{vendor}" site:canlii.org (lawsuit OR litigation OR "class action" OR "court" OR "tribunal") 2024 OR 2025 OR 2026',
            f'"{vendor}" site:canlii.org (settlement OR "enforcement" OR "penalty" OR "injunction" OR "judgment")',
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

            # Determine severity from snippet keywords
            sev = "Low"
            sev_text = (snippet + " " + title).lower()
            if any(k in sev_text for k in ["class action", "fraud", "criminal", "penalty", "injunction", "fine"]):
                sev = "High"
            elif any(k in sev_text for k in ["settlement", "violation", "enforcement", "sanction"]):
                sev = "Elevated"

            cases.append({
                "case_name": title[:200],
                "citation": citation,
                "court": court,
                "date": date or "Recent",
                "summary": snippet[:300],
                "severity": sev,
                "url": url,
            })

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
