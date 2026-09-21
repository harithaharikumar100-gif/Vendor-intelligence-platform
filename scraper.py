"""
scraper.py - Multi-Source Web Intelligence Scraper (SK-VDD-001 Section 5)
--------------------------------------------------------------------------
Features:
- Windows cp1252 safe logging
- Queries authoritative Canadian & Global intelligence sources:
  * Financial: SEDAR+, CBCA, Provincial Registries, CRA, D&B indicators, financial distress
  * Reputational: CBC, Globe and Mail, National Post, Financial Post, Google News, CanLII court cases
  * Key-Person: LinkedIn, SEDAR+ insiders, OFAC/OSFI Sanctions, CanLII litigation, executive exits
  * Tech & Cyber: CCCS (cyber.gc.ca), CISA KEV, NVD, HaveIBeenPwned, BitSight, CVEs, ransomware
  * Compliance: OSFI, FINTRAC AMPs, CSA Enforcement, OPC PIPEDA, CRTC CASL, Competition Bureau
- In-memory query caching to optimize performance & conserve API quotas
"""

import os
import re
import time
import threading
import requests
import ssl
from difflib import SequenceMatcher
from datetime import datetime
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from normalizer import normalize_vendor_name, extract_domain
import config

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()

# Intelligence horizon per SK-VDD-001 Section 2.2 / Section 11 lookback_months
# (configurable, default 36 months). Computed from the current date rather than
# hardcoded so the window doesn't silently go stale as real time passes.
_NOW = datetime.utcnow()
CURRENT_YEAR = _NOW.year
_LOOKBACK_YEARS = max(1, config.LOOKBACK_MONTHS // 12)
MIN_LOOKBACK_YEAR = _NOW.year - _LOOKBACK_YEARS

_SERPER_CACHE = {}
# collect_vendor_signals() runs all 5 dimensions concurrently in a
# ThreadPoolExecutor, and each one calls _serper() — so this cache and the
# search-status flag below are genuinely accessed from multiple threads at
# once within a single vendor analysis, not just a theoretical concern.
_CACHE_LOCK = threading.Lock()

# Section 10.2 "Intelligence Run Failure Handling": a quota-exhausted or
# misconfigured Serper key must not silently look identical to "searched and
# found nothing" — every prior signal in this codebase treated them the same,
# which meant the whole platform could run on LLM narrative alone with no
# report-visible indication that live search grounding was missing this run.
_SEARCH_STATUS = {"available": True, "reason": ""}
_STATUS_LOCK = threading.Lock()


def _mark_unavailable(reason: str):
    with _STATUS_LOCK:
        _SEARCH_STATUS["available"] = False
        _SEARCH_STATUS["reason"] = reason
    _safe_print(f"  [!] SEARCH GROUNDING UNAVAILABLE: {reason}")


def _mark_available():
    with _STATUS_LOCK:
        _SEARCH_STATUS["available"] = True
        _SEARCH_STATUS["reason"] = ""


def search_grounding_status() -> dict:
    """Current Serper availability, as observed by the most recent call(s)."""
    with _STATUS_LOCK:
        return dict(_SEARCH_STATUS)


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


class SSLAdapter(HTTPAdapter):
    """Fixes Windows SSL connection drops and handshake timeouts."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT')
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _serper(query: str, num: int = 5) -> list:
    """Performs Serper Google Search with 3-retry exponential backoff and in-memory caching (SK-VDD-001 Section 10.2)."""
    if not SERPER_API_KEY:
        _mark_unavailable("SERPER_API_KEY not configured")
        return []

    query_key = f"{query.strip()}__num_{num}"
    with _CACHE_LOCK:
        if query_key in _SERPER_CACHE:
            return _SERPER_CACHE[query_key]

    for attempt in range(3):
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
                _mark_available()
                hits = [
                    {
                        "title": rc.get("title", ""),
                        "snippet": rc.get("snippet", ""),
                        "url": rc.get("link", ""),
                        "date": rc.get("date", "")
                    }
                    for rc in r.json().get("organic", [])
                ]
                with _CACHE_LOCK:
                    _SERPER_CACHE[query_key] = hits
                return hits
            elif r.status_code in (429, 500, 502, 503) and attempt < 2:
                backoff = 2 ** attempt  # 1s, 2s
                _safe_print(f"  [~] Serper retry {attempt+1}/3 for [{query[:45]}] in {backoff}s...")
                time.sleep(backoff)
                continue
            elif r.status_code in (400, 401, 403):
                # Definitive account-level failure (bad/expired key, quota
                # exhausted) — not something a retry or a different query
                # will fix, unlike the transient statuses above.
                try:
                    detail = r.json().get("message", r.text[:120])
                except Exception:
                    detail = r.text[:120]
                _mark_unavailable(f"Serper HTTP {r.status_code} — {detail}")
                return []
            else:
                _mark_unavailable(f"Serper HTTP {r.status_code}")
                return []
        except Exception as e:
            if attempt < 2:
                backoff = 2 ** attempt
                _safe_print(f"  [~] Serper error retry {attempt+1}/3 [{query[:45]}]: {e} — retrying in {backoff}s...")
                time.sleep(backoff)
                continue
            _mark_unavailable(f"Serper request error — {e}")
            return []

    _mark_unavailable("Serper exhausted all retries (429/5xx)")
    return []


# SK-VDD-001 Section 5: Authoritative Search Query Templates.
# "{years}" is substituted at query time with the rolling lookback window
# (Section 11 lookback_months, default 36 months) instead of hardcoded years.
SEARCH_QUERIES = {
    "financial": [
        '"{vendor}" (site:sedarplus.ca OR "SEDAR+" OR "annual report" OR "MD&A" OR "audited financial") {years}',
        '"{vendor}" (solvency OR liquidity OR "debt-to-equity" OR "retained earnings" OR bankruptcy OR restructuring OR layoffs OR loss) {years}',
        '"{vendor}" ("credit rating" OR DBRS OR S&P OR Moody OR "going-concern" OR "material weakness" OR "default") {years}',
    ],
    "reputation": [
        '"{vendor}" (site:cbc.ca OR site:theglobeandmail.com OR site:nationalpost.com OR site:financialpost.com) (controversy OR fraud OR lawsuit OR scandal OR investigation) {years}',
        '"{vendor}" (site:canlii.org OR "court records" OR "class action" OR settlement OR misconduct OR penalty OR litigation) {years}',
        '"{vendor}" (lawsuit OR controversy OR fraud OR scandal OR "adverse media" OR dispute OR boycott) {years}',
    ],
    "key_person": [
        '"{vendor}" ("CEO" OR founder OR "executive departure" OR "resigned" OR "appointed" OR "board of directors" OR "management") {years}',
        '"{vendor}" (site:sedarplus.ca OR "SEDI" OR "insider filings" OR "management information circular") (officer OR director OR insider)',
        '"{vendor}" ("OSFI sanctions" OR "OFAC" OR "PEP" OR "disqualified director" OR "director ban" OR "criminal record" OR "fraud") {years}',
        # Targeted at OSFI Corporate Governance Guideline evidence (board risk
        # oversight, independent risk committee, chair/CEO separation, code of
        # conduct, whistleblower policy, succession plan) — without this, the
        # governance evidence corpus rarely contains this vocabulary at all.
        '"{vendor}" ("risk committee" OR "audit committee" OR "board oversight" OR "code of conduct" OR "code of ethics" OR "whistleblower policy" OR "succession plan" OR "independent chair")',
    ],
    "cyber": [
        '"{vendor}" (site:cyber.gc.ca OR "CCCS" OR "Canadian Centre for Cyber Security" OR "CISA" OR "advisory" OR "vulnerability") {years}',
        '"{vendor}" ("data breach" OR ransomware OR "cyber attack" OR "exposed database" OR HaveIBeenPwned OR BitSight OR leak) {years}',
        '"{vendor}" (CVE OR "vulnerability" OR "CVSS" OR "unpatched" OR "supply chain attack" OR outage) {years}',
    ],
    "compliance": [
        '"{vendor}" ("OSFI" OR "FINTRAC" OR "administrative monetary penalty" OR "AMP" OR "AML/ATF" OR enforcement) {years}',
        '"{vendor}" ("CSA enforcement" OR "securities commission" OR "OSC" OR "BCSC" OR "AMF" OR "cease-trade" OR penalty) {years}',
        '"{vendor}" ("Office of the Privacy Commissioner" OR "PIPEDA" OR "CRTC" OR "CASL" OR "Competition Bureau" OR violation) {years}',
        # Targeted at OSFI Guideline E-13 evidence (a named compliance function,
        # a formal compliance framework/program, monitoring, and board
        # reporting) — the enforcement-focused queries above rarely surface
        # this vocabulary since it describes an ongoing function, not an event.
        '"{vendor}" ("chief compliance officer" OR "compliance officer" OR "compliance framework" OR "compliance program" OR "regulatory compliance management")',
    ],
}

_YEARS_CLAUSE = " OR ".join(str(y) for y in range(MIN_LOOKBACK_YEAR, CURRENT_YEAR + 1))

PROFILE_QUERIES = [
    '"{vendor}" ("Corporations Canada" OR CBCA OR "headquarters" OR "founded" OR "CEO" OR "about us")',
    '"{vendor}" (site:crunchbase.com OR site:wikipedia.org OR site:linkedin.com) overview company profile',
    '"{vendor}" corporate headquarters founder established employees',
]

# Section 6.2.1/6.2.2: "Tier-1 sources (major newspapers, wire services)
# carry higher weight than Tier-2 (blogs, forums)... Tier-1 outlets carry
# higher weight than unverified online sources." Deliberately a short,
# high-confidence list of major Canadian and international wire/newspaper
# domains — not an attempt to classify every outlet, just to distinguish
# "credible major outlet" from "everything else."
TIER1_DOMAINS = {
    "cbc.ca", "theglobeandmail.com", "nationalpost.com", "financialpost.com",
    "globalnews.ca", "ctvnews.ca", "thestar.com", "reuters.com", "bloomberg.com",
    "wsj.com", "nytimes.com", "apnews.com", "bbc.com", "canlii.org",
}


def _is_tier1(hit: dict) -> bool:
    url = (hit.get("url") or "").lower()
    return any(d in url for d in TIER1_DOMAINS)


def _stale(r: dict) -> bool:
    """Enforces 36-month lookback window on risk incidents."""
    txt = f"{r.get('date', '')} {r.get('title', '')} {r.get('snippet', '')}".lower()
    # If the snippet is strictly about pre-2023 events and mentions no recent years
    has_recent = any(str(y) in txt for y in range(MIN_LOOKBACK_YEAR, CURRENT_YEAR + 1))
    if not has_recent and any(str(yr) in txt for yr in range(2010, MIN_LOOKBACK_YEAR)):
        return True
    return False


def _is_recent_12m(r: dict) -> bool:
    """
    Best-effort check for Section 11's recency_multiplier_12m ("signals from
    the most recent 12 months carry Nx weight"). Serper's `date` field is an
    inconsistent mix of relative ("3 weeks ago") and absolute strings, so
    this is deliberately conservative — it only returns True on a fairly
    confident match, never guesses on an ambiguous or missing date. Under-
    counting is the safe failure direction here, not over-counting.
    """
    date_str = (r.get("date") or "").lower().strip()
    if not date_str:
        return False
    m = re.match(r'(\d+)\s+(day|week|month)s?\s+ago', date_str)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "day":
            return True
        if unit == "week":
            return n <= 52
        return n <= 12  # month
    return str(CURRENT_YEAR) in date_str


def _relevant(r: dict, vendor_variants: list) -> bool:
    """Verifies that result mentions the vendor or its recognized trade name/acronym."""
    txt = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}".lower()
    for variant in vendor_variants:
        words = [w for w in variant.lower().split() if len(w) > 2]
        if words and sum(1 for w in words if w in txt) >= max(1, len(words) // 2):
            return True
    return False


def _is_duplicate_event(title: str, kept_hits: list, threshold: float = 0.78) -> bool:
    """
    Section 9.1: "where the same underlying event is reported by multiple
    news sources, it shall be logged once." Exact-URL dedup (the `seen` set
    in _search_category) only catches the same link twice — this catches
    the far more common case of the same story run under near-identical
    headlines by different outlets. difflib is stdlib, no new dependency;
    threshold is deliberately conservative (0.78) so genuinely distinct
    stories that merely share common words aren't merged.
    """
    if not title:
        return False
    t = title.lower()
    return any(SequenceMatcher(None, t, (h.get("title") or "").lower()).ratio() >= threshold for h in kept_hits)


def _block(hits: list) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        d = f" [{h['date']}]" if h.get("date") else ""
        lines.append(f"[{i}]{d} {h['title']}\nURL: {h['url']}\n{h['snippet']}")
    return "\n\n".join(lines)


def _detect_french(text: str) -> bool:
    """
    Lightweight, dependency-free French-language detector (SK-VDD-001
    Section 9.2: "French-language Canadian sources... where material risk
    signals are identified in French-language media, NIVETA shall flag them
    and provide a machine-translated summary"). Compares common French vs.
    English function-word density — conservative on purpose, so a French
    company name inside an otherwise-English snippet doesn't false-positive.
    """
    if not text or len(text) < 20:
        return False
    t = f" {text.lower()} "
    french_markers = [" le ", " la ", " les ", " des ", " une ", " et ", " dans ", " pour ",
                       " avec ", " est ", " sont ", " qui ", " que ", " du ", " au ", " aux ",
                       " été ", " être ", " selon ", " entreprise ", " société "]
    english_markers = [" the ", " and ", " for ", " with ", " is ", " are ", " that ",
                        " of ", " to ", " in ", " on ", " company ", " was ", " were "]
    fr_count = sum(t.count(m) for m in french_markers)
    en_count = sum(t.count(m) for m in english_markers)
    return fr_count >= 3 and fr_count > en_count * 1.5


def _translate_french_hits(french_hits: list) -> str:
    """Machine-translates flagged French-language hits via the same LLM
    ladder already used elsewhere (financial_fetcher.py does the same lazy
    cross-module import for the same reason: no circular import at module
    load time, since ai_engine.py never imports scraper.py)."""
    combined = "\n".join(f"- {h.get('title', '')}: {h.get('snippet', '')}" for h in french_hits[:5])
    try:
        from ai_engine import _groq as _ai_groq
        prompt = (
            "Translate the following French-language search results into English. "
            "Return ONLY the translated text, one item per line.\n\n" + combined
        )
        translated = _ai_groq(prompt, max_tokens=300)
        if translated:
            return f"[FRENCH-LANGUAGE SOURCE(S) DETECTED — MACHINE-TRANSLATED SUMMARY]:\n{translated.strip()}"
    except Exception:
        pass
    return f"[FRENCH-LANGUAGE SOURCE(S) DETECTED — {len(french_hits)} item(s), translation unavailable this run]:\n{combined}"


def _search_category(cat: str, templates: list, vendor_clean: str, vendor_variants: list, domain_hint: str,
                      extra_queries: list = None):
    hits, seen = [], set()
    for tmpl in templates:
        q = tmpl.replace("{vendor}", vendor_clean).replace("{years}", _YEARS_CLAUSE)
        if domain_hint and cat == "cyber":
            q += f' "{domain_hint}"'
        for h in _serper(q, 5):
            if h["url"] in seen or _stale(h) or not _relevant(h, vendor_variants):
                continue
            if _is_duplicate_event(h.get("title", ""), hits):
                continue
            seen.add(h["url"])
            hits.append(h)

    # Section 4.2 bilingual name resolution: a pre-built raw query (e.g. using
    # the French-name variant), not templated with {vendor}/{years} since the
    # caller already built the exact string.
    for q in (extra_queries or []):
        for h in _serper(q, 5):
            if h["url"] in seen or _stale(h) or not _relevant(h, vendor_variants):
                continue
            if _is_duplicate_event(h.get("title", ""), hits):
                continue
            seen.add(h["url"])
            hits.append(h)

    recent_count = sum(1 for h in hits if _is_recent_12m(h))
    tier1_count = sum(1 for h in hits if _is_tier1(h))
    french_hits = [h for h in hits if _detect_french(f"{h.get('title', '')} {h.get('snippet', '')}")]

    text_block = _block(hits)
    if french_hits:
        translated_note = _translate_french_hits(french_hits)
        text_block = f"{text_block}\n\n{translated_note}" if text_block else translated_note

    return cat, {
        "text": text_block, "urls": [h["url"] for h in hits], "hit_count": len(hits),
        "recent_hit_count": recent_count, "french_hit_count": len(french_hits),
        "tier1_hit_count": tier1_count,
        # Section 9.1: "NIVETA shall record the retrieval timestamp for each
        # source query" — when THIS search ran, distinct from each article's
        # own published date (already captured per-hit).
        "retrieved_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _search_profile(vendor_clean: str, vendor_variants: list, domain_hint: str, naics_code: str = "", duns_number: str = ""):
    hits, seen = [], set()
    queries = list(PROFILE_QUERIES)
    if naics_code:
        # SK-VDD-001 Section 4.3: NAICS code, when provided, is used to refine
        # and disambiguate the search (e.g. two similarly-named entities in
        # different industries) rather than just being stored unused.
        queries.append(f'"{vendor_clean}" "NAICS {naics_code}" OR "NAICS code {naics_code}"')
    if duns_number:
        # Same Section 4.3 treatment for the D&B D-U-N-S identifier — we have
        # no D&B API license, but the number itself is still useful as a
        # disambiguation search term.
        queries.append(f'"{vendor_clean}" "DUNS {duns_number}" OR "D-U-N-S {duns_number}"')
    for tmpl in queries:
        q = tmpl.replace("{vendor}", vendor_clean)
        if domain_hint:
            q += f' "{domain_hint}"'
        for h in _serper(q, 4):
            if h["url"] not in seen and _relevant(h, vendor_variants):
                seen.add(h["url"])
                hits.append(h)
    return {"snippet_text": _block(hits[:8]), "urls": [h["url"] for h in hits[:6]]}


def collect_vendor_signals(vendor: str, industry: str = "", country: str = "Canada",
                           company_url: str = "", business_number: str = "", naics_code: str = "",
                           duns_number: str = "", manual_profile: dict = None):
    """
    Executes parallel intelligence gathering across all 5 SK-VDD-001 risk dimensions.
    """
    norm = normalize_vendor_name(vendor)
    vendor_clean = norm["normalized_name"]
    vendor_variants = norm["variants"]
    french_variant = norm.get("french_variant")
    domain_hint = extract_domain(company_url)

    _safe_print(f"  [+] SK-VDD-001 Intelligence Sweep: {vendor_clean} (Raw: {vendor}) | Scope: {country}")
    context = {}

    # Section 4.2: search under the French-language name too, for the two
    # dimensions where French-language Canadian coverage is most likely to
    # exist (Quebec/national media, and federal regulator French-language
    # notices) — not all 5, since e.g. a cyber CVE search gains nothing from
    # a French name variant.
    french_extra = {}
    if french_variant:
        french_extra["reputation"] = [f'"{french_variant}" (controverse OR poursuite OR scandale OR amende) {_YEARS_CLAUSE}']
        french_extra["compliance"] = [f'"{french_variant}" (OSFI OR CANAFE OR sanction OR amende OR conformité) {_YEARS_CLAUSE}']

    with ThreadPoolExecutor(max_workers=6) as ex:
        cat_futures = {
            ex.submit(_search_category, cat, tmpl, vendor_clean, vendor_variants, domain_hint, french_extra.get(cat)): cat
            for cat, tmpl in SEARCH_QUERIES.items()
        }
        prof_future = ex.submit(_search_profile, vendor_clean, vendor_variants, domain_hint, naics_code, duns_number)

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
    context["search_grounding"] = search_grounding_status()
    return context