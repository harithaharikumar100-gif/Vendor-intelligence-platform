"""
ai_engine.py - Multi-Provider Gen-AI Risk Synthesis & Autonomous SK-VDD-001 Rule Engine
----------------------------------------------------------------------------------------
Supported AI Providers (Automatic Auto-Failover):
1. Google Gemini (GEMINI_API_KEY) - Generous Free Tier (15 RPM / 1M TPM)
2. Groq Cloud (GROQ_API_KEY) - Ultra-fast multi-model ladder
3. OpenAI (OPENAI_API_KEY) - gpt-4o-mini
4. Autonomous SK-VDD-001 Rule Engine (Zero-Key Fallback) - Generates complete 5-dimension risk synthesis even if AI quotas are exhausted!
"""

import os
import json
import re
import time
import random
import threading
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as _FutureTimeoutError
from dotenv import load_dotenv

import config
import licensed_sources
import cyber_intel
import sanctions_check
import frameworks

load_dotenv()

# SK-VDD-001 Section 6.1.2: deterministic keyword detection for audit-opinion
# red flags. These are Critical/High severity findings that should not depend
# on an LLM's discretion — if the underlying evidence text literally contains
# these phrases, the flag must fire.
_GOING_CONCERN_PATTERNS = [
    r"going[\s-]concern", r"substantial doubt", r"material uncertaint\w* relat\w* to going concern",
]
_MATERIAL_WEAKNESS_PATTERNS = [
    r"material weakness in internal control",
]

# Section 6.1.1: "identify any dissolution notices or receivership filings."
# Same deterministic-not-LLM-discretion treatment as going-concern above.
_DISSOLUTION_PATTERNS = [
    r"\bdissolv\w*\b", r"\bstruck\b", r"\breceivership\b", r"\bin receiver\w*\b",
    r"\bwound[\s-]up\b", r"\bwinding[\s-]up\b", r"\bceased to exist\b",
]


def _detect_financial_red_flags(evidence_text: str) -> dict:
    """Section 6.1.2 Audit signals: deterministic keyword scan, not LLM discretion."""
    text = (evidence_text or "").lower()
    return {
        "going_concern": any(re.search(p, text) for p in _GOING_CONCERN_PATTERNS),
        "material_weakness": any(re.search(p, text) for p in _MATERIAL_WEAKNESS_PATTERNS),
    }


def _detect_dissolution_status(evidence_text: str) -> bool:
    """
    Section 6.1.1: "confirm active good standing, identify any dissolution
    notices or receivership filings." A false positive here is as serious a
    claim as a false sanctions match, so this reuses the negation-aware
    matching already proven in frameworks.py — "no dissolution notices were
    found" must not be misread as a dissolution finding.
    """
    text = (evidence_text or "").lower()
    for p in _DISSOLUTION_PATTERNS:
        m = re.search(p, text)
        if m and not frameworks._is_negated(text, m.start()):
            return True
    return False

PREFERRED_MODELS = [
    # Diagnosed live (see git history): these two return correct JSON at
    # our real ~700-token budget, so they go first for the common case.
    "qwen/qwen3.8-27b",
    "allam-2-7b",
    "qwen/qwen3.6-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    # openai/gpt-oss-* are reasoning models: confirmed live they burn nearly
    # the entire token budget on hidden chain-of-thought (698 of 700 tokens)
    # before ever writing an answer, which is why they always logged
    # "returned empty response" - not flaky, structurally guaranteed at this
    # budget. _call_groq sends reasoning_effort="low" for these specifically
    # (confirmed live: cuts reasoning tokens to ~110-140, actually leaving
    # room for the answer) - passing that param to a non-reasoning model is a
    # hard 400 error, confirmed live on allam-2-7b, so it must stay scoped.
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    # groq/compound and groq/compound-mini deliberately excluded: they're
    # Groq's agentic "tool use" models, not plain chat models, and confirmed
    # live to 413 ("Request Entity Too Large") on every prompt size this
    # pipeline sends, including the smallest (250-token profile prompt) -
    # every attempt on them is a guaranteed-wasted round trip, and their
    # internal tool-calling likely explains some of this session's
    # multi-minute stalls.
]

RISK_CATEGORIES = ["financial", "reputation", "key_person", "cyber", "compliance"]

_DISCOVERED_MODELS = []
# Concurrent /api/analyze requests run analyze_vendor_full on different
# threadpool threads, and each can reach _call_groq -> mutate this list.
_MODELS_LOCK = threading.Lock()


def _safe_log(msg: str):
    try:
        print(msg)
    except Exception:
        clean = msg.encode("ascii", errors="replace").decode("ascii")
        try:
            print(clean)
        except Exception:
            pass


# ─── Multi-Provider Unified LLM Dispatch ──────────────────────────────────────

