"""
cyber_intel.py - Real Cybersecurity Data Source Integrations (SK-VDD-001 Section 6.4)
----------------------------------------------------------------------------------------
Unlike the generic Google/Serper keyword search used elsewhere for cyber signals,
this module queries actual authoritative structured data sources that are free
and require no license:

- NVD (nvd.nist.gov) REST API: CVE records filtered by CVSS base score, per the
  configurable min_cvss_score parameter (Section 11).
- CISA Known Exploited Vulnerabilities (KEV) Catalogue: the full JSON feed,
  filtered for entries naming the vendor as vendorProject.
- CCCS (cyber.gc.ca) Alerts & Advisories Atom feed: real, free, public feed
  of Canadian Centre for Cyber Security advisories, filtered for entries
  naming the vendor/product.
- HaveIBeenPwned domain breach search: only called if HIBP_API_KEY is configured
  (HIBP v3 requires a paid key); otherwise this is reported as a licensed-source
  gap by licensed_sources.py rather than silently faked.

Every returned signal carries its real source name, a source URL, and the
retrieval timestamp, per SK-VDD-001 Section 9.1 (source attribution / recency
verification). All calls are defensive and never raise.
"""

import os
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import config

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CISA_KEV_FEED = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# Real, free, public Atom feed (verified directly — the documented /rss/
# path 301-redirects here) of actual CCCS security advisories, e.g.
# "[Control systems] ABB security advisory (AV26-942)". This is Section
# 6.4.1 step 24's actual named source, not the generic Google search for
# the literal string "CCCS" that scraper.py's cyber query template runs.
CCCS_ATOM_FEED = "https://www.cyber.gc.ca/api/cccs/atom/v1/get?feed=alerts_advisories&lang=en"

_CISA_KEV_CACHE = {"data": None, "fetched_at": None}
_CCCS_CACHE = {"entries": None, "fetched_at": None}


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _word_match(needle: str, haystack: str) -> bool:
    """
    Word-boundary match, not a plain substring check. Confirmed live: a
    vendor named "Metro" was matching CVEs about an unrelated product called
    "Metronome" (and similar) purely because "metro" is a substring of
    "metronome" — this produced confidently-wrong "Critical/High severity"
    cyber findings under the wrong vendor's name. NVD/CISA/CCCS text search
    is loose by design; this is our own stricter filter on top of it.
    """
    if not needle:
        return False
    return re.search(rf"\b{re.escape(needle.lower())}\b", haystack.lower()) is not None


# Generic corporate/legal terms and common English words that show up inside
# many real vendor names (e.g. "Canadian National Railway Company"). Confirmed
# live: splitting that name into words and OR-matching each one let the lone
# word "national" false-match an unrelated "National Instruments security
# advisory" CCCS entry — the same substring-style false-positive class as the
# original "Metro"/"Metronome" bug, just one level up (whole-word match on a
# word that is itself too generic to identify the vendor). These are excluded
# from the per-word OR-match; the full multi-word phrase is still tried as-is.
_GENERIC_NAME_WORDS = {
    "inc", "incorporated", "corp", "corporation", "company", "co",
    "ltd", "limited", "llc", "lp", "plc", "group", "holdings", "holding",
    "international", "global", "national", "canadian", "canada", "american",
    "the", "and", "of", "for", "services", "systems", "solutions",
}


def _distinctive_words(vendor_or_product: str) -> list:
    """Words from the vendor name worth OR-matching individually — i.e. not
    generic enough to false-match unrelated entries on their own. Falls back
    to the full word list if every word happens to be generic (e.g. the
    vendor's name genuinely IS just "National")."""
    words = [w for w in re.split(r"\s+", vendor_or_product.lower()) if len(w) > 2]
    distinctive = [w for w in words if w not in _GENERIC_NAME_WORDS]
    return distinctive or words


