"""Due-diligence orchestration with explicit evidence gates and provisional scoring.

CFG-VDD-001 approval and analyst review are required before a vendor decision.
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
from registry_lookup import search_all_registries
from canlii_search import search_litigation
from sedarplus_lookup import search_filings
import config
import licensed_sources

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
    """
    Maps score to SK-VDD-001 4-tier rating band. The High/Critical boundaries
    are configurable per Section 11 (high_score_threshold, critical_score_threshold);
    the Low/Medium boundary (25) is fixed by the spec's own band table (Section 7.3).
    """
    s = int(round(score))
    if s <= 24:
        return "Low", RATING_BANDS["Low"]
    elif s < config.HIGH_SCORE_THRESHOLD:
        return "Medium", RATING_BANDS["Medium"]
    elif s < config.CRITICAL_SCORE_THRESHOLD:
        return "High", RATING_BANDS["High"]
    else:
        return "Critical", RATING_BANDS["Critical"]


def compute_confidence_score(
    total_hits: int,
    has_metrics: bool,
    federal_found: bool,
    provincial_found: bool,
    has_profile: bool,
    search_available: bool,
    licensed_gap_count: int,
) -> int:
    """
    SK-VDD-001 Section 11 data-confidence score.

    Confirmed live: without the two deductions below, this number was a
    near-constant 98 for any public-company run regardless of whether
    individual lookups actually succeeded this run (a failed provincial
    registry or corporate-profile lookup didn't move it at all) or how many
    licensed sources are missing - Section 9.2 explicitly requires "the
    corresponding dimension score confidence will be reduced" when
    BitSight/World-Check/Refinitiv/Factiva aren't licensed, and nothing
    previously implemented that.

    Deliberately does NOT take canlii_litigation/sedarplus_filings/
    serper-hit-count style "found nothing" signals as inputs - those are
    often good news (a clean litigation record), not lookup failures, and
    penalizing them would create a perverse "cleaner vendor -> lower
    confidence" incentive. yfinance/has_metrics is only used once, in the
    base tier below, not counted again as a failure signal.
    """
    confidence = (
        40 if total_hits == 0 and not has_metrics else
        65 if total_hits < 5 else
        85 if total_hits < 15 else 95
    )
    if has_metrics:
        confidence = min(confidence + 5, 98)

    run_failures = sum([not federal_found, not provincial_found, not has_profile, not search_available])
    confidence -= min(5 * run_failures, 20)

    confidence -= min(licensed_gap_count, 7)

    return max(confidence, 30)


def get_vendor_analysis(vendor: str, industry: str = "", country: str = "Canada", concerns: str = "",
                        company_url: str = "", business_number: str = "", ticker: str = "",
                        duns_number: str = "", naics_code: str = "", province: str = "", progress=None) -> tuple:
    """Collect evidence and return an explicitly incomplete or reviewable assessment."""
    from evidence import now_utc
    from uuid import uuid4
    def stage(name):
        if progress:
            progress(name)
    norm = normalize_vendor_name(vendor)
    clean_vendor = norm['normalized_name']
    stage('collecting_sources')
    with ThreadPoolExecutor(max_workers=5) as ex:
        searches = ex.submit(collect_vendor_signals, vendor=clean_vendor, industry=industry, country=country,
                             company_url=company_url, business_number=business_number, naics_code=naics_code,
                             duns_number=duns_number)
        finance = ex.submit(fetch_financial_and_profile, clean_vendor, country, ticker=ticker, company_url=company_url)
        registry = ex.submit(search_all_registries, clean_vendor, business_number, company_url, country, province)
        litigation = ex.submit(search_litigation, clean_vendor)
        filings = ex.submit(search_filings, clean_vendor, ticker)
        data = searches.result()
        metrics, profile, profile_sources = finance.result()
        registries, lit, fil = registry.result(), litigation.result(), filings.result()
    stage('extracting_evidence')
    result = analyze_vendor_full(clean_vendor, data, country, industry, concerns, metrics)
    result.update(run_id=uuid4().hex, schema_version='2.0', vendor_name=vendor,
                  normalized_vendor_name=clean_vendor, registration_country=country,
                  business_number=business_number, duns_number=duns_number, naics_code=naics_code,
                  province=province, query_date=now_utc().isoformat(), lookback_months=config.LOOKBACK_MONTHS,
                  review_status='pending', analyst_notes='')
    result['company_profile'].update({k: v for k, v in profile.items()
                                      if profile_sources.get(k) not in (None, 'llm_estimate')})
    result['company_profile']['field_sources'] = {k: v for k, v in profile_sources.items() if v != 'llm_estimate'}
    for key in ('ceo', 'founder', 'founded', 'headquarters', 'employees'):
        result['company_profile'].setdefault(key, 'Not verified')
    fed, prov = registries.get('federal_registry', {}), registries.get('provincial_registry', {})
    ledger = result.setdefault('source_ledger', [])
    for name, response in [('Corporations Canada', fed), ('Provincial Registry', prov), ('SEDAR+', fil), ('CanLII', lit)]:
        ledger.append({'source': name, 'status': response.get('query_status', 'unknown'),
                       'retrieved_at': response.get('retrieved_at'), 'method': response.get('method', 'search_index'),
                       'url': response.get('url', '')})
    identities = [r for r in (fed, prov) if r.get('identity_verified')]
    identity_ids = {r.get('business_number') or r.get('corporation_number') or r.get('url') for r in identities}
    ambiguous = any(r.get('ambiguous') for r in (fed, prov)) or (len(identity_ids) > 1 and not (business_number and all(r.get('business_number') == business_number for r in identities)))
    result['entity_candidates'] = [c for r in (fed, prov) for c in r.get('candidates', [])]
    result['jurisdiction_confirmed'] = bool(identities) and not ambiguous
    result['disambiguation_flag'] = ambiguous
    canada = country.strip().lower() in ('canada', 'ca')
    result['jurisdiction_gate'] = ('out_of_scope_non_canada' if not canada else
                                  'confirmed_canadian' if result['jurisdiction_confirmed'] else 'unconfirmed_canadian_registration')
    search_ok = all(data.get(c, {}).get('query_status') in ('success', 'no_matches') for c in RISK_CATEGORIES)
    critical_missing = fil.get('query_status') not in ('success', 'no_matches', 'not_applicable') or not search_ok
    if not canada:
        status = 'out_of_scope'
    elif critical_missing:
        status = 'paused_source_unavailable'
    elif not result['jurisdiction_confirmed']:
        status = 'awaiting_entity_confirmation'
    elif any(result['risk_scores'].get(c) is None for c in RISK_CATEGORIES):
        status = 'insufficient_evidence'
    else:
        status = 'awaiting_review'
    result['run_status'] = status
    from review_api import PARAMETERS
    result['policy_parameters'] = {key: getattr(config, key) for key in PARAMETERS}
    result['dimension_ratings'] = {category: get_risk_tier(score)[0] if score is not None else 'Not assessed'
                                   for category, score in result['risk_scores'].items()}
    result['completion_blockers'] = []
    if critical_missing:
        result['completion_blockers'].append('Required search or SEDAR+ access was not verified; restore sources and rerun.')
    if not result['jurisdiction_confirmed']:
        result['completion_blockers'].append('Confirm the legal entity against an authoritative Canadian registry record.')
    if any(result['risk_scores'].get(c) is None for c in RISK_CATEGORIES):
        result['completion_blockers'].append('One or more dimensions lack dated, source-linked evidence; no final rating can be issued.')
    result['completion_blockers'].append('Provisional scoring policy requires Risk & Control approval (CFG-VDD-001).')
    result['overall_score'] = (round(sum(result['risk_scores'][c] * WEIGHTS[c] for c in RISK_CATEGORIES))
                               if status == 'awaiting_review' else None)
    result['overall_risk_rating'] = get_risk_tier(result['overall_score'])[0] if result['overall_score'] is not None else 'Not assessed'
    result['traffic_light'] = 'Unrated' if result['overall_score'] is None else RATING_BANDS[result['overall_risk_rating']]['traffic_light']
    result['recommended_action'] = ('Review provisional findings and scoring before making a vendor decision.' if status == 'awaiting_review'
                                    else 'Assessment incomplete. Resolve the listed evidence gaps and obtain analyst review.')
    if result['overall_score'] is not None and result['overall_score'] >= config.CRITICAL_SCORE_THRESHOLD:
        result['automatic_escalations'].append('Provisional score meets the senior review threshold; analyst validation required.')
    result['review_flags'].extend(result['completion_blockers'])
    result['source_health'] = {x['source']: x['status'] for x in ledger}
    result['data_sources_used'] = sorted({x['source'] for x in ledger if x['status'] in ('success', 'no_matches')})
    result['data_gaps'].extend(f"{x['source']}: {x['status']}" for x in ledger if x['status'] not in ('success', 'no_matches', 'not_applicable'))
    result['confidence_score'] = None
    result['evidence_coverage'] = {'successful_checks': sum(x['status'] in ('success', 'no_matches') for x in ledger),
                                 'total_checks': len(ledger), 'meaning': 'Source availability, not probability of accuracy.'}
    result['financial_history_status'] = 'audited_statements_not_verified'
    result['private_co_confidence_flag'] = 'Unknown'  # Failed quote lookup is not proof of private ownership.
    for c, prefix, key in [('financial','fin_risk','signals'), ('reputation','rep_risk','articles'),
                           ('key_person','kp_risk','persons'), ('cyber','tech_cyber','signals'), ('compliance','compliance','signals')]:
        result[prefix+'_score'] = result['risk_scores'].get(c)
        alias = 'kp_persons' if c == 'key_person' else prefix+'_'+key
        result[alias] = result['explanations'][c].get(key, [])
    stage('awaiting_review' if status == 'awaiting_review' else status)
    return result, data
