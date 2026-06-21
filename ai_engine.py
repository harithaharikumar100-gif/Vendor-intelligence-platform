"""
ai_engine.py  v3
----------------
Fixes:
  - Risk prompts: surface LATEST + MOST SEVERE events first (explicit rule)
  - Synthesis prompt: forces specific, named signals / gaps / recommendations
  - Profile prompt: structured block is ground truth; no hallucination allowed
  - Financial prompt: full metrics table fed to LLM
"""

import os, json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from groq import Groq
from dotenv import load_dotenv



load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY",""))
MODEL  = "llama-3.3-70b-versatile"

RISK_CATEGORIES = ["financial","reputation","cyber","compliance","key_person"]

FOCUS = {
    "financial":  "revenue losses, debt crisis, layoffs, bankruptcy, funding failures, earnings misses, negative EPS, high debt/equity, poor ROCE",
    "reputation": "lawsuits, public scandals, discrimination, ethics violations, social media backlash, customer complaints",
    "cyber":      "data breaches, ransomware, hacking, exposed databases, security vulnerabilities, infrastructure weaknesses",
    "compliance": "regulatory fines, GDPR violations, government investigations, sanctions, AML penalties",
    "key_person": "CEO/executive resignations, mass layoffs, leadership instability, founder departure, management restructuring",
}