def query_nvd_cves(vendor_or_product: str, min_cvss: float = None, max_results: int = 10) -> dict:
    """
    Queries the real NVD CVE 2.0 REST API for CVEs whose description mentions
    the vendor/product keyword, filtered to CVSS base score >= min_cvss
    (Section 11 min_cvss_score, default 7.0/High per Section 6.4.1 step 26).
    """
    min_cvss = config.MIN_CVSS_SCORE if min_cvss is None else min_cvss
    result = {"cves": [], "total": 0, "source": "NVD (nvd.nist.gov)", "retrieved_at": _now_iso()}
    if not vendor_or_product or len(vendor_or_product) < 3:
        return result
    try:
        r = requests.get(
            NVD_API,
            params={"keywordSearch": vendor_or_product, "resultsPerPage": 20},
            headers={"User-Agent": "DRiskify-SK-VDD-001/1.0"},
            timeout=15,
        )
        if r.status_code != 200:
            _safe_print(f"  [~] NVD API returned {r.status_code} for '{vendor_or_product}'")
            return result

        data = r.json()
        cves = []
        for item in data.get("vulnerabilities", []):
            cve = item.get("cve", {})
            cve_id = cve.get("id", "")
            descriptions = cve.get("descriptions", [])
            desc = next((d.get("value", "") for d in descriptions if d.get("lang") == "en"), "")

            metrics = cve.get("metrics", {})
            base_score = None
            for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                m = metrics.get(metric_key, [])
                if m:
                    base_score = m[0].get("cvssData", {}).get("baseScore")
                    break
            if base_score is None or base_score < min_cvss:
                continue
            if not _word_match(vendor_or_product, desc):
                continue  # NVD's own keywordSearch is a loose full-text match; this is our stricter filter

            cves.append({
                "cve_id": cve_id,
                "description": desc[:300],
                "cvss_base_score": base_score,
                "published": cve.get("published", ""),
                "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "source": "NVD (nvd.nist.gov)",
                "retrieved_at": result["retrieved_at"],
                # A single-word vendor name matching a single word in free-text
                # CVE prose is inherently weaker evidence than a genuine
                # multi-word phrase match - confirmed live: a vendor named
                # "Metro" matched a CVE about Windows 8's unrelated "Metro" UI
                # design language purely because both use the bare word
                # "Metro". No fix closes this fully (would need real entity
                # resolution), so it's surfaced as reduced confidence instead
                # of hidden or silently presented at full severity.
                "ambiguous_match": " " not in vendor_or_product.strip(),
            })
            if len(cves) >= max_results:
                break

        result["cves"] = cves
        result["total"] = len(cves)
        _safe_print(f"  [✓] NVD: {len(cves)} CVE(s) >= CVSS {min_cvss} for '{vendor_or_product}'")
    except Exception as e:
        _safe_print(f"  [!] NVD query failed for '{vendor_or_product}': {e}")
    return result


def _load_cisa_kev() -> list:
    """Fetches and caches the full CISA KEV catalogue JSON feed in-memory."""
    if _CISA_KEV_CACHE["data"] is not None:
        return _CISA_KEV_CACHE["data"]
    try:
        r = requests.get(CISA_KEV_FEED, timeout=20, headers={"User-Agent": "DRiskify-SK-VDD-001/1.0"})
        if r.status_code == 200:
            vulns = r.json().get("vulnerabilities", [])
            _CISA_KEV_CACHE["data"] = vulns
            _CISA_KEV_CACHE["fetched_at"] = _now_iso()
            return vulns
    except Exception as e:
        _safe_print(f"  [!] CISA KEV feed fetch failed: {e}")
    _CISA_KEV_CACHE["data"] = []
    return []


def query_cisa_kev(vendor_or_product: str) -> dict:
    """
    Filters the real CISA Known Exploited Vulnerabilities catalogue for entries
    whose vendorProject or product field matches the vendor name.
    """
    result = {"entries": [], "total": 0, "source": "CISA KEV Catalogue", "retrieved_at": _now_iso()}
    if not vendor_or_product or len(vendor_or_product) < 3:
        return result
    try:
        kev = _load_cisa_kev()
        needle = vendor_or_product.lower()
        words = _distinctive_words(vendor_or_product)
        matches = []
        for entry in kev:
            vp = str(entry.get("vendorProject", "")).lower()
            prod = str(entry.get("product", "")).lower()
            haystack = f"{vp} {prod}"
            phrase_hit = _word_match(needle, haystack)
            word_hit = any(_word_match(w, haystack) for w in words)
            if phrase_hit or word_hit:
                matches.append({
                    "cve_id": entry.get("cveID", ""),
                    "vendor_project": entry.get("vendorProject", ""),
                    "product": entry.get("product", ""),
                    "vulnerability_name": entry.get("vulnerabilityName", ""),
                    "date_added": entry.get("dateAdded", ""),
                    "ransomware_use": entry.get("knownRansomwareCampaignUse", "Unknown"),
                    "url": f"https://nvd.nist.gov/vuln/detail/{entry.get('cveID', '')}",
                    "source": "CISA KEV Catalogue",
                    "retrieved_at": result["retrieved_at"],
                    # Confident only when the FULL multi-word vendor phrase
                    # matched together - a lone distinctive word (or a
                    # single-word vendor name, where phrase and word matching
                    # are the same thing) is the exact false-positive class
                    # this session found (e.g. "National" alone matching an
                    # unrelated "National Instruments" advisory).
                    "ambiguous_match": not (phrase_hit and " " in needle),
                })
        result["entries"] = matches[:10]
        result["total"] = len(matches)
        if matches:
            _safe_print(f"  [✓] CISA KEV: {len(matches)} known-exploited entr(ies) for '{vendor_or_product}'")
    except Exception as e:
        _safe_print(f"  [!] CISA KEV filter failed for '{vendor_or_product}': {e}")
    return result


