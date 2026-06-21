"""
services.py  v4
---------------
- _describe_small_company removed (description no longer shown in UI)
- company_url passed to fetch_financial_and_profile
- Wikipedia CEO disambiguation fix applied via vendor full-name query
- description stripped from company_profile before returning
"""

from concurrent.futures import ThreadPoolExecutor
from ai_engine          import analyze_vendor_full
from scraper            import collect_vendor_signals
from financial_fetcher  import fetch_financial_and_profile

RISK_CATEGORIES = ["financial","reputation","key_person","cyber","compliance"]

CATEGORY_BOOSTS = {
    "financial":  {"bankruptcy":12,"revenue decline":7,"layoffs":5,"debt crisis":9,"financial fraud":10,"earnings miss":5},
    "reputation": {"lawsuit":7,"scandal":9,"discrimination":7,"fraud":10,"ethics violation":7,"backlash":4},
    "cyber":      {"data breach":11,"ransomware":13,"cyberattack":11,"data leak":11,"exposed database":9,"hacked":9},
    "compliance": {"regulatory fine":9,"gdpr":7,"sec investigation":11,"sanctions":11,"penalty":6,"compliance violation":7},
    "key_person": {"ceo resign":9,"executive departure":7,"mass layoff":7,"leadership instability":7},
}
WEIGHTS = {"financial":0.25,"reputation":0.20,"key_person":0.15,"cyber":0.25,"compliance":0.15}


def _boost(text, cat):
    low = text.lower()
    return min(sum(pts for term,pts in CATEGORY_BOOSTS.get(cat,{}).items() if term in low), 18)


def get_vendor_analysis(vendor, industry, country, concerns,
                        company_url="", manual_profile=None, ticker=""):
    try:
        # ── Phase 1: scrape + financials IN PARALLEL ─────────────────────────
        print(f"\n🚀 Phase 1 parallel: scrape + financials for {vendor}")
        print(f"📡 {vendor} | {industry} | {country}")

        def _scrape():
            return collect_vendor_signals(vendor, industry, country,
                                          company_url=company_url,
                                          manual_profile=manual_profile or {})

        def _finance():
            return fetch_financial_and_profile(
                vendor, country,
                ticker=ticker,
                web_snippets="",       # snippets no longer used for description
                company_url=company_url,
            )

        with ThreadPoolExecutor(max_workers=2) as ex:
            sf = ex.submit(_scrape)
            ff = ex.submit(_finance)
            data                           = sf.result()
            financial_metrics, prof_extras = ff.result()

        # description is no longer needed anywhere — strip it if present
        prof_extras.pop("description", None)

        if not isinstance(data, dict):
            data = {}

        # ── Phase 2: inject structured profile into scraped data ──────────────
        existing_profile = data.get("profile", {})
        if not isinstance(existing_profile, dict):
            existing_profile = {}
        existing_text = existing_profile.get("text", "")

        if prof_extras:
            lines = ["--- Structured profile data (authoritative) ---"]
            for field, label in [
                ("ceo",          "CEO"),
                ("founder",      "Founder"),
                ("founded",      "Founded"),
                ("headquarters", "Headquarters"),
                ("employees",    "Employees"),
            ]:
                v = prof_extras.get(field, "")
                if v:
                    lines.append(f"{label}: {v}")
            block = "\n".join(lines)

            if "profile" not in data or not isinstance(data.get("profile"), dict):
                data["profile"] = {}
            data["profile"]["text"]           = block + "\n\n" + existing_text
            data["profile"]["has_structured"] = True
            # no description field injected

        # ── Phase 3: AI analysis ──────────────────────────────────────────────
        result = analyze_vendor_full(vendor, data, country, industry, concerns,
                                     financial_metrics=financial_metrics)
        if not isinstance(result, dict):
            result = {}
        result.setdefault("risk_scores", {k: 30 for k in RISK_CATEGORIES})

        # ── Phase 4: keyword boost ────────────────────────────────────────────
        for cat in RISK_CATEGORIES:
            cat_data = data.get(cat, {})
            cat_text = cat_data.get("text", "") if isinstance(cat_data, dict) else ""
            boost    = _boost(cat_text, cat)
            base     = int(result["risk_scores"].get(cat, 30))
            if base < 60 and boost > 0:
                result["risk_scores"][cat] = min(base + boost, 90)

        # ── Phase 5: patch company_profile with real data ─────────────────────────
        cp = result.get("company_profile", {})
        if not isinstance(cp, dict):
            cp = {}

        INVALID = {"", "not available", "unknown", "n/a", "none", "null", "undefined"}

        for field in ("ceo", "founder", "founded", "headquarters", "employees"):
            scraped_val = str(prof_extras.get(field, "")).strip()
            # Only override if scraped value is non-empty AND not a placeholder
            if scraped_val and scraped_val.lower() not in INVALID:
                cp[field] = scraped_val
            elif str(cp.get(field, "")).strip().lower() in INVALID:
                cp[field] = "Not Available"

        result["company_profile"] = cp  # ← was missing! cp was never written back

        # ── Phase 6: overall score ────────────────────────────────────────────
        s       = result["risk_scores"]
        overall = int(sum(s.get(k, 30) * WEIGHTS.get(k, 0.2) for k in RISK_CATEGORIES))
        result["overall_score"] = overall
        result["risk_level"]    = "Low" if overall <= 35 else ("Medium" if overall <= 65 else "High")

        print(f"\n📊 Overall: {overall} ({result['risk_level']}) | {result['risk_scores']}")
        return result, data

    except Exception as e:
        import traceback
        print(f"❌ SYSTEM ERROR: {e}")
        traceback.print_exc()
        return {"error": str(e)}, {}


def calculate_weighted_score(risk_scores, profile=None):
    if not risk_scores:
        return 30
    base = int(sum(risk_scores.get(k, 30) * WEIGHTS.get(k, 0.2) for k in RISK_CATEGORIES))
    if profile:
        missing = sum(
            1 for f in ("ceo", "founder", "founded", "headquarters")
            if str(profile.get(f, "")).strip().lower() in ("", "not available", "unknown")
        )
        base = min(base + min(missing * 4, 15), 100)
    return base