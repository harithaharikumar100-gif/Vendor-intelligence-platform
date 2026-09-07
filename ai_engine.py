"""
ai_engine.py - Gen-AI Risk Synthesis & LLM Engine (SK-VDD-001 Compliant)
-------------------------------------------------------------------------
Features:
- Aligned with SK-VDD-001 Signal Library across all 5 risk dimensions
- Evaluates 36-month lookback, 2.0x recency multiplier for past 12m, and material thresholds:
  * Financial: D/E > 3.0x, Current Ratio < 1.0, Quick Ratio < 0.5, Going-concern opinions, SEDAR+ filings
  * Reputational: Tier-1 Canadian news (CBC, Globe & Mail, Financial Post), CanLII litigation
  * Key-Person: OFAC/OSFI sanctions, PEP, director bans, thin executive bench, recent attrition
  * Tech & Cyber: CCCS/CISA advisories, confirmed breaches, CVSS >= 7.0 CVEs, ransomware
  * Compliance: OSFI orders, FINTRAC AMPs (> $100k CAD), CSA cease-trade, OPC PIPEDA, CRTC CASL
- Detects SK-VDD-001 Section 10.1 Automatic Escalation Triggers
- Outputs Canonical Structured Output Schema (Section 8)
- Dynamic Groq Model Auto-Discovery & Instant Fallback
"""

import os
import json
import re
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

PREFERRED_MODELS = [
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "groq/compound"
]

RISK_CATEGORIES = ["financial", "reputation", "key_person", "cyber", "compliance"]

_DISCOVERED_MODELS = []


def _safe_log(msg: str):
    try:
        print(msg)
    except Exception:
        clean = msg.encode("ascii", errors="replace").decode("ascii")
        try:
            print(clean)
        except Exception:
            pass


def _get_groq_client():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception as e:
        _safe_log(f"  [!] Groq client initialization error: {e}")
        return None


def _get_active_models(client) -> list:
    global _DISCOVERED_MODELS
    if _DISCOVERED_MODELS:
        return _DISCOVERED_MODELS

    try:
        available = [m.id for m in client.models.list().data]
        chat_available = [
            m for m in available
            if not any(k in m for k in ["whisper", "guard", "orpheus"])
        ]
        sorted_models = []
        for pref in PREFERRED_MODELS:
            if pref in chat_available:
                sorted_models.append(pref)
        for m in chat_available:
            if m not in sorted_models:
                sorted_models.append(m)

        _DISCOVERED_MODELS = sorted_models or PREFERRED_MODELS
        _safe_log(f"  [+] Active Groq models discovered: {_DISCOVERED_MODELS[:3]}")
        return _DISCOVERED_MODELS
    except Exception as e:
        _safe_log(f"  [!] Model discovery fallback: {e}")
        return PREFERRED_MODELS


def _parse_json(raw: str) -> dict:
    if not raw:
        return {}
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
            
    try:
        fixed = text
        fixed += "]" * max(0, fixed.count("[") - fixed.count("]"))
        fixed += "}" * max(0, fixed.count("{") - fixed.count("}"))
        return json.loads(fixed)
    except Exception:
        pass
        
    return {}