def _load_cccs_advisories() -> list:
    """Fetches and caches the real CCCS alerts & advisories Atom feed."""
    if _CCCS_CACHE["entries"] is not None:
        return _CCCS_CACHE["entries"]
    entries = []
    try:
        r = requests.get(CCCS_ATOM_FEED, timeout=20, headers={"User-Agent": "DRiskify-SK-VDD-001/1.0"})
        if r.status_code == 200:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(r.content)
            for entry in root.findall("a:entry", ns):
                title_el = entry.find("a:title", ns)
                link_el = entry.find("a:link", ns)
                updated_el = entry.find("a:updated", ns)
                entries.append({
                    "title": (title_el.text or "").strip() if title_el is not None else "",
                    "url": link_el.get("href", "") if link_el is not None else "",
                    "updated": (updated_el.text or "") if updated_el is not None else "",
                })
            _safe_print(f"  [✓] CCCS advisory feed loaded: {len(entries)} entries")
        else:
            _safe_print(f"  [~] CCCS advisory feed returned {r.status_code}")
    except Exception as e:
        _safe_print(f"  [!] CCCS advisory feed fetch failed: {e}")
    _CCCS_CACHE["entries"] = entries
    _CCCS_CACHE["fetched_at"] = _now_iso()
    return entries


def query_cccs_advisories(vendor_or_product: str) -> dict:
    """
    Filters the real CCCS alerts & advisories feed for entries whose title
    names the vendor/product — same matching approach as query_cisa_kev.
    The feed is a rolling window of recent advisories, not a full historical
    archive, which matches the spec's own 36-month recency intent.
    """
    result = {"entries": [], "total": 0, "source": "CCCS (cyber.gc.ca)", "retrieved_at": _now_iso()}
    if not vendor_or_product or len(vendor_or_product) < 3:
        return result
    try:
        entries = _load_cccs_advisories()
        needle = vendor_or_product.lower()
        words = _distinctive_words(vendor_or_product)
        matches = []
        for e in entries:
            title_lower = e["title"].lower()
            phrase_hit = _word_match(needle, title_lower)
            word_hit = bool(words) and any(_word_match(w, title_lower) for w in words)
            if phrase_hit or word_hit:
                matches.append({
                    "title": e["title"],
                    "url": e["url"],
                    "updated": e["updated"],
                    "source": "CCCS (cyber.gc.ca)",
                    "retrieved_at": result["retrieved_at"],
                    # See query_cisa_kev's identical field for the reasoning -
                    # confident only when the full multi-word vendor phrase
                    # matched together, not a single (possibly generic) word.
                    "ambiguous_match": not (phrase_hit and " " in needle),
                })
        result["entries"] = matches[:10]
        result["total"] = len(matches)
        if matches:
            _safe_print(f"  [✓] CCCS: {len(matches)} advisory/advisories naming '{vendor_or_product}'")
    except Exception as e:
        _safe_print(f"  [!] CCCS query failed for '{vendor_or_product}': {e}")
    return result


def query_hibp_domain(domain: str) -> dict:
    """
    Real HaveIBeenPwned domain breach search — only executes if HIBP_API_KEY
    is configured (HIBP v3 requires a paid subscription key). Otherwise this
    is reported as a licensed-source gap by licensed_sources.py, not faked.
    """
    result = {"breaches": [], "total": 0, "source": "HaveIBeenPwned", "retrieved_at": _now_iso(), "queried": False}
    api_key = os.getenv("HIBP_API_KEY", "").strip()
    if not api_key or not domain:
        return result
    try:
        r = requests.get(
            f"https://haveibeenpwned.com/api/v3/breaches",
            params={"domain": domain},
            headers={"hibp-api-key": api_key, "User-Agent": "DRiskify-SK-VDD-001/1.0"},
            timeout=12,
        )
        result["queried"] = True
        if r.status_code == 200:
            breaches = r.json()
            result["breaches"] = [
                {
                    "name": b.get("Name", ""),
                    "breach_date": b.get("BreachDate", ""),
                    "pwn_count": b.get("PwnCount", 0),
                    "data_classes": b.get("DataClasses", []),
                }
                for b in breaches
            ]
            result["total"] = len(result["breaches"])
    except Exception as e:
        _safe_print(f"  [!] HIBP query failed for domain '{domain}': {e}")
    return result