def _parse_json(raw: str) -> dict:
    if not raw: return {}
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*","",text,flags=re.IGNORECASE)
    text = re.sub(r"\s*```$","",text)
    try: return json.loads(text)
    except: pass
    m = re.search(r"\{.*\}",text,re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    try:
        f  = text
        f += "]"*(f.count("[")-f.count("]"))
        f += "}"*(f.count("{")-f.count("}"))
        return json.loads(f)
    except: pass
    return {}


def _groq(prompt: str, max_tokens: int = 700) -> str:
    for attempt in range(2):
        try:
            r = client.chat.completions.create(
                model=MODEL,
                messages=[{"role":"user","content":prompt}],
                temperature=0.1, max_tokens=max_tokens,
            )
            res = r.choices[0].message.content or ""
            if res.strip(): return res
        except Exception as e:
            print(f"  ⚠  Groq attempt {attempt+1}: {e}")
        time.sleep(1+attempt)
    return ""


# ── prompts ───────────────────────────────────────────────────────────────────

def _financial_prompt(vendor, industry, country, city, evidence, urls, metrics):
    loc = f"{city}, {country}" if city else country

    m_block = ""
    if metrics:
        rows = [f"  {k}: {v}" for k,v in metrics.items() if v not in (None,"","N/A","Not Available")]
        if rows:
            m_block = "VERIFIED FINANCIAL METRICS:\n" + "\n".join(rows) + "\n\n"

    ev = (evidence or "No evidence found.")[:1500]
    return f"""Senior Financial Risk Analyst. Assess {vendor} ({industry}, {loc}).

{m_block}WEB EVIDENCE (2024-2026):
{ev}

SOURCE URLs: {json.dumps(urls[:5])}

RULES:
1. Use ONLY data above. No outside knowledge.
2. Negative EPS → score ≥55. Debt/equity >2x → score ≥50. Revenue decline + layoffs → score ≥55.
3. No evidence + no metrics → score 25-35.
4. List the MOST SEVERE and MOST RECENT financial event first in observed_events.
5. Never fabricate numbers.

Scores: 0-25 healthy, 26-45 minor, 46-65 moderate, 66-85 serious, 86-100 critical.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "summary": "<2-3 sentences citing specific metrics or events>",
  "severity_reason": "<one sentence on WORST finding>",
  "observed_events": ["<most recent/severe event first>", "..."],
  "evidence_urls": [<max 3>],
  "key_metrics": {{
    "revenue_trend": "<growing|declining|stable|unknown>",
    "debt_equity":   "<value or unknown>",
    "eps":           "<value or unknown>",
    "roce":          "<value or unknown>",
    "net_margin":    "<value or unknown>"
  }}
}}"""


def _category_prompt(cat, vendor, industry, country, city, evidence, urls):
    loc   = f"{city}, {country}" if city else country
    focus = FOCUS[cat]
    ev    = (evidence or "No evidence found.")[:1500]
    return f"""Senior {cat.title()} Risk Analyst. Assess {vendor} ({industry}, {loc}).

WEB EVIDENCE (2023-2025):
{ev}

SOURCE URLs: {json.dumps(urls[:5])}

RULES:
1. Use ONLY the evidence above. No outside knowledge.
2. No evidence mentioning {vendor} → score 20-35.
3. Focus ONLY on: {focus}
4. In observed_events: list MOST RECENT event first, then most severe.
5. Never fabricate events.

Scores: 0-25 none, 26-45 minor/old, 46-65 active moderate, 66-85 serious, 86-100 critical.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "summary": "<2-3 sentences. Name specific events with dates from evidence.>",
  "severity_reason": "<one sentence on single worst finding>",
  "observed_events": ["<most recent first, with date>", "..."],
  "evidence_urls": [<max 3>]
}}"""


def _profile_prompt(vendor, industry, country, city, all_text):
    loc = f"{city}, {country}" if city else country
    return f"""Extract company profile for {vendor} ({industry}, {loc}).

TEXT (lines under "Structured profile data (authoritative)" are GROUND TRUTH — copy them verbatim):
{(all_text or "No data.")[:3000]}

STRICT RULES:
1. For any field present in the "Structured profile data (authoritative)" block: copy it EXACTLY, character for character. No paraphrasing, no changes.
2. For fields NOT in the authoritative block: extract ONLY if the exact value is explicitly stated in the text. Do NOT infer, guess, or use general knowledge.
3. If a field is not explicitly found → return exactly "Not Available".
4. ceo and founder MUST be real human full names (First Last). Reject any value that is a company name, org name, Wikipedia section label, or navigation text (e.g. "Tata Sons", "Area Served", "Sees Path", "Key", "Edit").
5. founded MUST be a 4-digit year between 1800-2026. If not explicitly stated, return "Not Available".
6. headquarters MUST be a real city/country pair explicitly mentioned. NEVER use Wikipedia infobox labels like "Area Served", "Key", "Overview" as a headquarters value.
7. employees MUST be a plain number like "614,000". Reject anything that is not a number.
8. NEVER use your training knowledge about {vendor}. Only use the TEXT provided above.

Return ONLY valid JSON:
{{
  "ceo":          "<human full name or Not Available>",
  "founder":      "<human full name or Not Available>",
  "founded":      "<4-digit year or Not Available>",
  "headquarters": "<City, Country or Not Available>",
  "employees":    "<number or Not Available>",
  "description":  "<1 sentence what company does, or Not Available>"
}}"""

def _synthesis_prompt(vendor, industry, country, city, cat_results, concerns, total_hits, company_desc):
    loc      = f"{city}, {country}" if city else country
    low_data = total_hits < 5
    lines    = []
    for cat, r in cat_results.items():
        evts = r.get("observed_events") or ["none"]
        lines.append(
            f"• {cat.upper()} score={r['score']}: {r.get('summary','')[:100]}\n"
            f"  TOP EVENT: {str(evts[0])[:80]}"
        )
    summary = "\n".join(lines)

    desc_block = f"\nCOMPANY: {company_desc}\n" if company_desc else ""

    return f"""Senior Risk Consultant. Synthesise findings for {vendor} ({industry}, {loc}).
{desc_block}
CATEGORY FINDINGS:
{summary}

USER CONCERNS: {concerns or "None"}
DATA LEVEL: {"LOW — limited public evidence" if low_data else "ADEQUATE"}

RULES for output:
1. key_signals: 3 signals that are SPECIFIC to {vendor} — name actual events, dates, metrics. No generic phrases.
2. gaps: 2 specific information gaps (e.g. "No audited financials post-2022 found publicly").
3. recommendations: 3 actionable steps tailored to the HIGHEST-SCORING categories.
4. filings_summary: 2 sentences on public regulatory/financial filings status.
5. risk_level: must match the weighted average of scores (High if avg>65, Low if avg<35).

Return ONLY valid JSON:
{{
  "risk_level":      "<Low|Medium|High>",
  "key_signals":     ["<specific signal with date/metric>", "...", "..."],
  "gaps":            ["<specific gap>", "<specific gap>"],
  "recommendations": ["<actionable rec for highest risk cat>", "...", "..."],
  "filings_summary": "<2 sentences>"
}}"""


def _fallback_synthesis(vendor, industry, country, cat_results, total_hits):
    scores    = [r["score"] for r in cat_results.values()]
    avg       = sum(scores)//len(scores) if scores else 30
    level     = "High" if avg>65 else ("Medium" if avg>35 else "Low")
    high_cats = [c for c,r in cat_results.items() if r["score"]>60]
    low_data  = total_hits < 5

    signals = []
    if low_data:
        signals.append(f"Limited public data for {vendor} — direct verification required.")
    for cat in high_cats[:2]:
        evt = (cat_results[cat].get("observed_events") or [""])[0]
        signals.append(f"Elevated {cat} risk ({cat_results[cat]['score']}/100): {str(evt)[:80]}")
    if not signals:
        signals.append(f"No major risk events found publicly for {vendor} in 2023-2025.")

    top_cat = max(cat_results, key=lambda c: cat_results[c]["score"])
    return {
        "risk_level":      level,
        "key_signals":     signals[:3],
        "gaps":            [
            f"No audited financial statements found publicly for {vendor}.",
            f"Limited regulatory filing history available for {industry} sector in {country}.",
        ],
        "recommendations": [
            f"Request latest audited financials and board resolutions from {vendor}.",
            f"Run background check on key executives — {top_cat} risk is highest.",
            "Include data-security and compliance clauses in contract.",
        ],
        "filings_summary": (
            f"No substantial public filings found for {vendor}. Direct verification recommended."
            if low_data else
            f"{vendor} operates in the {industry} sector in {country}. Check MCA/ROC or equivalent filings."
        ),
    }


def _unknown_defaults(cat, vendor):
    return {
        "score":            30,
        "summary":          f"No public evidence found for {vendor} in the {cat} category. Absence of data does not confirm low risk.",
        "severity_reason":  "Score reflects data unavailability, not confirmed low risk.",
        "observed_events":  ["No verifiable public records found in 2023-2025."],
        "evidence_urls":    [],
    }


def _analyze_category(cat, vendor, data, industry, country, city, financial_metrics):
    cat_data = data.get(cat, {})
    evidence = cat_data.get("text","") if isinstance(cat_data,dict) else ""
    urls     = cat_data.get("urls",[]) if isinstance(cat_data,dict) else []
    hits     = cat_data.get("hit_count",0)

    print(f"  🔌 {cat} ({hits} hits)…")

    if not evidence.strip():
        if cat == "financial" and financial_metrics:
            raw    = _groq(_financial_prompt(vendor,industry,country,city,"", [],financial_metrics),700)
            parsed = _parse_json(raw)
            if isinstance(parsed,dict) and "score" in parsed:
                parsed["score"] = max(0,min(int(parsed["score"]),100))
                print(f"     → financial (metrics only): {parsed['score']}")
                return cat, parsed
        r = _unknown_defaults(cat,vendor)
        print(f"     → {cat}: no evidence, default {r['score']}")
        return cat, r

    if cat == "financial":
        raw = _groq(_financial_prompt(vendor,industry,country,city,evidence,urls,financial_metrics),700)
    else:
        raw = _groq(_category_prompt(cat,vendor,industry,country,city,evidence,urls),600)

    parsed = _parse_json(raw)
    if isinstance(parsed,dict) and "score" in parsed:
        parsed["score"] = max(0,min(int(parsed["score"]),100))
        if parsed["score"]==0 and hits>0: parsed["score"]=15
        if "events" in parsed and "observed_events" not in parsed:
            parsed["observed_events"] = parsed.pop("events")
        print(f"     → {cat}: {parsed['score']}")
        return cat, parsed

    print(f"     ⚠  {cat}: parse failed, defaults")
    return cat, _unknown_defaults(cat,vendor)


def analyze_vendor_full(vendor, data, country, industry, concerns="", financial_metrics=None):
    if not data:            data = {}
    if not financial_metrics: financial_metrics = {}

    meta    = data.get("meta",{})
    city    = meta.get("city","")
    country = meta.get("country", country)
    total_hits = sum(data.get(c,{}).get("hit_count",0) for c in RISK_CATEGORIES)

    print(f"\n🤖 AI (FULL PARALLEL): {vendor} | hits:{total_hits}\n")

    # Profile text
    parts = []
    for key in ("profile","key_person","reputation"):
        d = data.get(key,{})
        t = d.get("text","") if isinstance(d,dict) else ""
        if t.strip(): parts.append(t)
    combined_profile = "\n\n".join(parts)

    # Company description for synthesis (from profile)
    company_desc = data.get("profile",{}).get("description","")

    cat_results = {}

    def _do_profile():
        if combined_profile.strip():
            raw = _groq(_profile_prompt(vendor,industry,country,city,combined_profile),400)
            return _parse_json(raw)
        return {}

    with ThreadPoolExecutor(max_workers=6) as ex:
        future_map = {
            ex.submit(_analyze_category,cat,vendor,data,industry,country,city,financial_metrics): cat
            for cat in RISK_CATEGORIES
        }
        prof_future = ex.submit(_do_profile)
        for fut in as_completed(future_map):
            cat, result = fut.result()
            cat_results[cat] = result
        parsed_prof = prof_future.result()

    # Synthesis
    print("  🧩 Synthesis…")
    raw_synth = _groq(
        _synthesis_prompt(vendor,industry,country,city,cat_results,concerns,total_hits,company_desc),
        max_tokens=900,
    )
    synth = _parse_json(raw_synth)

    def _pval(key):
        v = str(parsed_prof.get(key,"")).strip()
        return v if v and v.lower() not in ("not available","n/a","none","unknown","") else "Not Available"

    company_profile = {
        "ceo":          _pval("ceo"),
        "founder":      _pval("founder"),
        "founded":      _pval("founded"),
        "headquarters": _pval("headquarters"),
        "employees":    _pval("employees"),
        "description":  _pval("description"),
        "industry":     industry,
    }
    if company_profile["headquarters"]=="Not Available" and city:
        company_profile["headquarters"] = f"{city}, {country}"
    if financial_metrics:
        company_profile["financial_metrics"] = {k:v for k,v in financial_metrics.items() if v not in (None,"","N/A","Not Available")}

    required = ("key_signals","gaps","recommendations","filings_summary")
    missing  = [k for k in required if not synth.get(k)]
    if missing:
        fb = _fallback_synthesis(vendor,industry,country,cat_results,total_hits)
        for k in missing: synth[k]=fb[k]
        if "risk_level" not in synth: synth["risk_level"]=fb["risk_level"]
    for k in required:
        if isinstance(synth.get(k),list) and not synth[k]:
            synth[k]=_fallback_synthesis(vendor,industry,country,cat_results,total_hits)[k]

    has_metrics = bool(financial_metrics)
    confidence  = (
        20 if total_hits==0 and not has_metrics else
        45 if total_hits<5  else
        70 if total_hits<15 else 88
    )
    if has_metrics: confidence = min(confidence+10,95)

    return {
        "company_profile":  company_profile,
        "risk_scores":      {cat: cat_results[cat]["score"] for cat in RISK_CATEGORIES},
        "explanations":     {
            cat: {
                "summary":         cat_results[cat].get("summary",""),
                "severity_reason": cat_results[cat].get("severity_reason",""),
                "observed_events": cat_results[cat].get("observed_events",[]),
                **({"key_metrics": cat_results[cat]["key_metrics"]}
                   if cat=="financial" and "key_metrics" in cat_results[cat] else {}),
            }
            for cat in RISK_CATEGORIES
        },
        "evidence_links":   {cat: cat_results[cat].get("evidence_urls",[]) for cat in RISK_CATEGORIES},
        "key_signals":      synth.get("key_signals",[]),
        "gaps":             synth.get("gaps",[]),
        "recommendations":  synth.get("recommendations",[]),
        "filings_summary":  synth.get("filings_summary","No public filings found."),
        "risk_level":       synth.get("risk_level","Medium"),
        "confidence_score": confidence,
        "total_hits":       total_hits,
    }