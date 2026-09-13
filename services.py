"""
services.py - Due Diligence Pipeline & Orchestration (SK-VDD-001 Compliant)
-----------------------------------------------------------------------------
Features:
- SK-VDD-001 Section 7.2 Weighted Score Formula:
  Overall Score = (Fin x 0.30) + (Rep x 0.20) + (KP x 0.20) + (Tech x 0.20) + (Comp x 0.10)
- SK-VDD-001 Section 7.3 Four-Tier Rating Bands:
  * 0 - 24: Low (Green) - Standard onboarding may proceed
  * 25 - 49: Medium (Amber) - Enhanced due diligence recommended
  * 50 - 74: High (Orange) - Senior review and conditional onboarding
  * 75 - 100: Critical (Red) - Escalation required; onboarding to be suspended
- Automatic Escalation Trigger Detection (Section 10.1)
- Canonical Structured Output Generation (Section 8)
- Windows cp1252 safe logging
"""

import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from normalizer import normalize_vendor_name
from scraper import collect_vendor_signals
from financial_fetcher import fetch_financial_and_profile
from ai_engine import analyze_vendor_full

RISK_CATEGORIES = ["financial", "reputation", "key_person", "cyber", "compliance"]

# SK-VDD-001 Section 7.2 Exact Weights
WEIGHTS = {
    "financial": 0.30,
    "reputation": 0.20,
    "key_person": 0.20,
    "cyber": 0.20,
    "compliance": 0.10
}

# 4-Tier Rating Band Definitions (Section 7.3)
RATING_BANDS = {
    "Low": {
        "range": (0, 24),
        "traffic_light": "Green",
        "action": "No material concerns detected. Standard onboarding may proceed.",
        "color": "#10b981"
    },
    "Medium": {
        "range": (25, 49),
        "traffic_light": "Amber",
        "action": "Some risk signals present. Enhanced due diligence recommended.",
        "color": "#f59e0b"
    },
    "High": {
        "range": (50, 74),
        "traffic_light": "Orange",
        "action": "Significant risk signals. Senior review and conditional onboarding.",
        "color": "#f97316"
    },
    "Critical": {
        "range": (75, 100),
        "traffic_light": "Red",
        "action": "Severe risk signals. Escalation required; onboarding to be suspended.",
        "color": "#ef4444"
    }
}


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


def get_risk_tier(score: float) -> tuple:
    """Maps score to SK-VDD-001 4-tier rating band."""
    s = int(round(score))
    if s <= 24:
        return "Low", RATING_BANDS["Low"]
    elif s <= 49:
        return "Medium", RATING_BANDS["Medium"]
    elif s <= 74:
        return "High", RATING_BANDS["High"]
    else:
        return "Critical", RATING_BANDS["Critical"]