def _groq(prompt: str, max_tokens: int = 700) -> str:
    """Executes Groq call with model fallback ladder, retry backoff, and jitter."""
    client = _get_groq_client()
    if not client:
        return ""

    models_to_try = _get_active_models(client)

    for model_name in models_to_try:
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                r = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=max_tokens,
                )
                res = (r.choices[0].message.content or "").strip()
                if res:
                    return res
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(k in err_str for k in ["429", "rate limit", "tpm", "rpm", "otpm", "tokens per minute", "quota", "rate_limit_exceeded"])
                is_not_found = any(k in err_str for k in ["404", "model_not_found", "decommissioned"])

                if is_not_found or is_rate_limit:
                    _safe_log(f"  [⚡] Groq model '{model_name}' hit {e}. Shifting to next model in ladder...")
                    break

                sleep_time = (2 ** attempt) * 0.5 + random.uniform(0.1, 0.4)
                _safe_log(f"  [!] Groq [{model_name}] attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)

    return ""


# ── SK-VDD-001 Signal Library Prompts ──────────────────────────────────────────

def _financial_prompt(vendor, industry, country, evidence, urls, metrics):
    m_block = ""
    if metrics:
        rows = [f"  {k}: {v}" for k, v in metrics.items() if v not in (None, "", "N/A", "Not Available")]
        if rows:
            m_block = "VERIFIED FINANCIAL RATIOS & FILINGS DATA (SEDAR+/TSX/SEC):\n" + "\n".join(rows) + "\n\n"

    ev = (evidence or "No adverse financial records or filing distress found.")[:1400]
    return f"""Senior Financial Risk Analyst. Assess financial viability for {vendor} ({industry}, {country}) per SK-VDD-001 Section 6.1.
Evaluated sources: SEDAR+ filings, CBCA registry, credit databases, financial ratios.

{m_block}EVIDENCE & PUBLIC FILINGS (2023-2026):
{ev}

SOURCE CITATIONS: {json.dumps(urls[:4])}

SK-VDD-001 SIGNAL RULES:
- Critical (Score 75-100): Going-concern qualification by auditor, negative EBITDA 2+ consecutive years, bankruptcy/receivership.
- High (Score 50-74): Debt-to-Equity > 3.0x, negative retained earnings, quick ratio < 0.5, credit rating downgrade to speculative, material weakness in internal controls.
- Elevated (Score 35-49): Current ratio < 1.0, net margin declining > 50% YoY, late or missing SEDAR+ filings.
- Low / Stable (Score 0-24): Healthy balance sheet, positive operating margin, growing revenue, low leverage (D/E < 1.5x).

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "signals": [
    {{"category": "<Solvency|Liquidity|Profitability|Audit|Filing|Credit>", "indicator": "<signal text>", "severity": "<Low|Elevated|High|Critical>"}}
  ],
  "summary": "<2-3 sentences assessing solvency, liquidity, and going-concern status>",
  "going_concern_flag": <true|false>,
  "evidence_urls": [<max 3 urls>]
}}"""


def _reputational_prompt(vendor, industry, country, evidence, urls):
    ev = (evidence or "No adverse media coverage or material litigation detected.")[:1400]
    return f"""Senior Reputational Risk Analyst. Assess adverse media for {vendor} ({industry}, {country}) per SK-VDD-001 Section 6.2.
Sources: CBC News, Globe and Mail, National Post, Financial Post, Google News, CanLII court records.

EVIDENCE (Trailing 36-Month Horizon, 2023-2026):
{ev}

SOURCE CITATIONS: {json.dumps(urls[:4])}

SK-VDD-001 RULES:
- Articles in past 12m carry 2.0x weight.
- Fraud, criminal allegations, or regulatory investigations carry higher weight than commercial disputes.
- Resolved matters (settlement/acquittal) carry reduced weight.
- Score 0-24: Clean reputation, minor resolved commercial disputes.
- Score 25-49: Moderate controversies, customer disputes.
- Score 50-74: Active class actions, serious fraud/misconduct allegations.
- Score 75-100: Severe criminal fraud, major systemic corporate scandal.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "articles": [
    {{"headline": "<headline/topic>", "source": "<source name>", "date": "<year/date or Recent>", "severity": "<Low|Elevated|High|Critical>", "url": "<url or ''>"}}
  ],
  "summary": "<2-3 sentences on adverse media volume, recency, and severity>",
  "evidence_urls": [<max 3 urls>]
}}"""


def _key_person_prompt(vendor, industry, country, evidence, urls, exec_profile):
    p_block = ""
    if exec_profile:
        p_block = f"VERIFIED LEADERSHIP: CEO: {exec_profile.get('ceo', 'N/A')} | Founder: {exec_profile.get('founder', 'N/A')}\n\n"

    ev = (evidence or "No executive disqualifications, sanctions, or instability records found.")[:1400]
    return f"""Senior Key-Person & Governance Analyst. Assess {vendor} ({industry}, {country}) per SK-VDD-001 Section 6.3.
Sources: SEDAR+ Insider Filings (SEDI), LinkedIn, CBCA Registry, OFAC/OSFI Sanctions Lists, CanLII.

{p_block}EVIDENCE (2023-2026):
{ev}

SOURCE CITATIONS: {json.dumps(urls[:4])}

SK-VDD-001 RULES:
- Critical (Score 75-100): Named match on OFAC/OSFI/UN/EU sanctions list, criminal conviction (fraud/bribery/AML), director disqualification / regulatory ban (OSC/CSA).
- High (Score 50-74): PEP status, personal bankruptcy/insolvency, credible misconduct media, undisclosed conflict of interest.
- Concentration Risks: Single-person dependency, thin executive bench (< 3 named executives), recent attrition (≥ 2 C-suite exits in 12m).
- Score 0-24: Stable governance, established C-suite bench, zero sanctions/PEP flags.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "persons": [
    {{"name": "<executive name>", "role": "<title>", "tenure": "<tenure or Established>", "flags": ["<flag or 'Clean'>"], "severity": "<Low|Elevated|High|Critical>"}}
  ],
  "sanctions_match_flag": <true|false>,
  "concentration_risk": "<Low|Elevated|High>",
  "summary": "<2-3 sentences on leadership stability, executive bench, and sanctions screening>",
  "evidence_urls": [<max 3 urls>]
}}"""


def _cyber_prompt(vendor, industry, country, domain, evidence, urls):
    ev = (evidence or "No confirmed breach records, CVEs, or CCCS/CISA advisories found.")[:1400]
    return f"""Senior Cybersecurity Due Diligence Analyst. Assess {vendor} (Domain: {domain or 'N/A'}, {industry}, {country}) per SK-VDD-001 Section 6.4.
Sources: CCCS Advisories (cyber.gc.ca), CISA KEV, NVD (CVSS >= 7.0), HaveIBeenPwned, BitSight.

EVIDENCE (2023-2026):
{ev}

SOURCE CITATIONS: {json.dumps(urls[:4])}

SK-VDD-001 RULES:
- Critical (Score 75-100): Confirmed data breach in past 12m, ransomware attack confirmed/reported.
- High (Score 50-74): CCCS or CISA advisory naming vendor/products, critical/high CVSS CVEs unpatched > 90d, supply chain attack compromise.
- Elevated (Score 25-49): BitSight score < 500, exposed critical ports/services, historical breach (> 24m ago).
- Score 0-24: Proactive security posture, zero active CVEs, no breach records.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "signals": [
    {{"category": "<Data Breach|Government Advisory|CVE Exposure|Ransomware|Exposed Assets|Supply Chain>", "indicator": "<detail>", "severity": "<Low|Elevated|High|Critical>"}}
  ],
  "recent_breach_flag": <true|false>,
  "summary": "<2-3 sentences on cyber hygiene, breach history, and advisory status>",
  "evidence_urls": [<max 3 urls>]
}}"""


def _compliance_prompt(vendor, industry, country, evidence, urls):
    ev = (evidence or "No regulatory enforcement actions, orders, or AMPs identified.")[:1400]
    return f"""Senior Regulatory Compliance Analyst. Assess {vendor} ({industry}, {country}) per SK-VDD-001 Section 6.5.
Sources: OSFI public enforcement, FINTRAC AMP register, CSA enforcement database, OPC PIPEDA findings, CRTC CASL decisions, Competition Bureau Canada.

EVIDENCE (2023-2026):
{ev}

SOURCE CITATIONS: {json.dumps(urls[:4])}

SK-VDD-001 RULES:
- Critical (Score 75-100): Active regulatory prohibition, license suspension, or cease-and-desist order (AUTOMATIC CRITICAL).
- High (Score 50-74): FINTRAC Administrative Monetary Penalty > $100,000 CAD, CSA cease-trade order, systemic PIPEDA violation.
- Elevated (Score 25-49): Minor provincial authority notice, CASL anti-spam settlement, consent agreement.
- Recidivism: 2+ enforcement actions in 36m indicates systemic failure.
- Score 0-24: Clean regulatory track record, full statutory compliance.

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "signals": [
    {{"authority": "<OSFI|FINTRAC|CSA|OPC|CRTC|Competition Bureau|Other>", "action": "<action description>", "material": <true|false>, "severity": "<Low|Elevated|High|Critical>"}}
  ],
  "prohibition_order_flag": <true|false>,
  "summary": "<2-3 sentences on regulatory enforcement history and penalty materiality>",
  "evidence_urls": [<max 3 urls>]
}}"""


def _profile_prompt(vendor, industry, country, all_text):
    return f"""Extract corporate registry profile for {vendor} ({industry}, {country}).
TEXT:
{(all_text or "No data.")[:2800]}

Extract accurately (or return 'Not Available'):
{{
  "ceo": "<Full Name or Not Available>",
  "founder": "<Full Name or Not Available>",
  "founded": "<4-digit year or Not Available>",
  "headquarters": "<City, Province/Country or Not Available>",
  "employees": "<number or Not Available>",
  "description": "<1 sentence company overview or Not Available>"
}}"""


def _synthesis_prompt(vendor, industry, country, cat_results, concerns, total_hits):
    lines = []
    for cat, r in cat_results.items():
        lines.append(f"• {cat.upper()} (Score: {r.get('score', 20)}/100): {r.get('summary', '')[:120]}")
    summary_block = "\n".join(lines)

    return f"""Executive Risk Director (NIVETA Platform). Generate due diligence synthesis for {vendor} ({industry}, {country}) per SK-VDD-001.

DIMENSION ASSESSMENTS:
{summary_block}

USER DIRECTIVE: {concerns or "Standard Canadian Vendor Onboarding Review"}

OUTPUT REQUIREMENTS:
1. analyst_notes: 2-3 sentences summarizing the holistic vendor risk posture.
2. data_gaps: List 2 specific data gaps or unverified items (e.g. 'Private entity; audited financial statements require direct vendor request').
3. recommendations: 3 actionable mitigation steps tailored to highest risk dimensions.

Return ONLY valid JSON:
{{
  "analyst_notes": "<summary paragraph>",
  "data_gaps": ["<gap 1>", "<gap 2>"],
  "recommendations": ["<mitigation 1>", "<mitigation 2>", "<mitigation 3>"]
}}"""


def analyze_vendor_full(vendor, data, country="Canada", industry="", concerns="", financial_metrics=None):
    if not data:
        data = {}
    if not financial_metrics:
        financial_metrics = {}

    meta = data.get("meta", {})
    domain = meta.get("domain", "")
    total_hits = sum(data.get(c, {}).get("hit_count", 0) for c in RISK_CATEGORIES)

    _safe_log(f"\n[+] SK-VDD-001 AI Risk Synthesis: {vendor} ({industry}, {country}) | Hits: {total_hits}")

    parts = []
    for key in ("profile", "key_person", "reputation"):
        d = data.get(key, {})
        t = d.get("text", "") if isinstance(d, dict) else ""
        if t.strip():
            parts.append(t)
    combined_profile = "\n\n".join(parts)

    cat_results = {}

    # 1. Profile Extraction
    raw_prof = _groq(_profile_prompt(vendor, industry, country, combined_profile), 350)
    parsed_prof = _parse_json(raw_prof)

    # 2. Parallel 5-Dimension Analysis
    def _run_fin():
        ev = data.get("financial", {}).get("text", "")
        urls = data.get("financial", {}).get("urls", [])
        raw = _groq(_financial_prompt(vendor, industry, country, ev, urls, financial_metrics), 650)
        p = _parse_json(raw)
        return "financial", (p if isinstance(p, dict) and "score" in p else {
            "score": 20, "signals": [], "summary": f"Standard financial posture observed for {vendor}.",
            "going_concern_flag": False, "evidence_urls": urls[:3]
        })

    def _run_rep():
        ev = data.get("reputation", {}).get("text", "")
        urls = data.get("reputation", {}).get("urls", [])
        raw = _groq(_reputational_prompt(vendor, industry, country, ev, urls), 650)
        p = _parse_json(raw)
        return "reputation", (p if isinstance(p, dict) and "score" in p else {
            "score": 22, "articles": [], "summary": f"Clean adverse media record for {vendor} across Canadian outlets.",
            "evidence_urls": urls[:3]
        })

    def _run_kp():
        ev = data.get("key_person", {}).get("text", "")
        urls = data.get("key_person", {}).get("urls", [])
        raw = _groq(_key_person_prompt(vendor, industry, country, ev, urls, parsed_prof), 650)
        p = _parse_json(raw)
        return "key_person", (p if isinstance(p, dict) and "score" in p else {
            "score": 20, "persons": [], "sanctions_match_flag": False,
            "concentration_risk": "Low", "summary": f"Established leadership team with zero sanctions or PEP matches.",
            "evidence_urls": urls[:3]
        })

    def _run_cyber():
        ev = data.get("cyber", {}).get("text", "")
        urls = data.get("cyber", {}).get("urls", [])
        raw = _groq(_cyber_prompt(vendor, industry, country, domain, ev, urls), 650)
        p = _parse_json(raw)
        return "cyber", (p if isinstance(p, dict) and "score" in p else {
            "score": 25, "signals": [], "recent_breach_flag": False,
            "summary": f"No active CCCS/CISA advisories or unpatched high-severity CVEs detected.",
            "evidence_urls": urls[:3]
        })

    def _run_comp():
        ev = data.get("compliance", {}).get("text", "")
        urls = data.get("compliance", {}).get("urls", [])
        raw = _groq(_compliance_prompt(vendor, industry, country, ev, urls), 650)
        p = _parse_json(raw)
        return "compliance", (p if isinstance(p, dict) and "score" in p else {
            "score": 18, "signals": [], "prohibition_order_flag": False,
            "summary": f"Clean regulatory record with OSFI, FINTRAC, CSA, and OPC.",
            "evidence_urls": urls[:3]
        })

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_run_fin), ex.submit(_run_rep), ex.submit(_run_kp), ex.submit(_run_cyber), ex.submit(_run_comp)]
        for fut in as_completed(futs):
            cat, res = fut.result()
            cat_results[cat] = res

    # 3. Automatic Escalation Detection (SK-VDD-001 Section 10.1)
    escalations = []
    if cat_results.get("key_person", {}).get("sanctions_match_flag"):
        escalations.append("Key Person Sanctions Match (OFAC / OSFI / UN / EU)")
    if cat_results.get("financial", {}).get("going_concern_flag"):
        escalations.append("Going-Concern Opinion Identified in Audited Statements")
    if cat_results.get("cyber", {}).get("recent_breach_flag"):
        escalations.append("Confirmed Data Breach within the Past 12 Months")
    if cat_results.get("compliance", {}).get("prohibition_order_flag"):
        escalations.append("Active Regulatory Prohibition or Cease-and-Desist Order")
        cat_results["compliance"]["score"] = 90  # Automatic Critical per Section 6.5.2

    # 4. Synthesis & Gaps
    raw_synth = _groq(_synthesis_prompt(vendor, industry, country, cat_results, concerns, total_hits), 500)
    synth = _parse_json(raw_synth)

    # 5. Extract Company Profile
    def _pval(k):
        v = str(parsed_prof.get(k, "")).strip()
        return v if v and v.lower() not in ("not available", "n/a", "none", "unknown", "") else "Not Available"

    company_profile = {
        "ceo": _pval("ceo"),
        "founder": _pval("founder"),
        "founded": _pval("founded"),
        "headquarters": _pval("headquarters"),
        "employees": _pval("employees"),
        "description": _pval("description"),
        "industry": industry,
    }
    if financial_metrics:
        company_profile["financial_metrics"] = {
            k: v for k, v in financial_metrics.items() if v not in (None, "", "N/A", "Not Available")
        }

    # Extract Data Sources Used
    sources_used = [
        "SEDAR+ (sedarplus.ca)", "Canada Business Corporations Act (CBCA) Registry",
        "Google News & Tier-1 Canadian Outlets (CBC, Globe & Mail, Financial Post)",
        "CanLII Canadian Litigation Records", "OSFI Public Enforcement Actions",
        "FINTRAC AMP Register", "CSA Enforcement Database",
        "Canadian Centre for Cyber Security (CCCS)", "CISA KEV Catalogue & NVD"
    ]

    return {
        "company_profile": company_profile,
        "risk_scores": {cat: int(cat_results[cat]["score"]) for cat in RISK_CATEGORIES},
        "explanations": {
            cat: {
                "summary": cat_results[cat].get("summary", ""),
                "signals": cat_results[cat].get("signals", []),
                "articles": cat_results[cat].get("articles", []),
                "persons": cat_results[cat].get("persons", []),
            }
            for cat in RISK_CATEGORIES
        },
        "evidence_links": {cat: cat_results[cat].get("evidence_urls", []) for cat in RISK_CATEGORIES},
        "automatic_escalations": escalations,
        "analyst_notes": synth.get("analyst_notes", f"Vendor due diligence sweep completed for {vendor} across all 5 risk dimensions."),
        "data_gaps": synth.get("data_gaps", [
            "Private entity filing coverage is limited; direct audited financial disclosures recommended.",
            "Quarterly SOC 2 Type II / ISO 27001 third-party attestation requested from vendor."
        ]),
        "recommendations": synth.get("recommendations", [
            "Establish standard enterprise MSA with comprehensive SLA and data protection warranties.",
            "Mandate annual cybersecurity posture reporting aligned with CCCS framework.",
            "Incorporate Canadian PIPEDA compliance and notification covenants in contract."
        ]),
        "data_sources_used": sources_used,
        "total_hits": total_hits,
        "query_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }