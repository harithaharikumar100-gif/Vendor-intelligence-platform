"""
frameworks.py - Named Regulatory Framework Alignment (Provided-Framework Model)
--------------------------------------------------------------------------------
Per direction from the platform's product owner: the compliance/governance
dimensions should be scoped to a specific, supplied set of named regulatory
frameworks rather than open-ended, unbounded "regulation in general" reasoning.

This starts with the two frameworks explicitly named as the priority set:
  - OSFI Corporate Governance Guideline   -> Key-Person & Governance dimension
  - OSFI Guideline E-13 (Regulatory Compliance Management) -> Compliance dimension

Each framework is broken into named, citable sub-principles (paraphrased from
the guideline's publicly stated expectations, not reproduced verbatim). Every
principle is checked deterministically against the evidence corpus already
gathered for that vendor (scraped text, LLM summaries/signals) using keyword
matching -- consistent with the rest of this codebase's "no fabrication"
convention: if there is no evidence either way, the principle is reported as
"not disclosed in available sources", never assumed to pass or fail.

Additional named frameworks (from the same supplied list) can be added the
same way later -- each is just a dict of principles with keywords.
"""

FRAMEWORKS = {
    "osfi_corporate_governance": {
        "id": "osfi_corporate_governance",
        "name": "OSFI Corporate Governance Guideline",
        "authority": "Office of the Superintendent of Financial Institutions (Canada)",
        "dimension": "key_person",
        "principles": [
            {
                "id": "board_risk_oversight",
                "title": "Board maintains active oversight of risk appetite and major risk categories",
                "polarity": "positive",
                "keywords": ["board of directors", "board oversight", "risk appetite", "board-approved", "board approved"],
            },
            {
                "id": "independent_risk_committee",
                "title": "An independent board-level risk (or audit) committee reviews risk exposures",
                "polarity": "positive",
                "keywords": ["risk committee", "audit committee", "board committee"],
            },
            {
                "id": "ceo_chair_separation",
                "title": "Board leadership (Chair) is independent of CEO/President management role",
                "polarity": "positive",
                "keywords": ["independent chair", "non-executive chair", "separate chair", "lead independent director"],
            },
            {
                "id": "code_of_conduct",
                "title": "A documented code of conduct/ethics governs senior management and staff",
                "polarity": "positive",
                "keywords": ["code of conduct", "code of ethics", "ethics policy"],
            },
            {
                "id": "whistleblower_mechanism",
                "title": "A confidential whistleblower / ethics-reporting mechanism exists",
                "polarity": "positive",
                "keywords": ["whistleblower", "ethics hotline", "anonymous reporting", "speak up policy"],
            },
            {
                "id": "succession_planning",
                "title": "Documented succession planning reduces key-person dependency",
                "polarity": "positive",
                "keywords": ["succession plan", "succession planning"],
            },
            {
                "id": "governance_adverse_finding",
                "title": "No disclosed governance failure (e.g. board/executive misconduct, disqualification)",
                "polarity": "adverse",
                "keywords": ["director disqualification", "removed as director", "governance failure", "boardroom dispute", "resigned amid"],
            },
        ],
    },
    "osfi_e13": {
        "id": "osfi_e13",
        "name": "OSFI Guideline E-13 (Regulatory Compliance Management)",
        "authority": "Office of the Superintendent of Financial Institutions (Canada)",
        "dimension": "compliance",
        "principles": [
            {
                "id": "compliance_function",
                "title": "A designated compliance function / Chief Compliance Officer is identifiable",
                "polarity": "positive",
                "keywords": ["chief compliance officer", "compliance officer", "head of compliance", "compliance function"],
            },
            {
                "id": "obligations_inventory",
                "title": "Regulatory obligations are tracked through a formal compliance framework",
                "polarity": "positive",
                "keywords": ["compliance framework", "regulatory obligations", "compliance program", "compliance management system"],
            },
            {
                "id": "monitoring_testing",
                "title": "Ongoing compliance monitoring or testing activity is disclosed",
                "polarity": "positive",
                "keywords": ["compliance monitoring", "compliance testing", "compliance audit", "internal audit"],
            },
            {
                "id": "board_compliance_reporting",
                "title": "Compliance status is reported to senior management or the board",
                "polarity": "positive",
                "keywords": ["reported to the board", "board reporting", "compliance report", "reported to senior management"],
            },
            {
                "id": "remediation_process",
                "title": "A documented process exists for remediating identified compliance gaps",
                "polarity": "positive",
                "keywords": ["remediation plan", "corrective action plan", "remediation program"],
            },
            {
                "id": "enforcement_history",
                "title": "No unresolved regulatory enforcement action against the entity",
                "polarity": "adverse",
                "keywords": [
                    "consent order", "cease and desist", "cease-and-desist", "enforcement action",
                    "regulatory penalty", "administrative monetary penalty", "fined by osfi",
                    "prohibition order", "regulatory sanction",
                ],
            },
        ],
    },
    "fintrac_guidance": {
        "id": "fintrac_guidance",
        "name": "FINTRAC Guidance (AML/ATF Compliance Program)",
        "authority": "Financial Transactions and Reports Analysis Centre of Canada",
        "dimension": "compliance",
        "principles": [
            {
                "id": "compliance_officer_appointed",
                "title": "A designated AML/ATF compliance officer is identifiable",
                "polarity": "positive",
                "keywords": ["compliance officer", "aml officer", "anti-money laundering officer"],
            },
            {
                "id": "written_compliance_program",
                "title": "Written AML/ATF compliance policies and procedures are disclosed",
                "polarity": "positive",
                "keywords": ["compliance policy", "compliance procedures", "aml program", "aml/atf program"],
            },
            {
                "id": "risk_assessment",
                "title": "A documented business-wide money-laundering/terrorist-financing risk assessment exists",
                "polarity": "positive",
                "keywords": ["risk assessment", "money laundering risk", "terrorist financing risk"],
            },
            {
                "id": "compliance_training",
                "title": "An ongoing AML/ATF compliance training program is disclosed",
                "polarity": "positive",
                "keywords": ["compliance training", "aml training", "staff training program"],
            },
            {
                "id": "effectiveness_review",
                "title": "A periodic independent effectiveness review of the compliance program is disclosed",
                "polarity": "positive",
                "keywords": ["effectiveness review", "compliance audit", "independent review of compliance"],
            },
            {
                "id": "amp_history",
                "title": "No FINTRAC administrative monetary penalty (AMP) on record",
                "polarity": "adverse",
                "keywords": ["fintrac penalty", "administrative monetary penalty", "amp from fintrac", "fintrac fine"],
            },
        ],
    },
    "opc_pipeda_guidelines": {
        "id": "opc_pipeda_guidelines",
        "name": "OPC Guidelines (PIPEDA Privacy Program)",
        "authority": "Office of the Privacy Commissioner of Canada",
        "dimension": "compliance",
        "principles": [
            {
                "id": "accountability",
                "title": "A designated privacy officer or accountable individual for personal information is identifiable",
                "polarity": "positive",
                "keywords": ["privacy officer", "chief privacy officer", "data protection officer"],
            },
            {
                "id": "breach_notification_process",
                "title": "A documented breach notification / incident-response process for personal information is disclosed",
                "polarity": "positive",
                "keywords": ["breach notification", "incident response plan", "privacy breach protocol"],
            },
            {
                "id": "public_privacy_policy",
                "title": "A publicly available privacy policy governing personal information is disclosed",
                "polarity": "positive",
                "keywords": ["privacy policy", "privacy notice"],
            },
            {
                "id": "safeguards",
                "title": "Documented technical/organizational safeguards for personal information are disclosed",
                "polarity": "positive",
                "keywords": ["data safeguards", "security safeguards", "information safeguards"],
            },
            {
                "id": "pipeda_finding_history",
                "title": "No OPC finding of PIPEDA contravention on record",
                "polarity": "adverse",
                "keywords": ["pipeda violation", "opc finding", "privacy commissioner investigation", "found in contravention"],
            },
        ],
    },
}