def get_vendor_analysis(vendor: str, industry: str = "", country: str = "Canada", concerns: str = "",
                        company_url: str = "", business_number: str = "", ticker: str = "") -> tuple:
    """
    Executes end-to-end SK-VDD-001 Due Diligence Pipeline.
    """
    try:
        norm = normalize_vendor_name(vendor)
        clean_vendor = norm["normalized_name"]

        _safe_print(f"\n[+] Phase 1: Ingesting Signals & Financials for {clean_vendor} ({country})...")

        def _scrape():
            return collect_vendor_signals(
                vendor=clean_vendor,
                industry=industry,
                country=country,
                company_url=company_url,
                business_number=business_number
            )

        def _finance():
            return fetch_financial_and_profile(
                clean_vendor,
                country,
                ticker=ticker,
                company_url=company_url
            )

        with ThreadPoolExecutor(max_workers=2) as ex:
            sf = ex.submit(_scrape)
            ff = ex.submit(_finance)
            data = sf.result()
            financial_metrics, prof_extras = ff.result()

        if not isinstance(data, dict):
            data = {}

        # Inject structured profile into context
        existing_profile = data.get("profile", {})
        if not isinstance(existing_profile, dict):
            existing_profile = {}
        existing_text = existing_profile.get("text", "")

        if prof_extras:
            lines = ["--- Structured profile data (authoritative) ---"]
            for field, label in [
                ("ceo", "CEO"),
                ("founder", "Founder"),
                ("founded", "Founded"),
                ("headquarters", "Headquarters"),
                ("employees", "Employees"),
            ]:
                v = prof_extras.get(field, "")
                if v:
                    lines.append(f"{label}: {v}")
            block = "\n".join(lines)

            if "profile" not in data or not isinstance(data.get("profile"), dict):
                data["profile"] = {}
            data["profile"]["text"] = block + "\n\n" + existing_text
            data["profile"]["has_structured"] = True

        # Phase 2: Gen-AI Risk Synthesis & Signal Classification
        _safe_print(f"[+] Phase 2: AI Multi-Dimension Synthesis for {clean_vendor}...")
        result = analyze_vendor_full(
            clean_vendor, data,
            country=country,
            industry=industry,
            concerns=concerns,
            financial_metrics=financial_metrics
        )
        if not isinstance(result, dict):
            result = {}
        result.setdefault("risk_scores", {k: 25 for k in RISK_CATEGORIES})

        # Phase 3: Patch Company Profile with authoritative fields
        cp = result.get("company_profile", {})
        if not isinstance(cp, dict):
            cp = {}

        INVALID = {"", "not available", "unknown", "n/a", "none", "null", "undefined"}
        for field in ("ceo", "founder", "founded", "headquarters", "employees"):
            scraped_val = str(prof_extras.get(field, "")).strip()
            if scraped_val and scraped_val.lower() not in INVALID:
                cp[field] = scraped_val
            elif str(cp.get(field, "")).strip().lower() in INVALID:
                cp[field] = "Not Available"

        if financial_metrics:
            cp["financial_metrics"] = {
                k: v for k, v in financial_metrics.items() if v not in (None, "", "N/A", "Not Available")
            }

        result["company_profile"] = cp

        # Phase 4: Compute Exact SK-VDD-001 Weighted Score (Section 7.2)
        scores = result["risk_scores"]
        overall = int(round(
            scores.get("financial", 25) * WEIGHTS["financial"] +
            scores.get("reputation", 25) * WEIGHTS["reputation"] +
            scores.get("key_person", 25) * WEIGHTS["key_person"] +
            scores.get("cyber", 25) * WEIGHTS["cyber"] +
            scores.get("compliance", 25) * WEIGHTS["compliance"]
        ))
        overall = max(0, min(overall, 100))

        tier_name, tier_meta = get_risk_tier(overall)

        # Check for Critical score escalation
        escalations = result.get("automatic_escalations", [])
        if overall >= 75 and "Overall Vendor Risk Score >= 75 (Critical rating)" not in escalations:
            escalations.append("Overall Vendor Risk Score >= 75 (Critical rating)")

        # SK-VDD-001 Section 10.1: Entity Disambiguation Escalation
        # Flag if profile search results point to 2+ distinct company websites (excluding info aggregators)
        _reference_domains = [
            "google.", "serper.", "bing.", "yahoo.", "duckduckgo.", "search.",
            "wikipedia.org", "linkedin.com", "crunchbase.com", "zoominfo.com",
            "bloomberg.com", "reuters.com", "forbes.com", "marketwatch.com",
            "stockanalysis.com", "finviz.com", "yahoofinance.", "investing.com",
        ]
        _profile_urls = data.get("profile", {}).get("urls", [])
        _company_domains = set()
        for url in _profile_urls:
            try:
                netloc = urlparse(url).netloc.lower().replace("www.", "")
                if netloc and not any(d in netloc for d in _reference_domains):
                    _company_domains.add(netloc)
            except Exception:
                pass
        if len(_company_domains) >= 2:
            disambiguation_flag = "Multiple entities match the provided vendor name — manual disambiguation required"
            if disambiguation_flag not in escalations:
                escalations.append(disambiguation_flag)
            result["disambiguation_flag"] = True
        else:
            result["disambiguation_flag"] = False

        result["overall_score"] = overall
        result["overall_risk_score"] = overall
        result["overall_risk_rating"] = tier_name
        result["risk_level"] = tier_name
        result["traffic_light"] = tier_meta["traffic_light"]
        result["recommended_action"] = tier_meta["action"]
        result["automatic_escalations"] = escalations
        result["vendor_name"] = clean_vendor
        result["raw_vendor_name"] = vendor
        result["registration_country"] = country
        result["business_number"] = business_number
        result["query_date"] = datetime.utcnow().strftime("%Y-%m-%d")

        # Canonical Section 8 Schema Aliases
        result["fin_risk_score"] = scores.get("financial", 25)
        result["fin_risk_signals"] = result.get("explanations", {}).get("financial", {}).get("signals", [])
        result["rep_risk_score"] = scores.get("reputation", 25)
        result["rep_risk_articles"] = result.get("explanations", {}).get("reputation", {}).get("articles", [])
        result["kp_risk_score"] = scores.get("key_person", 25)
        result["kp_persons"] = result.get("explanations", {}).get("key_person", {}).get("persons", [])
        result["tech_cyber_score"] = scores.get("cyber", 25)
        result["tech_cyber_signals"] = result.get("explanations", {}).get("cyber", {}).get("signals", [])
        result["compliance_score"] = scores.get("compliance", 25)
        result["compliance_signals"] = result.get("explanations", {}).get("compliance", {}).get("signals", [])

        # Data Confidence Score (SK-VDD-001 Section 11)
        total_hits = result.get("total_hits", 0)
        has_metrics = bool(financial_metrics)
        confidence = (
            40 if total_hits == 0 and not has_metrics else
            65 if total_hits < 5 else
            85 if total_hits < 15 else 95
        )
        if has_metrics:
            confidence = min(confidence + 5, 98)

        # SK-VDD-001 Section 9.2: Private company confidence flag
        # Private companies (no ticker, no SEC/SEDAR+ financials) get reduced confidence
        has_ticker = bool(ticker.strip() or financial_metrics.get("ticker"))
        if not has_ticker or not has_metrics:
            result["private_co_confidence_flag"] = "Reduced"
            confidence = max(confidence - 15, 30)
        else:
            result["private_co_confidence_flag"] = "Standard"

        result["confidence_score"] = confidence

        _safe_print(f"\n[+] Due Diligence Complete: Overall Score: {overall} ({tier_name} - {tier_meta['traffic_light']}) | {scores}")
        return result, data

    except Exception as e:
        import traceback
        _safe_print(f"[!] SYSTEM ERROR in services.py: {e}")
        traceback.print_exc()
        return {"error": str(e)}, {}