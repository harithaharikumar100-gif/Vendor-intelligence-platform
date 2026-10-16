"""Regressions from the SK-VDD-001 audit: unknown is never clean evidence."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pandas as pd
import pytest

import analysis_pipeline as pipeline
import config
import evidence
import financial_history
import registry_verification
import scraper
import services


def event(**changes):
    return dict(event_id='e1', severity='High', event_date=evidence.now_utc().date().isoformat(),
                verification_status='source_linked', sources=['https://example.org/notice'], **changes)


@pytest.mark.parametrize('changes', [
    {'event_date': ''}, {'event_date': '2009-01-01'}, {'event_date': 'tomorrow'},
    {'event_date': (evidence.now_utc() + timedelta(days=2)).date().isoformat()},
    {'severity': 'Unknown'}, {'verification_status': 'candidate_match'},
    {'ambiguous_match': True}, {'sources': []}, {'sources': ['javascript:alert(1)']},
])
def test_unusable_evidence_cannot_be_scored(changes):
    finding = event()
    finding.update(changes)
    assert evidence.score_events([finding]) == (None, [])


def test_provisional_contribution_is_inspectable_and_resolution_discounted():
    finding = event(resolution='resolved')
    score, ledger = evidence.score_events([finding], recency_multiplier=2)
    assert score == 35
    assert ledger == [{'event_id': 'e1', 'base': 35, 'recency_multiplier': 2, 'points': 35.0}]


def test_calendar_window_and_relative_date_regressions():
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert evidence.within_months('2025-10-16', 12, now)
    assert not evidence.within_months('2025-10-15', 12, now)
    assert not evidence.within_months('800 days ago', 12, now)
    assert evidence.parse_date('2026') is None
    assert not scraper._is_recent_12m({'date': '800 days ago'})
    assert scraper._stale({'date': '2009-01-01', 'snippet': '', 'title': ''})


def extract(model_event, text=None, category='cyber'):
    date = evidence.now_utc().date().isoformat()
    quote = text or f'Example Corporation disclosed a security incident on {date}.'
    records = [{'id': 'record', 'url': 'https://example.org/notice', 'text': quote}]
    payload = dict(source_id='record', evidence_quote=quote, event_date=date, severity='High')
    payload.update(model_event)
    return pipeline.extract_events('Example Corporation', category, records, 'hack',
                                   lambda *a, **k: json.dumps({'events': [payload]}), json.loads)


@pytest.mark.parametrize('model_event', [
    {'source_id': 'invented'}, {'evidence_quote': 'This invented quotation is absent from the source.'},
])
def test_model_cannot_invent_citations(model_event):
    assert extract(model_event) == ([], 1)


def test_unsupported_incident_date_stays_unscored():
    findings, rejected = extract({}, text='Example Corporation reported an incident without providing its date.')
    assert not rejected
    assert findings[0]['event_date'] == ''
    assert evidence.score_events(findings) == (None, [])


def test_real_quote_preserves_full_url_and_date():
    findings, rejected = extract({})
    assert not rejected
    assert findings[0]['url'] == 'https://example.org/notice'
    assert findings[0]['event_date'] == evidence.now_utc().date().isoformat()
    assert evidence.score_events(findings)[0] == 35


def test_undocumented_person_is_rejected():
    assert extract({'name': 'Invented Person'}, category='key_person') == ([], 1)


@pytest.fixture
def empty_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline.cyber_intel, 'gather_cyber_intelligence', lambda *a: {'signals': [], 'source_health': []})
    monkeypatch.setattr(pipeline.sanctions_check, 'search_sdn', lambda name: [])
    monkeypatch.setattr(pipeline.sanctions_check, 'source_status', lambda: {'source': 'OFAC', 'status': 'failed'})
    return {c: {'records': [], 'query_status': 'success'} for c in pipeline.CATEGORIES}


def test_empty_evidence_and_user_concern_do_not_invent_breach_or_clean_screening(empty_pipeline):
    result = pipeline.analyze('Example', empty_pipeline, concerns='hack and going concern', financial_metrics={'quick_ratio': .4})
    assert all(value is None for value in result['risk_scores'].values())
    assert result['automatic_escalations'] == []
    assert all(not explanation[pipeline.ARRAYS[category]] for category, explanation in result['explanations'].items())
    assert 'OFAC' not in result['data_sources_used']


def service_result(monkeypatch, data, filings_status='success', registry=None):
    monkeypatch.setattr(services, 'collect_vendor_signals', lambda **kw: data)
    monkeypatch.setattr(services, 'fetch_financial_and_profile', lambda *a, **kw: ({}, {}, {}))
    monkeypatch.setattr(services, 'search_all_registries', lambda *a: registry or {
        'federal_registry': {'identity_verified': True, 'business_number': '123456789', 'query_status': 'success'}})
    monkeypatch.setattr(services, 'search_litigation', lambda *a: {'query_status': 'success'})
    monkeypatch.setattr(services, 'search_filings', lambda *a: {'query_status': filings_status})
    return services.get_vendor_analysis('Example')[0]


def test_required_filing_failure_pauses_even_with_verified_registry(monkeypatch, empty_pipeline):
    result = service_result(monkeypatch, empty_pipeline, filings_status='failed')
    assert result['run_status'] == 'paused_source_unavailable'
    assert result['overall_score'] is None
    assert result['overall_risk_rating'] == 'Not assessed'
    assert 'SEDAR+' not in result['data_sources_used']


def test_registry_ambiguity_blocks_rating(monkeypatch, empty_pipeline):
    result = service_result(monkeypatch, empty_pipeline, registry={
        'federal_registry': {'identity_verified': False, 'ambiguous': True, 'query_status': 'success'}})
    assert result['disambiguation_flag']
    assert not result['jurisdiction_confirmed']
    assert result['run_status'] == 'awaiting_entity_confirmation'
    assert result['overall_score'] is None


def test_no_final_rating_without_evidence_and_approved_policy(monkeypatch, empty_pipeline):
    result = service_result(monkeypatch, empty_pipeline)
    assert result['run_status'] == 'insufficient_evidence'
    assert result['confidence_score'] is None
    assert any('CFG-VDD-001' in blocker for blocker in result['completion_blockers'])
    assert 'onboarding may proceed' not in result['recommended_action']


def test_registry_requires_authoritative_name_and_identifier():
    url = 'https://ised-isde.canada.ca/registry/record'
    text = 'Legal Name: Example Inc.\nBusiness Number: 123456789\n'
    verify = registry_verification.verify_record
    assert verify('Example', '123456789', url, text)['identity_verified']
    assert not verify('Other', '', url, text)['identity_verified']
    assert not verify('Example', '987654321', url, text)['identity_verified']
    assert not verify('Example', '', 'https://ised-isde.canada.ca.evil.example/', text)['identity_verified']
    assert not verify('Example', '', url, 'Search results for Example')['identity_verified']


def test_three_year_history_has_sources_and_no_invented_ratios():
    periods = pd.to_datetime(['2025-12-31', '2024-12-31', '2023-12-31'])
    income = pd.DataFrame([[100, 80, 60], [-10, -5, 5], [-8, -4, 6]],
                          index=['Total Revenue', 'Net Income', 'EBITDA'], columns=periods)
    balance = pd.DataFrame([[40, 50, 40], [100, 100, 0], [10, 10, 10]],
                           index=['Current Assets', 'Current Liabilities', 'Inventory'], columns=periods)
    history = financial_history.annual_history(income, balance, 'EX')
    assert len(history) == 3
    assert history[0]['quick_ratio'] == .3
    assert history[2]['current_ratio'] is None
    assert history[0]['debt_equity'] is None
    assert all(r['source_url'].startswith('https://finance.yahoo.com/') for r in history)
    signals = financial_history.history_signals(history)
    assert any('Negative EBITDA in two consecutive' in s['indicator'] for s in signals)
    assert not any('going concern' in s['indicator'].lower() for s in signals)
    assert not any('Negative EBITDA' in s['indicator'] for s in financial_history.history_signals([history[0], history[2]]))


def test_serper_cache_expires_and_keeps_original_retrieval_time(monkeypatch):
    monkeypatch.setattr(scraper, 'SERPER_API_KEY', 'offline-test')
    monkeypatch.setattr(scraper, '_SERPER_CACHE', {})
    response = Mock(status_code=200)
    response.json.return_value = {'organic': [{'title': 'Example notice', 'link': 'https://example.org/notice'}]}
    session = Mock()
    session.post.return_value = response
    monkeypatch.setattr(scraper.requests, 'Session', lambda: session)
    first = scraper._serper('Example query')
    second = scraper._serper('Example query')
    assert session.post.call_count == 1
    assert first[0]['retrieved_at'] == second[0]['retrieved_at']
    for entry in scraper._SERPER_CACHE.values():
        entry['cached_at'] -= config.CACHE_TTL_SECONDS + 1
    scraper._serper('Example query')
    assert session.post.call_count == 2


def test_recent_attrition_excludes_older_than_twelve_months():
    import ai_engine
    count, names = ai_engine._detect_recent_attrition(
        [{'name': 'Example Person'}], 'Example Person resigned 18 months ago.')
    assert (count, names) == (0, [])


def test_pdf_rating_uses_saved_policy_parameters():
    from pdf_generator import _tier_for
    assert _tier_for(45, {'HIGH_SCORE_THRESHOLD': 40, 'CRITICAL_SCORE_THRESHOLD': 80}) == 'High'
    assert _tier_for(77, {'HIGH_SCORE_THRESHOLD': 40, 'CRITICAL_SCORE_THRESHOLD': 80}) == 'High'
    assert _tier_for(None, {'HIGH_SCORE_THRESHOLD': 40}) == 'Not assessed'