def _call_gemini(prompt: str, max_tokens: int = 400) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return ""
    # gemini-1.5-* / gemini-2.0-* were retired by Google (confirmed via direct
    # API probe — they now 404 with "use models/gemini-3.6-flash"). The
    # "-latest" aliases auto-track whatever Google's current model is, so
    # they're used first to avoid this going stale again next time Google
    # retires a version; gemini-3.6-flash is kept as an explicit pin in case
    # the alias itself becomes unavailable or overloaded (HTTP 503).
    for model in ["gemini-flash-latest", "gemini-3.6-flash", "gemini-pro-latest"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            r = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": max_tokens,
                        # Gemini 3.x models "think" before answering, and that
                        # reasoning silently consumes maxOutputTokens, leaving
                        # nothing for the actual answer (observed: finishReason
                        # MAX_TOKENS after 12 visible tokens vs. 452 thinking
                        # tokens). Disabling it makes the visible answer the
                        # whole budget again.
                        "thinkingConfig": {"thinkingBudget": 0},
                    }
                },
                timeout=15
            )
            if r.status_code == 200:
                d = r.json()
                candidates = d.get("candidates", [])
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                finish_reason = candidates[0].get("finishReason", "")
                if text.strip() and finish_reason != "MAX_TOKENS":
                    return text.strip()
        except Exception:
            pass
    return ""


def _call_openai(prompt: str, max_tokens: int = 400) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return ""
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": max_tokens
            },
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=12
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return ""


def _call_groq(prompt: str, max_tokens: int = 400, model_hint: str = None) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return ""
    try:
        from groq import Groq
        # Gemini (timeout=15) and OpenAI (timeout=12) below both bound their
        # request time; this client had none, so an SDK-default-timeout or
        # a plain stalled connection here blocked the ENTIRE analysis
        # indefinitely instead of failing over to the next model/provider
        # (confirmed live: a request hung for 15+ minutes with zero log
        # output mid-way through Phase 2, versus every other observed call
        # in this codebase resolving in 1-3s). 20s keeps us well under the
        # 2-attempt-per-model retry budget while still failing fast enough
        # to move on to the next of ~6 models.
        client = Groq(api_key=key, timeout=20)
    except Exception:
        return ""

    global _DISCOVERED_MODELS
    with _MODELS_LOCK:
        if not _DISCOVERED_MODELS:
            try:
                # "compound"/"compound-mini" excluded outright, not just left
                # off PREFERRED_MODELS - they'd otherwise get appended here as
                # "discovered but unlisted" and still get tried as a last
                # resort, but they're confirmed to 413 on every prompt size
                # this pipeline sends, so every attempt is pure wasted latency.
                avail = [
                    m.id for m in client.models.list().data
                    if not any(k in m.id for k in ["whisper", "guard", "orpheus", "compound"])
                ]
                _DISCOVERED_MODELS = [m for m in PREFERRED_MODELS if m in avail] + [m for m in avail if m not in PREFERRED_MODELS]
            except Exception:
                _DISCOVERED_MODELS = PREFERRED_MODELS

    models = [model_hint] + [m for m in _DISCOVERED_MODELS if m != model_hint] if model_hint else _DISCOVERED_MODELS

    # Overall wall-clock budget across the whole model cascade for this one
    # call. Without this, an individually-reasonable per-model timeout (20s)
    # still multiplies across ~6 models x 2 attempts into several minutes
    # whenever Groq's queue_time is elevated - every individual call
    # "succeeds" within its own timeout, just slowly, so nothing else here
    # catches it. The 5-dimension loop in analyze_vendor_full already always
    # runs the deterministic autonomous rule engine as a backfill regardless
    # of whether AI synthesis succeeds, so giving up on remaining models
    # sooner costs detail, not correctness.
    deadline = time.time() + 25
    for m_name in models:
        if time.time() > deadline:
            _safe_log(f"  [!] Groq cascade budget (25s) exceeded, giving up for this call")
            break
        for attempt in range(2):
            try:
                kwargs = dict(
                    model=m_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=max_tokens
                )
                # gpt-oss-* are reasoning models: without this, they spend
                # nearly the whole max_tokens budget on hidden chain-of-
                # thought and return empty content (confirmed live: 698 of
                # 700 tokens went to invisible reasoning). "low" is the
                # minimum Groq accepts and still leaves room for an actual
                # answer. Every other model in PREFERRED_MODELS 400s on this
                # param (confirmed live on allam-2-7b), so it must stay
                # scoped to gpt-oss specifically.
                if "gpt-oss" in m_name:
                    kwargs["reasoning_effort"] = "low"
                # A hard EXTERNAL deadline, not just the client's own
                # timeout=20 constructor arg - confirmed live that the SDK
                # parameter alone does not reliably bound wall-clock time
                # (a call stalled well past 20s with the client timeout
                # already in place). Running the blocking call in its own
                # one-shot thread and bounding .result() ourselves gives a
                # real ceiling regardless of what the SDK/transport does
                # internally. shutdown(wait=False) is deliberate: a `with`
                # block (or wait=True) would block HERE until the abandoned
                # thread finishes, which defeats the entire point on a call
                # that's genuinely stuck - the thread is left to finish (or
                # never finish) on its own and its result is discarded.
                _ex = ThreadPoolExecutor(max_workers=1)
                try:
                    _fut = _ex.submit(client.chat.completions.create, **kwargs)
                    r = _fut.result(timeout=12)
                finally:
                    _ex.shutdown(wait=False)
                res = (r.choices[0].message.content or "").strip()
                if res:
                    stripped = res.rstrip()
                    if stripped.startswith('{') and not stripped.endswith('}') and not stripped.endswith(']'):
                        _safe_log(f"  [~] Groq model {m_name} returned truncated JSON, trying next model...")
                        break
                    # Validate response contains parseable JSON before accepting
                    if _parse_json(res):
                        return res
                    _safe_log(f"  [~] Groq model {m_name} returned non-JSON response, trying next model...")
                    break
                else:
                    _safe_log(f"  [~] Groq model {m_name} returned empty response, trying next model...")
                    break
            except _FutureTimeoutError:
                _safe_log(f"  [!] Groq model {m_name} exceeded 12s hard timeout, trying next model...")
                break
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str:
                    if attempt < 1:
                        _safe_log(f"  [~] Groq model {m_name} rate limited, retrying in 3s...")
                        time.sleep(3)
                        continue
                    _safe_log(f"  [!] Groq model {m_name} rate limited, trying next model...")
                    break
                if "413" in err_str or "entity too large" in err_str:
                    _safe_log(f"  [!] Groq model {m_name} prompt too large, trying next model...")
                    break
                _safe_log(f"  [!] Groq model {m_name} error: {str(e)[:100]}")
                break

    return ""


