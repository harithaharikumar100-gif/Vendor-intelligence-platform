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
from datetime import datetime, timezone

import config

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CISA_KEV_FEED = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

_CISA_KEV_CACHE = {"data": None, "fetched_at": None}


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

            cves.append({
                "cve_id": cve_id,
                "description": desc[:300],
                "cvss_base_score": base_score,
                "published": cve.get("published", ""),
                "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "source": "NVD (nvd.nist.gov)",
                "retrieved_at": result["retrieved_at"],
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
        words = [w for w in re.split(r"\s+", needle) if len(w) > 2]
        matches = []
        for entry in kev:
            vp = str(entry.get("vendorProject", "")).lower()
            prod = str(entry.get("product", "")).lower()
            haystack = f"{vp} {prod}"
            if any(w in haystack for w in words):
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
                })
        result["entries"] = matches[:10]
        result["total"] = len(matches)
        if matches:
            _safe_print(f"  [✓] CISA KEV: {len(matches)} known-exploited entr(ies) for '{vendor_or_product}'")
    except Exception as e:
        _safe_print(f"  [!] CISA KEV filter failed for '{vendor_or_product}': {e}")
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
    hibp = query_hibp_domain(domain) if domain else {"breaches": [], "total": 0, "queried": False}

    signals = []
    for cve in nvd["cves"]:
        signals.append({
            "category": "CVE Exposure",
            "indicator": f"{cve['cve_id']} (CVSS {cve['cvss_base_score']}): {cve['description'][:150]}",
            "severity": "Critical" if cve["cvss_base_score"] >= 9.0 else "High",
            "source": cve["source"],
            "url": cve["url"],
            "retrieved_at": cve["retrieved_at"],
        })
    for entry in kev["entries"]:
        signals.append({
            "category": "Government Advisory",
            "indicator": f"CISA KEV: {entry['cve_id']} — {entry['vulnerability_name']} (added {entry['date_added']}, "
                         f"ransomware use: {entry['ransomware_use']})",
            "severity": "Critical",
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
        "breach_count": hibp.get("total", 0),
        "recent_breach_flag": hibp.get("total", 0) > 0,
        "hibp_queried": hibp.get("queried", False),
    }
