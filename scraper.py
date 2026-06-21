"""
scraper.py  v3
--------------
- All 5 categories + profile run in ONE parallel round (unchanged)
- Deep fetch REMOVED (handled by financial_fetcher)
- Profile queries trimmed to 2 (faster)
- Returns combined_text for small-company description fallback
"""

# scraper.py

import os, re, requests, ssl
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
CURRENT_YEAR   = 2026
MIN_YEAR       = 2023

# ── SSL Adapter (fixes Windows SSL EOF error) ─────────────────────────────
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT')
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

# ── replace your existing _serper function with this ─────────────────────
def _serper(query: str, num: int = 6) -> list:
    if not SERPER_API_KEY:
        return []
    try:
        session = requests.Session()
        session.mount('https://', SSLAdapter())
        r = session.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=14,
            verify=True
        )
        return [
            {"title": rc.get("title",""), "snippet": rc.get("snippet",""),
             "url": rc.get("link",""),    "date":    rc.get("date","")}
            for rc in r.json().get("organic", [])
        ]
    except Exception as e:
        print(f"  ⚠  Serper: {e}")
        return []

# ... rest of your scraper.py stays exactly the same

SEARCH_QUERIES = {
    "financial": [
        '"{vendor}" {country} financial losses layoffs debt bankruptcy 2024 OR 2025',
        '"{vendor}" {city} revenue decline funding failed earnings 2024 OR 2025',
    ],
    "reputation": [
        '"{vendor}" {country} lawsuit scandal controversy fraud 2024 OR 2025',
        '"{vendor}" {city} employee complaint discrimination backlash 2024 OR 2025',
    ],
    "cyber": [
        '"{vendor}" {country} data breach hack ransomware cyberattack 2024 OR 2025',
        '"{vendor}" {city} security vulnerability exposed database 2024 OR 2025',
    ],
    "compliance": [
        '"{vendor}" {country} regulatory fine penalty GDPR violation sanctions 2024 OR 2025',
        '"{vendor}" {city} government investigation compliance failure 2024 OR 2025',
    ],
    "key_person": [
        '"{vendor}" {country} CEO founder executive resign departure layoff 2024 OR 2025',
        '"{vendor}" {city} leadership change management restructuring 2024 OR 2025',
    ],
}

# Lean — only 2 queries, no deep fetch here
PROFILE_QUERIES = [
    '"{vendor}" {city} {country} founded CEO founder headquarters about company',
    '"{vendor}" site:crunchbase.com OR site:tracxn.com OR site:wikipedia.org about',
]


def _stale(r: dict) -> bool:
    txt = f"{r.get('date','')} {r.get('title','')} {r.get('snippet','')}".lower()
    for yr in range(2018, MIN_YEAR):
        if str(yr) in txt and not any(str(y) in txt for y in range(MIN_YEAR, CURRENT_YEAR+1)):
            return True
    return False

def _relevant(r: dict, vendor: str) -> bool:
    words = [w for w in vendor.lower().split() if len(w) > 2]
    txt   = f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}".lower()
    return sum(1 for w in words if w in txt) >= max(1, len(words)//2)

def _block(hits: list) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        d = f" [{h['date']}]" if h.get("date") else ""
        lines.append(f"[{i}]{d} {h['title']}\nURL: {h['url']}\n{h['snippet']}")
    return "\n\n".join(lines)

def _parse_location(country: str) -> tuple:
    p = [x.strip() for x in country.split(",")]
    return (p[0], p[-1]) if len(p) >= 2 else ("", country.strip())


def _search_category(cat, templates, vendor, country_clean, city, industry, url_hint):
    hits, seen = [], set()
    for tmpl in templates:
        q = (tmpl
             .replace("{vendor}", vendor)
             .replace("{country}", country_clean)
             .replace("{city}", city or country_clean)
             .replace("{industry}", industry))
        if url_hint: q += url_hint
        for h in _serper(q, 6):
            if h["url"] in seen or _stale(h) or not _relevant(h, vendor): continue
            seen.add(h["url"])
            hits.append(h)
    print(f"  ✅ {cat}: {len(hits)} hits")
    return cat, {"text": _block(hits), "urls": [h["url"] for h in hits], "hit_count": len(hits)}


def _search_profile(vendor, city, country_clean, url_hint):
    
    hits, seen = [], set()
    for tmpl in PROFILE_QUERIES:
        q = (tmpl
             .replace("{vendor}", vendor)
             .replace("{city}", city or country_clean)
             .replace("{country}", country_clean))
        if url_hint: q += url_hint
        for h in _serper(q, 5):
            if h["url"] not in seen and _relevant(h, vendor):
                seen.add(h["url"])
                hits.append(h)
    print(f"  ✅ profile: {len(hits)} hits")
    return {"snippet_text": _block(hits[:10]), "urls": [h["url"] for h in hits[:8]]}


def _manual_block(manual: dict) -> str:
    if not manual: return ""
    lines = ["--- User-provided company details ---"]
    for key, label in [("ceo","CEO"),("founder","Founder"),("founded","Founded"),
                        ("headquarters","Headquarters"),("employees","Employees"),("description","About")]:
        v = manual.get(key,"").strip()
        if v: lines.append(f"{label}: {v}")
    return "\n".join(lines) if len(lines) > 1 else ""


def collect_vendor_signals(vendor, industry, country, company_url="", manual_profile=None):
    city, country_clean = _parse_location(country)
    url_hint = ""
    if company_url:
        domain   = company_url.replace("https://","").replace("http://","").split("/")[0]
        url_hint = f' "{domain}"'

    print(f"\n📡 {vendor} | {industry} | {city or country_clean}\n")
    context = {}

    with ThreadPoolExecutor(max_workers=6) as ex:
        cat_futures = {
            ex.submit(_search_category, cat, tmpl, vendor, country_clean, city, industry, url_hint): cat
            for cat, tmpl in SEARCH_QUERIES.items()
        }
        prof_future = ex.submit(_search_profile, vendor, city, country_clean, url_hint)

        for fut in as_completed(cat_futures):
            cat, data = fut.result()
            context[cat] = data

        prof_data = prof_future.result()

    manual_text = _manual_block(manual_profile or {})
    parts = []
    if manual_text:                   parts.append(manual_text)
    if prof_data["snippet_text"]:     parts.append(prof_data["snippet_text"])
    kp = context.get("key_person",{}).get("text","")
    if kp:                            parts.append(kp)

    # combined_text for small-company description fallback
    all_text = "\n\n".join(parts)

    context["profile"] = {
        "text":         all_text,
        "urls":         prof_data["urls"],
        "has_manual":   bool(manual_text),
        "has_deep":     False,
        "combined_text": all_text,   # used by financial_fetcher._describe_small_company
    }
    context["meta"] = {
        "vendor":      vendor, "industry":    industry,
        "country":     country_clean, "city": city,
        "company_url": company_url,  "has_manual": bool(manual_text),
    }
    return context