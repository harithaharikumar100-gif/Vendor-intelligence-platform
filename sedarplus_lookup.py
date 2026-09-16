"""
sedarplus_lookup.py - SEDAR+ Direct Filing Search (SK-VDD-001 Section 6.1)
------------------------------------------------------------------------
Provides real SEDAR+ filing search beyond generic Google snippets:
- Searches SEDAR+ (sedarplus.ca) for vendor regulatory filings
- Extracts: filing type, filing date, document description, URL

All calls are defensive — never raises; returns empty dict on any failure.
"""

import re
from financial_fetcher import _serper, _webpage


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        pass


FILING_TYPES = {
    "annual": "Annual Financial Statements",
    "audited": "Audited Annual Financial Statements",
    "interim": "Interim Financial Statements",
    "md&a": "Management Discussion & Analysis",
    "annual information form": "Annual Information Form (AIF)",
    "material change": "Material Change Report",
    "proxy": "Management Proxy Circular",
    "prospectus": "Prospectus",
    "news release": "News Release",
    "insider": "Insider Report",
    "early warning": "Early Warning Report",
    "financial statements": "Financial Statements",
    "quarterly": "Quarterly Financial Statements",
    "information circular": "Information Circular",
}


def _classify_filing(text: str) -> str:
    """Classify a filing based on its title/snippet text."""
    tl = text.lower()
    for keyword, label in FILING_TYPES.items():
        if keyword in tl:
            return label
    return "Other Regulatory Filing"


def search_filings(vendor: str, ticker: str = "") -> dict:
    """Search SEDAR+ for regulatory filings by the vendor."""
    results = {"filings": [], "total": 0, "source": "SEDAR+ (sedarplus.ca)"}
    try:
        queries = [
            f'"{vendor}" site:sedarplus.ca 2024 OR 2025 OR 2026',
            f'"{vendor}" ("SEDAR+" OR "sedarplus") ("financial statements" OR "MD&A" OR "annual report" OR "proxy" OR "AIF") 2024 OR 2025',
        ]
        if ticker:
            queries.append(f'"{ticker}" site:sedarplus.ca filing')

        hits = []
        seen_urls = set()
        for q in queries:
            for h in _serper(q, 8):
                url = h.get("link", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    hits.append(h)

        if not hits:
            _safe_print(f"  [~] SEDAR+: no filing results for {vendor}")
            return results

        filings = []
        for h in hits[:15]:
            title = h.get("title", "")
            snippet = h.get("snippet", "")
            url = h.get("link", "")
            date = h.get("date", "")
            combined = f"{title} {snippet}"

            filing_type = _classify_filing(combined)

            m = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}\s+\w+\s+\d{4})', combined)
            if m:
                date = m.group(1)

            filings.append({
                "filing_type": filing_type,
                "title": title[:200],
                "date": date or "Recent",
                "description": snippet[:300],
                "url": url,
            })

        results["filings"] = filings
        results["total"] = len(filings)

        # Fetch the top filing page for more detail (limit to 1 to conserve API quota)
        if filings and "sedarplus.ca" in filings[0]["url"]:
            page_text = _webpage(filings[0]["url"], 5000)
            if page_text and len(page_text) > 300:
                m = re.search(
                    r'(?:Filing Type|Document Type|Type)[:\s]+([^\n<]{5,80})',
                    page_text, re.I,
                )
                if m:
                    filings[0]["filing_type"] = m.group(1).strip()[:80]

                m = re.search(
                    r'(?:Filing Date|Date)[:\s]+(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}\s+\w+\s+\d{4})',
                    page_text, re.I,
                )
                if m:
                    filings[0]["date"] = m.group(1)

        _safe_print(f"  [✓] SEDAR+: {len(filings)} filing(s) found for {vendor}")
    except Exception as e:
        _safe_print(f"  [!] SEDAR+ search failed: {e}")
        results["error"] = str(e)[:100]

    return results
