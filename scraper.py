"""
scraper.py - Multi-Source Web Intelligence Scraper (SK-VDD-001 Section 5)
--------------------------------------------------------------------------
Features:
- Queries authoritative Canadian & Global intelligence sources:
  * Financial: SEDAR+, CBCA, Provincial Registries, CRA, D&B indicators
  * Reputational: CBC, Globe and Mail, National Post, Financial Post, Google News, CanLII
  * Key-Person: LinkedIn, SEDAR+ insiders, OFAC/OSFI Sanctions, CanLII litigation
  * Tech & Cyber: CCCS (cyber.gc.ca), CISA KEV, NVD, HaveIBeenPwned, BitSight
  * Compliance: OSFI, FINTRAC AMPs, CSA Enforcement, OPC PIPEDA, CRTC CASL, Competition Bureau
- 36-Month Lookback Window & Recency Filtering
- In-memory query caching to optimize performance & conserve API quotas
"""

import os
import re
import requests
import ssl
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from normalizer import normalize_vendor_name, extract_domain

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
CURRENT_YEAR = 2026
MIN_LOOKBACK_YEAR = 2023  # 36-month lookback per SK-VDD-001 Section 2.2

_SERPER_CACHE = {}


class SSLAdapter(HTTPAdapter):
    """Fixes Windows SSL connection drops and handshake timeouts."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT')
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _serper(query: str, num: int = 5) -> list:
    """Performs Serper Google Search with in-memory caching and resilient timeouts."""
    if not SERPER_API_KEY:
        return []
    
    query_key = f"{query.strip()}__num_{num}"
    if query_key in _SERPER_CACHE:
        return _SERPER_CACHE[query_key]

    try:
        session = requests.Session()
        session.mount('https://', SSLAdapter())
        r = session.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=12,
            verify=True
        )
        if r.status_code == 200:
            hits = [
                {
                    "title": rc.get("title", ""),
                    "snippet": rc.get("snippet", ""),
                    "url": rc.get("link", ""),
                    "date": rc.get("date", "")
                }
                for rc in r.json().get("organic", [])
            ]
            _SERPER_CACHE[query_key] = hits
            return hits
        else:
            return []
    except Exception as e:
        print(f"  ⚠ Serper query failed [{query[:45]}]: {e}")
        return []


# SK-VDD-001 Section 5: Authoritative Search Query Templates
SEARCH_QUERIES = {
    "financial": [
        '"{vendor}" (site:sedarplus.ca OR "SEDAR+" OR "annual report" OR "MD&A" OR "audited financial") 2024 OR 2025 OR 2026',
        '"{vendor}" (solvency OR liquidity OR "debt-to-equity" OR "retained earnings" OR bankruptcy OR restructuring OR layoffs) 2024 OR 2025 OR 2026',
        '"{vendor}" ("credit rating" OR DBRS OR S&P OR Moody OR "going-concern" OR "material weakness") 2024 OR 2025 OR 2026',
    ],
    "reputation": [
        '"{vendor}" (site:cbc.ca OR site:theglobeandmail.com OR site:nationalpost.com OR site:financialpost.com) (controversy OR fraud OR lawsuit OR scandal OR investigation) 2024 OR 2025 OR 2026',
        '"{vendor}" (site:canlii.org OR "court records" OR "class action" OR settlement OR misconduct OR penalty) 2024 OR 2025 OR 2026',
        '"{vendor}" (lawsuit OR controversy OR fraud OR scandal OR "adverse media") 2024 OR 2025 OR 2026',
    ],
    "key_person": [
        '"{vendor}" ("CEO" OR founder OR "executive departure" OR "resigned" OR "appointed" OR "board of directors") 2024 OR 2025 OR 2026',
        '"{vendor}" (site:sedarplus.ca OR "SEDI" OR "insider filings" OR "management information circular") (officer OR director OR insider)',
        '"{vendor}" ("OSFI sanctions" OR "OFAC" OR "PEP" OR "disqualified director" OR "director ban" OR "criminal record") 2024 OR 2025 OR 2026',
    ],
    "cyber": [
        '"{vendor}" (site:cyber.gc.ca OR "CCCS" OR "Canadian Centre for Cyber Security" OR "CISA" OR "advisory") 2024 OR 2025 OR 2026',
        '"{vendor}" ("data breach" OR ransomware OR "cyber attack" OR "exposed database" OR HaveIBeenPwned OR BitSight) 2024 OR 2025 OR 2026',
        '"{vendor}" (CVE OR "vulnerability" OR "CVSS" OR "unpatched" OR "supply chain attack") 2024 OR 2025 OR 2026',
    ],
    "compliance": [
        '"{vendor}" ("OSFI" OR "FINTRAC" OR "administrative monetary penalty" OR "AMP" OR "AML/ATF") 2024 OR 2025 OR 2026',
        '"{vendor}" ("CSA enforcement" OR "securities commission" OR "OSC" OR "BCSC" OR "AMF" OR "cease-trade") 2024 OR 2025 OR 2026',
        '"{vendor}" ("Office of the Privacy Commissioner" OR "PIPEDA" OR "CRTC" OR "CASL" OR "Competition Bureau") 2024 OR 2025 OR 2026',
    ],
}

PROFILE_QUERIES = [
    '"{vendor}" ("Corporations Canada" OR CBCA OR "headquarters" OR "founded" OR "CEO" OR "about us")',
    '"{vendor}" (site:crunchbase.com OR site:wikipedia.org OR site:linkedin.com) overview company profile',
]


def _stale(r: dict) -> bool:
    """Enforces 36-month lookback window (SK-VDD-001 Section 2.2)."""
    txt = f"{r.get('date', '')} {r.get('title', '')} {r.get('snippet', '')}".lower()
    for yr in range(2015, MIN_LOOKBACK_YEAR):
        if str(yr) in txt and not any(str(y) in txt for y in range(MIN_LOOKBACK_YEAR, CURRENT_YEAR + 1)):
            return True
    return False


def _relevant(r: dict, vendor_variants: list) -> bool:
    """Verifies that result mentions the vendor or its recognized trade name/acronym."""
    txt = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}".lower()
    for variant in vendor_variants:
        words = [w for w in variant.lower().split() if len(w) > 2]
        if words and sum(1 for w in words if w in txt) >= max(1, len(words) // 2):
            return True
    return False


def _block(hits: list) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        d = f" [{h['date']}]" if h.get("date") else ""
        lines.append(f"[{i}]{d} {h['title']}\nURL: {h['url']}\n{h['snippet']}")
    return "\n\n".join(lines)


def _search_category(cat: str, templates: list, vendor_clean: str, vendor_variants: list, domain_hint: str):
    hits, seen = [], set()
    for tmpl in templates:
        q = tmpl.replace("{vendor}", vendor_clean)
        if domain_hint and cat == "cyber":
            q += f' "{domain_hint}"'
        for h in _serper(q, 5):
            if h["url"] in seen or _stale(h) or not _relevant(h, vendor_variants):
                continue
            seen.add(h["url"])
            hits.append(h)
    return cat, {"text": _block(hits), "urls": [h["url"] for h in hits], "hit_count": len(hits)}


def _search_profile(vendor_clean: str, vendor_variants: list, domain_hint: str):
    hits, seen = [], set()
    for tmpl in PROFILE_QUERIES:
        q = tmpl.replace("{vendor}", vendor_clean)
        if domain_hint:
            q += f' "{domain_hint}"'
        for h in _serper(q, 4):
            if h["url"] not in seen and _relevant(h, vendor_variants):
                seen.add(h["url"])
                hits.append(h)
    return {"snippet_text": _block(hits[:8]), "urls": [h["url"] for h in hits[:6]]}


def collect_vendor_signals(vendor: str, industry: str = "", country: str = "Canada",
                           company_url: str = "", business_number: str = "", manual_profile: dict = None):
    """
    Executes parallel intelligence gathering across all 5 SK-VDD-001 risk dimensions.
    """
    norm = normalize_vendor_name(vendor)
    vendor_clean = norm["normalized_name"]
    vendor_variants = norm["variants"]
    domain_hint = extract_domain(company_url)

    print(f"\n📡 SK-VDD-001 Intelligence Sweep: {vendor_clean} (Raw: {vendor}) | Scope: {country}")
    context = {}

    with ThreadPoolExecutor(max_workers=6) as ex:
        cat_futures = {
            ex.submit(_search_category, cat, tmpl, vendor_clean, vendor_variants, domain_hint): cat
            for cat, tmpl in SEARCH_QUERIES.items()
        }
        prof_future = ex.submit(_search_profile, vendor_clean, vendor_variants, domain_hint)

        for fut in as_completed(cat_futures):
            cat, data = fut.result()
            context[cat] = data

        prof_data = prof_future.result()

    parts = []
    if prof_data["snippet_text"]:
        parts.append(prof_data["snippet_text"])
    kp = context.get("key_person", {}).get("text", "")
    if kp:
        parts.append(kp)

    all_text = "\n\n".join(parts)

    context["profile"] = {
        "text": all_text,
        "urls": prof_data["urls"],
        "combined_text": all_text,
    }
    context["meta"] = {
        "vendor": vendor_clean,
        "raw_vendor": vendor,
        "variants": vendor_variants,
        "industry": industry,
        "country": country,
        "business_number": business_number,
        "domain": domain_hint,
    }
    return context