_NEGATIONS = (
    "no ", "not ", "none ", "zero ", "never ", "n't ", "without ", "lack of ",
    "absence of ", "no material", "no confirmed", "no recorded", "no recent",
    "no public", "no known", "clean -", "clean-",
)


def _sentence_window(text: str, idx: int, back: int = 60) -> str:
    """Text preceding a match, clipped to the start of its own sentence — a
    negation two sentences earlier shouldn't flip this match's meaning."""
    start = max(0, idx - back)
    window = text[start:idx]
    boundary = max(window.rfind("."), window.rfind("\n"), window.rfind("!"), window.rfind("?"))
    if boundary != -1:
        window = window[boundary + 1:]
    return window


def _is_negated(text: str, idx: int) -> bool:
    return any(neg in _sentence_window(text, idx) for neg in _NEGATIONS)


def _find_match(text: str, keywords: list):
    """Returns (keyword, index) for the first keyword found, or (None, -1)."""
    for kw in keywords:
        idx = text.find(kw)
        if idx != -1:
            return kw, idx
    return None, -1


def assess_framework(framework_id: str, corpus_text: str) -> list:
    """Evaluate every principle of one named framework against the evidence corpus."""
    fw = FRAMEWORKS.get(framework_id)
    if not fw:
        return []
    text = (corpus_text or "").lower()
    results = []
    for p in fw["principles"]:
        matched, idx = _find_match(text, p["keywords"])
        if not matched:
            status = "not_disclosed_in_available_sources"
        else:
            negated = _is_negated(text, idx)
            if p["polarity"] == "adverse":
                # e.g. "no enforcement action" confirms the good state, not a concern.
                status = "evidence_found" if negated else "evidence_of_concern"
            else:
                # A negated positive-polarity match ("no whistleblower policy") is a
                # real gap, but keyword matching alone isn't reliable enough to assert
                # that — fall back to the honest "not disclosed" default rather than
                # fabricate a finding either way (Section 9.3 no-speculation convention).
                status = "not_disclosed_in_available_sources" if negated else "evidence_found"
        results.append({
            "principle_id": p["id"],
            "title": p["title"],
            "polarity": p["polarity"],
            "status": status,
            "matched_keyword": matched,
        })
    return results


def assess_all(dimension: str, corpus_text: str) -> list:
    """
    Returns every named framework mapped to this SK-VDD-001 dimension, each with
    its principle-level assessment. Empty list if no framework is mapped to this
    dimension yet (the "provided framework" set grows over time, not on demand).
    """
    out = []
    for fw_id, fw in FRAMEWORKS.items():
        if fw["dimension"] != dimension:
            continue
        out.append({
            "framework_id": fw_id,
            "framework": fw["name"],
            "authority": fw["authority"],
            "principles": assess_framework(fw_id, corpus_text),
        })
    return out
