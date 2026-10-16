"""Run identity, review authorization and durable worker regressions."""
import base64
import threading

import fakeredis
import pytest
from fastapi.testclient import TestClient

import config
import licensed_sources
import network_safety
import server
import store
from job_runner import JobRunner


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(server, 'KV_STORE', store.InMemoryKVStore())
    monkeypatch.setattr(server, 'RATE_LIMITER', store.InMemoryRateLimiter())
    monkeypatch.setattr(server.config, 'AUTO_GENERATE_PDF_REPORT', False)
    monkeypatch.setattr(server.config, 'API_KEYS', {
        'alice': {'client': 'tenant-a', 'role': 'reviewer', 'daily_quota': 1},
        'viewer': {'client': 'tenant-a', 'role': 'viewer'},
        'bob': {'client': 'tenant-b', 'role': 'admin'},
    })
    return TestClient(server.app)


def saved_run(run_id='r1', owner='tenant-a', score=None):
    result = {'run_id': run_id, 'vendor_name': 'Same Vendor', 'query_date': '2026-10-16',
              'overall_score': score, 'run_status': 'insufficient_evidence', 'review_status': 'pending',
              'completion_blockers': ['Evidence missing'], 'risk_scores': {}}
    entry = {'result': result, 'owner': owner, 'content_hash': server._content_hash(result),
             'pdf_bytes_b64': base64.b64encode(run_id.encode()).decode()}
    server.KV_STORE.set_json(f'run:{run_id}', entry)
    return result


def test_all_material_inputs_and_owner_partition_cache():
    req = server.AnalyzeRequest(vendor='Same Vendor')
    key = server._cache_key_for(req, 'Same Vendor', 'tenant-a')
    for field, value in [('business_number', '123456789'), ('concerns', 'breach'), ('province', 'Ontario'), ('company_url', 'https://example.org')]:
        changed = req.model_copy(update={field: value})
        assert server._cache_key_for(changed, 'Same Vendor', 'tenant-a') != key
    assert server._cache_key_for(req, 'Same Vendor', 'tenant-b') != key


def test_pdf_binds_exact_run_owner_and_content(api):
    first = saved_run('first', score=10)
    second = saved_run('second', score=90)
    assert server._find_cached_pdf(first, 'tenant-a') == b'first'
    assert server._find_cached_pdf(second, 'tenant-a') == b'second'
    assert server._find_cached_pdf(first, 'tenant-b') is None
    changed = dict(first, overall_score=99)
    assert server._find_cached_pdf(changed, 'tenant-a') is None
    assert api.post('/api/download-pdf', headers={'X-API-Key': 'alice'}, json={'result': changed}).status_code == 409
    assert api.post('/api/download-pdf', headers={'X-API-Key': 'bob'}, json={'result': first}).status_code == 404


def test_review_access_append_only_history_and_completion_gate(api):
    original = saved_run()
    payload = {'decision': 'reviewed', 'notes': 'Reviewed; more evidence needed.'}
    assert api.get('/api/runs/r1', headers={'X-API-Key': 'bob'}).status_code == 404
    assert api.post('/api/runs/r1/reviews', headers={'X-API-Key': 'viewer'}, json=payload).status_code == 403
    assert api.post('/api/runs/r1/reviews', headers={'X-API-Key': 'alice'}, json=payload).status_code == 200
    payload['decision'] = 'approve'
    assert api.post('/api/runs/r1/reviews', headers={'X-API-Key': 'alice'}, json=payload).status_code == 409
    history = api.get('/api/runs/r1/reviews', headers={'X-API-Key': 'alice'}).json()
    assert len(history) == 1 and history[0]['decision'] == 'reviewed'
    assert api.get('/api/runs/r1', headers={'X-API-Key': 'alice'}).json() == original
    queue = api.get('/api/reviews', headers={'X-API-Key': 'alice'}).json()
    assert queue[0]['review_status'] == 'reviewed'
    assert api.get('/api/reviews', headers={'X-API-Key': 'bob'}).json() == []


def test_polling_does_not_spend_analysis_quota(api):
    job = {'job_id': 'job', 'status': 'pending', 'vendor': 'Example', 'created_at': '2026-10-16', 'owner': 'tenant-a'}
    server.KV_STORE.set_json('job:job', job)
    server.RATE_LIMITER.hit('quota:alice', 86400, 1)
    for _ in range(3):
        assert api.get('/api/jobs/job', headers={'X-API-Key': 'alice'}).status_code == 200
    assert api.get('/api/jobs/job', headers={'X-API-Key': 'bob'}).status_code == 404
    assert api.post('/api/jobs', headers={'X-API-Key': 'alice'}, json={'vendor': 'Example'}).status_code == 429


def test_admin_setting_ranges_and_roles(api):
    assert api.get('/api/admin/settings', headers={'X-API-Key': 'alice'}).status_code == 403
    assert api.put('/api/admin/settings', headers={'X-API-Key': 'bob'}, json={'LOOKBACK_MONTHS': 500}).status_code == 422
    assert api.put('/api/admin/settings', headers={'X-API-Key': 'bob'}, json={'LOOKBACK_MONTHS': 24}).status_code == 200
    assert api.get('/api/admin/settings', headers={'X-API-Key': 'bob'}).json()['pending']['LOOKBACK_MONTHS'] == 24


def test_refresh_runs_pipeline_instead_of_reusing_cached_assessment(api, monkeypatch):
    calls = []
    def analyze(**kw):
        calls.append(kw)
        return {'vendor_name': kw['vendor'], 'risk_scores': {}, 'run_status': 'awaiting_review'}, {}
    monkeypatch.setattr(server, 'get_vendor_analysis', analyze)
    request = server.AnalyzeRequest(vendor='Example')
    first = server._run_analysis(request)
    assert server._run_analysis(request)['run_id'] == first['run_id']
    refreshed = server._run_analysis(request.model_copy(update={'refresh': True}))
    assert refreshed['run_id'] != first['run_id']
    assert len(calls) == 2


