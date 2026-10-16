"""Persisted review queue, reviewer audit events, source health and administrator settings."""
from datetime import datetime, timezone
import os
import uuid
from fastapi import HTTPException, Depends
from pydantic import BaseModel, Field

PARAMETERS = {
    'LOOKBACK_MONTHS': (12, 60), 'CRITICAL_SCORE_THRESHOLD': (50, 90),
    'HIGH_SCORE_THRESHOLD': (30, 74), 'RECENCY_MULTIPLIER_12M': (1, 3),
    'MAX_NEWS_ARTICLES_LOGGED': (10, 200), 'MIN_CVSS_SCORE': (4, 10),
    'BITSIGHT_THRESHOLD_ELEVATED': (300, 700), 'AMP_MATERIALITY_THRESHOLD_CAD': (10000, 1000000),
}


class ReviewRequest(BaseModel):
    decision: str = Field(pattern='^(needs_information|reviewed|approve)$')
    notes: str = Field(min_length=10, max_length=10000)


def apply_settings(server):
    for key, value in (server.KV_STORE.get_json('admin:settings') or {}).items():
        if key in PARAMETERS:
            setattr(server.config, key, value)


def register(app, server):
    def role(info, required):
        if os.getenv('RENDER') and not server.config.API_KEYS:
            raise HTTPException(403, 'Configure API_KEYS_JSON with reviewer/admin roles before using review or administration on Render.')
        if server.config.API_KEYS and (info or {}).get('role') not in required:
            raise HTTPException(403, 'A reviewer or administrator role is required.')

    def owned_run(run_id, info):
        entry = server.KV_STORE.get_json(f'run:{run_id}')
        if not entry or entry.get('owner') != server._owner(info):
            raise HTTPException(404, 'Unknown assessment.')
        return entry

    @app.get('/api/reviews', tags=['Reviews'])
    def queue(info=Depends(server.require_api_key)):
        items = []
        for key in server.KV_STORE.keys('run:'):
            entry = server.KV_STORE.get_json(key)
            if entry and entry.get('owner') == server._owner(info):
                result = entry['result']
                item = {k: result.get(k) for k in ('run_id', 'vendor_name', 'query_date', 'run_status', 'review_status', 'review_flags')}
                reviews = sorted(server.KV_STORE.keys(f'review:{result["run_id"]}:'))
                if reviews:
                    latest = server.KV_STORE.get_json(reviews[-1])
                    item['review_status'] = latest['decision']
                items.append(item)
        return sorted(items, key=lambda x: x.get('query_date') or '', reverse=True)

    @app.get('/api/runs/{run_id}', tags=['Reviews'])
    def read_run(run_id: str, info=Depends(server.require_api_key)):
        return owned_run(run_id, info)['result']

    @app.get('/api/runs/{run_id}/reviews', tags=['Reviews'])
    def history(run_id: str, info=Depends(server.require_api_key)):
        owned_run(run_id, info)
        return [server.KV_STORE.get_json(k) for k in sorted(server.KV_STORE.keys(f'review:{run_id}:'))]

    @app.post('/api/runs/{run_id}/reviews', tags=['Reviews'])
    def review(run_id: str, request: ReviewRequest, info=Depends(server.require_api_key)):
        role(info, ('reviewer', 'admin'))
        result = owned_run(run_id, info)['result']
        if request.decision == 'approve' and (result.get('completion_blockers') or result.get('overall_score') is None):
            raise HTTPException(409, 'Required evidence or policy approval is missing. Record needs-information and rerun after resolving blockers.')
        event = {'review_id': uuid.uuid4().hex, 'run_id': run_id, 'reviewer': server._owner(info),
                 'created_at': datetime.now(timezone.utc).isoformat(), **request.model_dump()}
        server.KV_STORE.set_json(f'review:{run_id}:{event["created_at"]}:{event["review_id"]}', event)
        # Reviews are separate immutable records; a review cannot silently alter previously exported evidence.
        return event

    @app.post('/api/jobs/{job_id}/cancel', tags=['Jobs'])
    def cancel(job_id: str, info=Depends(server.require_api_key)):
        job = server.KV_STORE.get_json(f'job:{job_id}')
        if not job or job.get('owner') != server._owner(info):
            raise HTTPException(404, 'Unknown job.')
        if job['status'] in ('pending', 'running'):
            server.KV_STORE.set_json(f'cancel:{job_id}', {'requested': True})
            job['cancel_requested'] = True
            if job['status'] == 'pending':
                job['status'] = 'cancelled'
                server.KV_STORE.delete(f'inflight:{job["cache_key"]}')
            server.KV_STORE.set_json(f'job:{job_id}', job)
        return {'status': job['status'], 'cancel_requested': job.get('cancel_requested', False)}

    @app.get('/api/admin/settings', tags=['Administration'])
    def settings(info=Depends(server.require_api_key)):
        role(info, ('admin',))
        return {'active': {k: getattr(server.config, k) for k in PARAMETERS},
                'pending': server.KV_STORE.get_json('admin:settings') or {},
                'ranges': PARAMETERS, 'activation': 'Changes apply on application restart.'}

    @app.put('/api/admin/settings', tags=['Administration'])
    def save_settings(values: dict, info=Depends(server.require_api_key)):
        role(info, ('admin',))
        current = {k: getattr(server.config, k) for k in PARAMETERS}
        current.update(server.KV_STORE.get_json('admin:settings') or {})
        for key, value in values.items():
            if key not in PARAMETERS or isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(422, 'Unknown parameter or invalid numeric value.')
            low, high = PARAMETERS[key]
            if not low <= value <= high or (isinstance(getattr(server.config, key), int) and int(value) != value):
                raise HTTPException(422, f'{key} is outside its permitted range or precision.')
            current[key] = value
        if current['HIGH_SCORE_THRESHOLD'] >= current['CRITICAL_SCORE_THRESHOLD']:
            raise HTTPException(422, 'High threshold must be below the critical threshold.')
        server.KV_STORE.set_json('admin:settings', current)
        return {'pending': current, 'activation': 'Restart the application to apply these settings.'}