def _looks_like_json_attempt(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith("{") or t.startswith("```")


def _llm_dispatch(prompt: str, max_tokens: int = 400, model_hint: str = None) -> str:
    """Dispatches prompt across Gemini -> Groq -> OpenAI in priority order."""
    # 1. Google Gemini (Fastest & Highest Free Quota)
    if os.getenv("GEMINI_API_KEY"):
        res = _call_gemini(prompt, max_tokens)
        # Parity with the Groq path below: if the caller asked for JSON (the
        # response looks like an attempt at it), don't accept it unless it
        # actually parses — otherwise a truncated/garbage Gemini reply would
        # be treated as final instead of falling through to Groq/OpenAI.
        if res and (not _looks_like_json_attempt(res) or _parse_json(res)):
            return res

    # 2. Groq Cloud
    if os.getenv("GROQ_API_KEY"):
        res = _call_groq(prompt, max_tokens, model_hint)
        if res: return res

    # 3. OpenAI
    if os.getenv("OPENAI_API_KEY"):
        res = _call_openai(prompt, max_tokens)
        if res: return res

    return ""

_groq = _llm_dispatch


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
    return {}


# ── SK-VDD-001 Prompt Builders ────────────────────────────────────────────────

_RISK_FACTOR_LIST_INSTRUCTION = (
    "List 5 to 8 DISTINCT risk factors as separate items, the way a due-diligence analyst "
    "would write a point-by-point risk list for a reader who asked 'what are the risks?' — "
    "not a narrative paragraph. Each item must be a complete, standalone, specific statement "
    "(name the actual metric, event, or fact — never a vague placeholder like 'standard risk "
    "posture'). Cover a mix of severities; only include Low-severity items if you genuinely have "
    "nothing more material to report after covering everything real."
)

# Confirmed live: with the score requested BEFORE the itemized findings in
# the JSON schema, the model commits to a number before it has "written out"
# the reasoning that would justify one - reproduced a compliance run that
# returned score=80 while every single signal it listed was Low severity
# and non-material, from otherwise-identical evidence that correctly scored
# 0-15 on other attempts. Reordering the schema so the itemized list comes
# FIRST, plus this explicit instruction, took repeated runs on the same
# ambiguous evidence from inconsistent (0, 15, 80, 15) to consistent (0, 0,
# 10, 10) in direct live testing.
_SCORE_CONSISTENCY_INSTRUCTION = (
    "The score below MUST be mathematically consistent with the severities in the list you "
    "just wrote, not a separately-guessed number: if every item above is Low severity, the "
    "score must be low (0-24); one Critical item alone justifies a high score even if "
    "everything else is Low. Never pair a high score with an all-Low findings list, or a low "
    "score with a Critical finding. Uncertainty or missing information is not itself a risk "
    "finding - do not inflate the score for what you don't know, only for what the list above "
    "actually says was found."
)


def _financial_prompt(vendor, industry, country, evidence, urls, metrics, concerns):
    m_block = ""
    if metrics:
        rows = [f"  {k}: {v}" for k, v in metrics.items() if v not in (None, "", "N/A", "Not Available")]
        if rows:
            m_block = "VERIFIED FINANCIAL DATA:\n" + "\n".join(rows) + "\n\n"

    ev = (evidence or "Standard public financial search.")[:800]
    return f"""Senior Financial Risk Auditor (SK-VDD-001 Section 6.1).
Assess financial solvency, liquidity, debt load, and bankruptcy risk for {vendor} ({industry}, {country}).
User Concerns: {concerns or 'None'}

{m_block}EVIDENCE:
{ev}

{_RISK_FACTOR_LIST_INSTRUCTION} Cover solvency, liquidity, profitability, leverage, and audit/going-concern
signals as distinct items wherever evidence or verified financial data supports them.

Return ONLY valid JSON, with "signals" written BEFORE "score" so the score reflects what you just found:
{{
  "signals": [{{"category": "<Solvency|Liquidity|Profitability|Leverage|Audit|Growth>", "indicator": "<one complete, specific risk factor statement>", "severity": "<Low|Elevated|High|Critical>"}}],
  "score": <0-100 FINANCIAL RISK score, not a health/strength score: 0 means no financial risk found, 100 means severe/critical financial risk. A LOW score is GOOD (financially strong); a HIGH score is BAD (financially weak). {_SCORE_CONSISTENCY_INSTRUCTION}>,
  "summary": "<2-3 sentences assessing balance sheet, leverage, and going-concern status>",
  "going_concern_flag": <true|false>,
  "evidence_urls": {json.dumps(urls[:3])}
}}"""


def _reputational_prompt(vendor, industry, country, evidence, urls, concerns):
    ev = (evidence or "Standard adverse media scan.")[:800]
    return f"""Adverse Media Risk Analyst (SK-VDD-001 Section 6.2).
Assess controversies, lawsuits, class actions, and reputational risk for {vendor} ({industry}, {country}).
User Concerns: {concerns or 'None'}

EVIDENCE:
{ev}

{_RISK_FACTOR_LIST_INSTRUCTION} Each item is one distinct adverse-media/litigation/controversy
finding, not a summary of several combined.

Return ONLY valid JSON, with "articles" written BEFORE "score" so the score reflects what you just found:
{{
  "articles": [{{"headline": "<one specific issue, naming what actually happened>", "source": "<source>", "date": "<the actual date/month/year from the evidence if it states one, otherwise 'Date unknown' - never guess or default to 'Recent'>", "severity": "<Low|Elevated|High|Critical>", "url": ""}}],
  "score": <0-100 REPUTATIONAL RISK score, not a reputation-health score: 0 means no adverse media/controversy found, 100 means severe/critical reputational risk. A LOW score is GOOD (clean reputation); a HIGH score is BAD (damaged reputation). {_SCORE_CONSISTENCY_INSTRUCTION}>,
  "summary": "<2-3 sentences assessing controversies and litigation history>",
  "evidence_urls": {json.dumps(urls[:3])}
}}"""


def _key_person_prompt(vendor, industry, country, evidence, urls, exec_profile, concerns):
    p_block = ""
    if exec_profile:
        p_block = f"LEADERSHIP: CEO: {exec_profile.get('ceo', 'N/A')} | Founder: {exec_profile.get('founder', 'N/A')}\n\n"

    ev = (evidence or "Standard executive screening.")[:800]
    return f"""Key-Person & Governance Analyst (SK-VDD-001 Section 6.3).
Assess executive stability, sanctions, and governance for {vendor} ({industry}, {country}).
User Concerns: {concerns or 'None'}

{p_block}EVIDENCE:
{ev}

List every key person you have evidence for (executives, founders, directors), each with their own
specific, standalone flags — not a generic "Clean" for everyone unless genuinely nothing else applies.
List each distinct person exactly once - never repeat the same name as a separate entry.

Return ONLY valid JSON, with "persons" written BEFORE "score" so the score reflects what you just found:
{{
  "persons": [{{"name": "<executive name>", "role": "<title>", "tenure": "<tenure>", "flags": ["<specific finding, e.g. 'No OFAC/OSFI sanctions match found' or the actual concern>"], "severity": "<Low|Elevated|High|Critical>"}}],
  "score": <0-100 KEY-PERSON RISK score, not a leadership-strength score: 0 means no sanctions/governance/key-person risk found, 100 means severe/critical key-person risk. A LOW score is GOOD (stable, clean leadership); a HIGH score is BAD (sanctions hit or governance concern). {_SCORE_CONSISTENCY_INSTRUCTION}>,
  "sanctions_match_flag": <true ONLY if one of the persons above has a genuine, specific sanctions/PEP/disqualification hit named in their own flags - false in every other case, including when every person above is clean. This is a Section 10.1 automatic-escalation trigger, so a false positive here is a serious, unwarranted claim.>,
  "concentration_risk": "<Low|Elevated|High>",
  "summary": "<2-3 sentences on leadership bench strength and sanctions checks>",
  "evidence_urls": {json.dumps(urls[:3])}
}}"""


def _cyber_prompt(vendor, industry, country, domain, evidence, urls, concerns):
    ev = (evidence or "Standard cyber scan.")[:800]
    return f"""Cybersecurity Auditor (SK-VDD-001 Section 6.4).
Assess data breaches, CVEs, ransomware, and attack surface for {vendor} (Domain: {domain or 'N/A'}, {industry}, {country}).
User Concerns: {concerns or 'None'}

EVIDENCE:
{ev}

{_RISK_FACTOR_LIST_INSTRUCTION} Cover breach history, CVE/advisory exposure, ransomware, and general
posture as distinct items - but ONLY where the evidence actually supports it. If you have no specific,
dated, named incident for a category (e.g. no named breach, no dated ransomware event, no specific
advisory), write that plainly - "No specific evidence of a [category] found in available sources" with
severity set to the word "Low" (the field is always one of Low/Elevated/High/Critical, never true/false)
- instead of asserting a generic unsubstantiated claim like "{vendor} has experienced a data breach in
the past" or "{vendor} has been affected by ransomware attacks". A claim with no source and no date is
not a finding.

Return ONLY valid JSON, with "signals" written BEFORE "score" so the score reflects what you just found:
{{
  "signals": [{{"category": "<Data Breach|CVE Exposure|Government Advisory|Ransomware|Cyber Hygiene>", "indicator": "<one complete, specific risk factor statement - name the actual incident/date if asserting one occurred>", "severity": "<Low|Elevated|High|Critical>", "sources": ["<specific source URL for this item if you have one, otherwise an empty array>"]}}],
  "score": <0-100 CYBER RISK score, not a security-posture score: 0 means no breach/CVE/advisory exposure found, 100 means severe/critical cyber risk. A LOW score is GOOD (clean cyber posture); a HIGH score is BAD (breach or critical exposure). {_SCORE_CONSISTENCY_INSTRUCTION}>,
  "recent_breach_flag": <true ONLY if the signals above include a specific, dated, named data breach event backed by a real source - false in every other case, including a generic/unverified "has experienced a breach" claim with no source. This is a Section 10.1 automatic-escalation trigger, so a false positive here is a serious, unwarranted claim.>,
  "summary": "<2-3 sentences on breach history and cyber defense posture>",
  "evidence_urls": {json.dumps(urls[:3])}
}}"""


def _compliance_prompt(vendor, industry, country, evidence, urls, concerns):
    ev = (evidence or "Standard regulatory check.")[:800]
    return f"""Regulatory Compliance Officer (SK-VDD-001 Section 6.5).
Assess regulatory penalties, orders, and compliance track record for {vendor} ({industry}, {country}).
User Concerns: {concerns or 'None'}

EVIDENCE:
{ev}

{_RISK_FACTOR_LIST_INSTRUCTION} Check each of these SIX regulators separately, using this exact spelling
for each - never abbreviate, substitute, or invent a different name (OPC is the Office of the Privacy
Commissioner - do not confuse it with OPP, the Ontario Provincial Police, an unrelated police force):
OSFI, FINTRAC, CSA, OPC, CRTC, Competition Bureau. Exactly one item per regulator, never more than one
- if you have nothing to say about a regulator beyond "no findings," that is still exactly one Low-severity
item for it, not zero and not a duplicate. CSA already covers its provincial member regulators (OSC,
BCSC, AMF, etc.) - never add a separate item for one of those, fold anything about them into the single
CSA item instead. Do not add a seventh regulator beyond this exact list of six.

Return ONLY valid JSON, with "signals" written BEFORE "score" so the score reflects what you just found:
{{
  "signals": [{{"authority": "<one of: OSFI|FINTRAC|CSA|OPC|CRTC|Competition Bureau - exactly one entry per regulator>", "action": "<one complete, specific finding for this regulator>", "material": <true if penalty exceeds CAD 100,000 else false>, "severity": "<Low|Elevated|High|Critical>", "sources": ["<specific source URL genuinely about this regulator's action for this vendor, otherwise an empty array - never reuse an unrelated URL, e.g. an app store or marketplace page, just to fill this field>"]}}],
  "score": <0-100 COMPLIANCE RISK score, not a compliance-health score: 0 means no regulatory penalties/orders found, 100 means severe/critical compliance risk. A LOW score is GOOD (clean regulatory record); a HIGH score is BAD (active penalties or orders). {_SCORE_CONSISTENCY_INSTRUCTION}>,
  "prohibition_order_flag": <true ONLY if one of the signals above is a genuine, currently-active prohibition/cease-and-desist order - false in every other case, including "zero findings" and ordinary penalties/fines that don't bar the entity from operating. This is a Section 10.1 automatic-escalation trigger, so a false positive here is a serious, unwarranted claim.>,
  "summary": "<2-3 sentences on regulatory enforcement history>",
  "evidence_urls": {json.dumps(urls[:3])}
}}"""


def _profile_prompt(vendor, industry, country, all_text):
    return f"""Corporate Registry Researcher. Extract factual corporate details for: {vendor} ({industry}, {country})
CONTEXT: {(all_text or '')[:1800]}

Return ONLY valid JSON:
{{
  "ceo": "<Current CEO name>",
  "founder": "<Founder name(s)>",
  "founded": "<4-digit founding year>",
  "headquarters": "<City, Country>",
  "employees": "<Estimated headcount>",
  "description": "<1-2 sentence overview>"
}}"""


def _risk_tier_label(score) -> str:
    """Same 4-band thresholds as services.py's get_risk_tier (duplicated
    here, not imported, since services.py imports ai_engine and importing
    back would be circular). Used to hand the synthesis LLM an already-
    computed verdict per dimension instead of a bare number it has to
    interpret the direction of itself - confirmed live that prose guidance
    alone ("low score = good") isn't a hard guarantee the model follows
    every time; a pre-labeled tier removes that interpretive step entirely."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "Unknown"
    if s <= 24:
        return "LOW RISK"
    if s <= 49:
        return "MEDIUM RISK"
    if s <= 74:
        return "HIGH RISK"
    return "CRITICAL RISK"


def _synthesis_prompt(vendor, industry, country, cat_results, concerns, total_hits):
    lines = [
        f"- {cat.upper()} (Risk Score: {r.get('score', 25)}/100 = {_risk_tier_label(r.get('score', 25))}): {r.get('summary', '')[:90]}"
        for cat, r in cat_results.items()
    ]
    assessments_block = "\n".join(lines)
    return f"""Executive Risk Committee. Synthesize due diligence for {vendor} ({industry}, {country}) per SK-VDD-001.

IMPORTANT - score direction: every score below is a RISK score, not a health/strength score.
0 = no risk found (GOOD). 100 = severe/critical risk (BAD). A LOW score is the desirable outcome in
every dimension. Do not describe a high score as "strength" or "stability", and do not describe a
low score as a "deficiency" or "concern" - get the polarity right in analyst_notes.

ASSESSMENTS:
{assessments_block}
CONCERNS: {concerns or 'Standard Vendor Due Diligence'}

Return ONLY valid JSON:
{{
  "analyst_notes": "<3-4 sentence comprehensive assessment paragraph>",
  "data_gaps": ["<gap 1>", "<gap 2>"],
  "recommendations": ["<actionable mitigation 1>", "<actionable mitigation 2>", "<actionable mitigation 3>"]
}}"""


# ── Autonomous SK-VDD-001 Deterministic Rule Engine (Zero-Key Fallback) ───────

def _autonomous_fallback_engine(vendor, industry, country, concerns, financial_metrics, prof_extras, hits_count):
    """No-evidence fallback: never invent a finding, screening result, or score."""
    result = {}
    for category, key in (("financial", "signals"), ("reputation", "articles"),
                          ("key_person", "persons"), ("cyber", "signals"), ("compliance", "signals")):
        result[category] = {"score": None, key: [], "evidence_urls": [],
                            "summary": "Insufficient verified evidence; assessment incomplete.",
                            "going_concern_flag": False, "sanctions_match_flag": False,
                            "recent_breach_flag": False, "prohibition_order_flag": False}
    result["synth"] = {"analyst_notes": "", "data_gaps": ["Evidence unavailable; screening not verified."],
                       "recommendations": ["Restore required sources and obtain analyst review."]}
    return result


_SEVERITY_SCORE_CEILING = {"low": 24, "elevated": 49, "high": 74, "critical": 100}


def _normalize_severities(cat: str, parsed: dict) -> dict:
    array_key = {
        "financial": "signals", "cyber": "signals", "compliance": "signals",
        "reputation": "articles", "key_person": "persons",
    }.get(cat)
    if not array_key or not isinstance(parsed.get(array_key), list):
        return parsed
    for item in parsed[array_key]:
        if not isinstance(item, dict):
            continue
        if str(item.get("severity", "")).strip().lower() not in _SEVERITY_SCORE_CEILING:
            item["severity"] = "Low"
    return parsed


def _clamp_score_to_evidence(cat: str, parsed: dict) -> dict:
    array_key = {
        "financial": "signals", "cyber": "signals", "compliance": "signals",
        "reputation": "articles", "key_person": "persons",
    }.get(cat)
    if not array_key or not isinstance(parsed.get(array_key), list):
        return parsed
    severities = [
        str(item.get("severity", "")).strip().lower()
        for item in parsed[array_key] if isinstance(item, dict)
    ]
    severities = [s for s in severities if s in _SEVERITY_SCORE_CEILING]
    if not severities:
        return parsed
    ceiling = max(_SEVERITY_SCORE_CEILING[s] for s in severities)
    try:
        score = float(parsed.get("score", 0))
    except (TypeError, ValueError):
        return parsed
    if score > ceiling:
        parsed["score"] = ceiling
    return parsed


# Confirmed live on two unrelated vendors (BlackBerry, Shopify): even with the
# prompt instructed not to, the model can still set recent_breach_flag=true off
# a generic, undated, unsourced "X has experienced a data breach in the past"
# item - which then drives a client-facing "Confirmed Data Breach within the
# Past 12 Months" Section 10.1 escalation banner with nothing behind it. Same
# class of bug as prohibition_order_flag, same fix shape: a deterministic
# backstop that only ever turns the flag OFF, never on, so a residual LLM
# misfire can't manufacture a false escalation.
def _validate_breach_flag(parsed: dict) -> dict:
    if not parsed.get("recent_breach_flag"):
        return parsed
    signals = parsed.get("signals", [])
    if not isinstance(signals, list):
        signals = []
    from evidence import within_months, http_url
    has_sourced_breach = any(
        isinstance(s, dict)
        and str(s.get("category", "")).strip().lower() == "data breach"
        and str(s.get("severity", "")).strip().lower() in ("high", "critical")
        and s.get("verification_status") == "source_linked"
        and any(http_url(u) for u in s.get("sources", []))
        and within_months(s.get("event_date"), 12)
        for s in signals
    )
    if not has_sourced_breach:
        parsed["recent_breach_flag"] = False
    return parsed


# Confirmed live (BlackBerry run): sanctions_match_flag came back true while
# every person in the persons list the model had just written showed a clean
# severity ("Low") and no sanctions-related flag - the exact same failure
# mode as recent_breach_flag above and prohibition_order_flag in compliance,
# just on key-person's own escalation trigger. Same fix shape: only allow
# the flag to stand if a person in that same list is actually flagged
# High/Critical, which is the same structured severity signal already used
# throughout this file (_SEVERITY_SCORE_CEILING) rather than fragile
# free-text matching on each person's "flags" wording.
def _validate_sanctions_flag(parsed: dict) -> dict:
    if not parsed.get("sanctions_match_flag"):
        return parsed
    persons = parsed.get("persons", [])
    if not isinstance(persons, list):
        persons = []
    has_flagged_person = any(
        isinstance(p, dict) and p.get("sanctions_identity_confirmed") is True
        and p.get("sanctions_record_id") and p.get("sources")
        for p in persons
    )
    if not has_flagged_person:
        parsed["sanctions_match_flag"] = False
    return parsed


# Confirmed live (BlackBerry run): despite the prompt explicitly listing the
# six canonical authorities, the model added a seventh, off-list entry -
# "Ontario Securities Commission" - as its own row, even though the prompt's
# "CSA" item is already defined to cover CSA's provincial members (OSC,
# BCSC, AMF). Rather than trying to enumerate every alias the model might
# invent, this normalizes the ones the prompt's own text already names as
# CSA members so they collapse into the single canonical CSA row via
# _dedupe_compliance_signals below, instead of appearing as an extra,
# redundant line the sample report's one-row-per-regulator format doesn't
# have room for.
_CSA_MEMBER_ALIASES = {
    "osc", "ontario securities commission",
    "bcsc", "british columbia securities commission",
    "amf", "autorité des marchés financiers", "autorite des marches financieres",
}


def _normalize_compliance_authorities(parsed: dict) -> dict:
    signals = parsed.get("signals")
    if not isinstance(signals, list):
        return parsed
    for s in signals:
        if not isinstance(s, dict):
            continue
        if str(s.get("authority", "")).strip().lower() in _CSA_MEMBER_ALIASES:
            s["authority"] = "CSA"
    return parsed


# Confirmed live (BlackBerry run): despite the prompt asking for "exactly one
# item per regulator," the model returned "OSFI" four times and dropped three
# of the six named regulators entirely - not aligned with the sample report's
# one-row-per-regulator breakdown. This dedupes deterministically rather than
# relying on the prompt alone: keeps the first entry per authority (normalized
# case/whitespace), preferring one with a non-empty severity/source over a
# near-duplicate that has neither.
def _dedupe_compliance_signals(parsed: dict) -> dict:
    signals = parsed.get("signals")
    if not isinstance(signals, list):
        return parsed
    seen = {}
    order = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        key = str(s.get("authority", "")).strip().lower()
        if not key:
            order.append(s)
            continue
        if key not in seen:
            seen[key] = s
            order.append(s)
        else:
            existing = seen[key]
            if not existing.get("sources") and s.get("sources"):
                idx = order.index(existing)
                order[idx] = s
                seen[key] = s
    parsed["signals"] = order
    return parsed


# Confirmed live (BlackBerry run): two cyber signals came back with the
# identical category and indicator text ("[Cybersecurity Posture] BlackBerry
# has a strong cybersecurity posture") back to back - same duplication
# failure mode as compliance/key-person above, just on cyber's "signals"
# array, which has no natural identity field like "authority" or "name" to
# key on. Dedupes by normalized indicator text instead; real CVE items are
# unaffected since each one's indicator text includes a unique CVE ID.
def _dedupe_cyber_signals(parsed: dict) -> dict:
    signals = parsed.get("signals")
    if not isinstance(signals, list):
        return parsed
    seen = set()
    order = []
    for s in signals:
        if not isinstance(s, dict):
            order.append(s)
            continue
        key = str(s.get("indicator", "")).strip().lower()
        if not key or key not in seen:
            if key:
                seen.add(key)
            order.append(s)
    parsed["signals"] = order
    return parsed


# Confirmed live (BlackBerry run): the model returned John Chen and Richard
# Stiennon as two persons, then repeated the identical two entries again
# immediately after - same duplication failure mode as the compliance
# authority bug above, just on the "persons" array instead of "signals".
# Dedupes by normalized name, preferring an entry with more sources/flags
# over a near-duplicate that has fewer.
def _dedupe_key_person_signals(parsed: dict) -> dict:
    persons = parsed.get("persons")
    if not isinstance(persons, list):
        return parsed
    seen = {}
    order = []
    for p in persons:
        if not isinstance(p, dict):
            continue
        key = str(p.get("name", "")).strip().lower()
        if not key:
            order.append(p)
            continue
        if key not in seen:
            seen[key] = p
            order.append(p)
        else:
            existing = seen[key]
            existing_richness = len(existing.get("sources") or []) + len(existing.get("flags") or [])
            candidate_richness = len(p.get("sources") or []) + len(p.get("flags") or [])
            if candidate_richness > existing_richness:
                idx = order.index(existing)
                order[idx] = p
                seen[key] = p
    parsed["persons"] = order
    return parsed


# Confirmed live (BlackBerry run): _reputational_prompt hard-truncates the
# evidence it hands the model to 800 chars, so a URL sitting near that
# cutoff can come out chopped mid-path (observed:
# "https://financialpost.com/news/judge-"), and the model faithfully echoes
# the truncated string as if it were the complete source link - a broken
# citation a client would hit as a 404. Repairs this deterministically only
# for URLs bearing the truncation signature (ending in "-" or "_", which a
# legitimate URL essentially never does): if it's an unambiguous prefix of
# one of the full, untruncated URLs already known for this vendor/dimension,
# replaces it with the complete URL; otherwise clears it to an empty string
# rather than serve a link that won't resolve. Never touches a URL that
# doesn't show that signature, so an otherwise-unfamiliar but well-formed
# URL is left alone rather than second-guessed.
def _repair_truncated_urls(parsed: dict, known_urls) -> dict:
    articles = parsed.get("articles")
    if not isinstance(articles, list):
        return parsed
    for a in articles:
        if not isinstance(a, dict):
            continue
        url = str(a.get("url", "")).strip()
        if not url or url[-1] not in "-_":
            continue
        matches = [u for u in (known_urls or []) if u.startswith(url)]
        a["url"] = matches[0] if len(matches) == 1 else ""
    return parsed


_ATTRITION_KEYWORDS = ["resigned", "departed", "stepped down", "left the company", "fired", "terminated"]


# The prior version of this check counted DISTINCT ATTRITION KEYWORDS present
# anywhere in the raw scraped evidence blob, with no link to a specific
# person and no time-scoping despite the escalation message claiming
# "12-month lookback" - one person described two ways ("resigned ... he
# later said he'd stepped down") would false-positive a "2+ C-suite exits"
# escalation, and a departure from years ago counted identically to one from
# last month. This version requires each hit to be in the SAME SENTENCE as
# a specific named person already extracted into the persons list (a fixed
# character window was tried first but bled adjacent people's sentences into
# each other in short evidence text - "Jane Smith resigned. Bob Jones
# continues to lead the team." falsely attributed "resigned" to Bob too) and
# (b), if any year is present in that same sentence, that it not be stale
# relative to the configured lookback - the same "no year found = keep it,
# a stale year found = drop it" philosophy already used for CanLII
# litigation staleness elsewhere in this codebase, so an undated mention
# isn't penalized for something it never claimed.
def _detect_recent_attrition(kp_persons, kp_evidence):
    """Count distinct named departures only when a date in the same sentence is recent."""
    from evidence import within_months
    if not kp_evidence:
        return 0, []
    sentences = re.split(r"(?<=[.!?])\s+", kp_evidence.lower())
    attrited = []
    date_pattern = r"\b(?:\d{4}-\d{2}-\d{2}|\d+ (?:days?|weeks?|months?|years?) ago)\b"
    for person in kp_persons:
        name = str(person.get('name', '')).strip()
        if len(name) < 3 or name.casefold() in {n.casefold() for n in attrited}:
            continue
        for sentence in sentences:
            if name.lower() not in sentence or not any(kw in sentence for kw in _ATTRITION_KEYWORDS):
                continue
            dates = re.findall(date_pattern, sentence)
            if any(within_months(date, 12) for date in dates):
                attrited.append(name)
                break
    return len(attrited), attrited


# ── Public Entry Point ────────────────────────────────────────────────────────

def analyze_vendor_full(vendor, data, country="Canada", industry="", concerns="", financial_metrics=None):
    from analysis_pipeline import analyze
    return analyze(vendor, data, country, industry, concerns, financial_metrics)