@pytest.mark.parametrize('backend', ['memory', 'sqlite', 'redis'])
def test_leases_cannot_be_renewed_or_released_by_another_worker(tmp_path, backend):
    kv = {'memory': lambda: store.InMemoryKVStore(), 'sqlite': lambda: store.SQLiteKVStore(str(tmp_path / 'state.db')),
          'redis': lambda: store.RedisKVStore(fakeredis.FakeStrictRedis(decode_responses=True))}[backend]()
    first, other = {'worker': 'first'}, {'worker': 'other'}
    assert kv.try_claim('lease:a', first, ttl_seconds=120)
    assert not kv.try_claim('lease:a', other, ttl_seconds=120)
    assert not kv.renew_claim('lease:a', other, 120)
    kv.release_claim('lease:a', other)
    assert kv.get_json('lease:a') == first
    assert kv.renew_claim('lease:a', first, 120)
    kv.release_claim('lease:a', first)
    assert kv.try_claim('lease:a', other, ttl_seconds=120)


def test_pending_job_recovers_from_reopened_sqlite(tmp_path):
    path = str(tmp_path / 'state.db')
    before = store.SQLiteKVStore(path)
    before.set_json('job:restart', {'job_id': 'restart', 'status': 'running', 'request': {'vendor': 'Example'}})
    after = store.SQLiteKVStore(path)
    done = threading.Event()
    def execute(job, kv, owns_lease):
        assert owns_lease()
        job['status'] = 'needs_review'
        kv.set_json('job:restart', job)
        done.set()
    runner = JobRunner(after, execute, concurrency=1)
    try:
        runner.recover()
        assert done.wait(3)
        assert after.get_json('job:restart')['status'] == 'needs_review'
    finally:
        runner.shutdown()


def test_only_one_worker_executes_a_job_and_concurrency_is_bounded():
    kv = store.InMemoryKVStore()
    for name in ['one', 'two']:
        kv.set_json(f'job:{name}', {'job_id': name, 'status': 'pending', 'request': {'vendor': name}})
    entered, release = threading.Event(), threading.Event()
    calls = []
    def execute(job, state, owns_lease):
        calls.append(job['job_id'])
        entered.set()
        release.wait(3)
    first, second = JobRunner(kv, execute, concurrency=1), JobRunner(kv, execute, concurrency=1)
    try:
        assert first.submit('one')
        assert entered.wait(3)
        assert not first.submit('two')
        assert not second.submit('one')
        assert calls == ['one']
    finally:
        release.set()
        first.shutdown()
        second.shutdown()


def test_paid_key_presence_does_not_claim_implemented_connector(monkeypatch):
    monkeypatch.setenv('BITSIGHT_API_KEY', 'placeholder-not-a-credential')
    label = next(name for name in licensed_sources.LICENSED_SOURCES if name.startswith('BitSight'))
    assert not licensed_sources.is_configured(label)
    assert label in licensed_sources.missing_sources_for_dimension('cyber')


@pytest.mark.parametrize('value', ['not-json', '{}', '[]', '{"key": {"client": "a", "daily_quota": -1}}'])
def test_invalid_auth_configuration_cannot_fail_open(monkeypatch, value):
    monkeypatch.setenv('API_KEYS_JSON', value)
    with pytest.raises(RuntimeError, match='refusing to disable authentication'):
        config._parse_api_keys()


@pytest.mark.parametrize('url', ['http://example.org', 'https://127.0.0.1', 'https://user:secret@example.org', 'https://example.org:8080'])
def test_unsafe_callback_destinations_rejected(url):
    with pytest.raises(ValueError):
        network_safety.public_https_url(url, {'example.org', '127.0.0.1'})


def test_cancellation_survives_worker_stage_updates(api, monkeypatch):
    job = {'job_id': 'cancelled', 'status': 'running', 'vendor': 'Example', 'created_at': '2026-10-16',
           'owner': 'tenant-a', 'cache_key': 'cache'}
    server.KV_STORE.set_json('job:cancelled', job)
    response = api.post('/api/jobs/cancelled/cancel', headers={'X-API-Key': 'alice'})
    assert response.status_code == 200
    assert server.KV_STORE.get_json('cancel:cancelled')['requested']
    def analyze(**kw):
        kw['progress']('collecting_sources')
        raise AssertionError('Cancelled work must stop at the checkpoint')
    monkeypatch.setattr(server, 'get_vendor_analysis', analyze)
    # The worker's earlier local snapshot deliberately omits the cancellation flag.
    server._execute_job('cancelled', server.AnalyzeRequest(vendor='Example'), 'cache', job)
    assert server.KV_STORE.get_json('job:cancelled')['status'] == 'cancelled'
    assert not server.KV_STORE.keys('run:')


def test_render_does_not_expose_local_admin_bypass(api, monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setattr(server.config, 'API_KEYS', {})
    saved_run(owner='local')
    assert api.get('/api/admin/settings').status_code == 403
    assert api.put('/api/admin/settings', json={'LOOKBACK_MONTHS': 24}).status_code == 403
    assert api.post('/api/runs/r1/reviews', json={'decision': 'reviewed', 'notes': 'An anonymous review must be blocked.'}).status_code == 403


def test_health_exposes_render_revision_without_credentials(api, monkeypatch):
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'abc123')
    response = api.get('/api/health')
    assert response.status_code == 200
    assert response.json()['deployment_commit'] == 'abc123'