def gather_cyber_intelligence(vendor: str, domain: str = "") -> dict:
    """
    Aggregates all real (free-tier) cyber intelligence for a vendor:
    NVD CVEs, CISA KEV matches, and HIBP breach data (if licensed).
    Returns structured signals ready to merge into the cyber dimension output.
    """
    nvd = query_nvd_cves(vendor)
    kev = query_cisa_kev(vendor)
    cccs = query_cccs_advisories(vendor)
    hibp = query_hibp_domain(domain) if domain else {"breaches": [], "total": 0, "queried": False}

    # A name-only match (single generic word, no corroborating multi-word
    # phrase) is real evidence of a possible coincidence, not a confirmed
    # finding - confirmed live for both the CVE-description and advisory-
    # title matching paths this session (Windows "Metro" UI, "National
    # Instruments"). Capping severity and adding a visible caveat means the
    # finding still surfaces (required - never silently dropped) but doesn't
    # carry the same unearned confidence as a genuine multi-word match.
    _AMBIGUOUS_NOTE = " [Name-only match - verify this is genuinely about {vendor}, not a coincidental word match.]"

    signals = []
    for cve in nvd["cves"]:
        ambiguous = cve.get("ambiguous_match", False)
        severity = "Elevated" if ambiguous else ("Critical" if cve["cvss_base_score"] >= 9.0 else "High")
        indicator = f"{cve['cve_id']} (CVSS {cve['cvss_base_score']}): {cve['description'][:150]}"
        if ambiguous:
            indicator += _AMBIGUOUS_NOTE.format(vendor=vendor)
        signals.append({
            "category": "CVE Exposure",
            "indicator": indicator,
            "severity": severity,
            "source": cve["source"],
            "url": cve["url"],
            "retrieved_at": cve["retrieved_at"],
        })
    for entry in kev["entries"]:
        ambiguous = entry.get("ambiguous_match", False)
        indicator = (f"CISA KEV: {entry['cve_id']} — {entry['vulnerability_name']} (added {entry['date_added']}, "
                     f"ransomware use: {entry['ransomware_use']})")
        if ambiguous:
            indicator += _AMBIGUOUS_NOTE.format(vendor=vendor)
        signals.append({
            "category": "Government Advisory",
            "indicator": indicator,
            "severity": "Elevated" if ambiguous else "Critical",
            "source": entry["source"],
            "url": entry["url"],
            "retrieved_at": entry["retrieved_at"],
        })
    for entry in cccs["entries"]:
        ambiguous = entry.get("ambiguous_match", False)
        indicator = f"CCCS Advisory: {entry['title']} (updated {entry['updated'][:10]})"
        if ambiguous:
            indicator += _AMBIGUOUS_NOTE.format(vendor=vendor)
        signals.append({
            "category": "Government Advisory",
            "indicator": indicator,
            "severity": "Elevated" if ambiguous else "High",
            "source": entry["source"],
            "url": entry["url"],
            "retrieved_at": entry["retrieved_at"],
        })
    for breach in hibp.get("breaches", []):
        signals.append({
            "category": "Data Breach",
            "indicator": f"Confirmed breach '{breach['name']}' ({breach['breach_date']}) affecting "
                         f"{breach['pwn_count']:,} accounts; data classes: {', '.join(breach['data_classes'][:5])}",
            "severity": "Critical",
            "source": "HaveIBeenPwned",
            "url": "https://haveibeenpwned.com/",
            "retrieved_at": hibp["retrieved_at"],
        })

    return {
        "signals": signals,
        "cve_count": nvd["total"],
        "kev_count": kev["total"],
        "cccs_count": cccs["total"],
        "breach_count": hibp.get("total", 0),
        "recent_breach_flag": hibp.get("total", 0) > 0,
        "hibp_queried": hibp.get("queried", False),
    }
