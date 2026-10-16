"""
server.py - DRiskify (NIVETA Platform) REST API Server
------------------------------------------------------
Serves endpoints for:
- POST /api/analyze: Runs SK-VDD-001 Due Diligence Pipeline (synchronous -
  blocks for the full run, from ~90s to 15+ minutes depending on upstream
  LLM/search latency; kept for the bundled UI, which already shows its own
  loading state for however long that takes)
- POST /api/jobs, GET /api/jobs/{job_id}: same pipeline, asynchronous - the
  intended integration surface for a caller embedding this as a feature in
  another system, where a multi-minute blocking HTTP call isn't viable
  against that system's own timeouts/gateways
- POST /api/download-pdf: Generates and streams official SK-VDD-001 PDF report
- GET  /api/presets: Returns pre-configured enterprise targets
- GET  /api/health: Status check for AI & Serper APIs
- Serves static production build from frontend/dist (if built)
"""

import os
import io
import json
import time
import uuid
import base64
import threading
import hashlib
import tempfile
import re
from concurrent.futures import ThreadPoolExecutor
from network_safety import public_https_url
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Response, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List

from services import get_vendor_analysis
from normalizer import normalize_vendor_name
from pdf_generator import generate_pdf
from store import create_stores, RedisKVStore, SQLiteKVStore
from job_runner import JobRunner
import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_print(msg: str):
    """Windows cp1252-safe logging (matches the pattern used across the codebase)."""
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass

app = FastAPI(
    title="DRiskify NIVETA Platform API",
    description=(
        "Skill SK-VDD-001: Vendor Intelligence Scraping for Due Diligence. "
        "For an embedded/automated integration, use POST /api/jobs + "
        "GET /api/jobs/{job_id} (optionally with callback_url) rather than "
        "the synchronous POST /api/analyze - a real analysis run has been "
        "observed taking anywhere from ~90 seconds to 15+ minutes depending "
        "on upstream LLM/search latency, which is not viable to hold open "
        "as a single blocking HTTP call against most gateways/clients."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "Analysis", "description": "Run the SK-VDD-001 pipeline synchronously (for the bundled UI)."},
        {"name": "Jobs", "description": "Run the same pipeline asynchronously - the integration surface for embedding this as a feature in another system."},
        {"name": "Reports", "description": "Generate/download the official PDF report for a completed analysis."},
        {"name": "Meta", "description": "Health, configuration, and reference data."},
    ],
)

# CORS: locked to config.ALLOWED_ORIGINS (default: local dev origins only).
# The previous allow_origins=["*"] combined with allow_credentials=True was
# already an invalid combination browsers reject outright, so no genuine
# credentialed cross-origin request was ever actually working under it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# KV_STORE backs the analysis cache and job records; RATE_LIMITER backs both
# the per-IP abuse-prevention limit and per-API-key daily quota. Redis-backed
# when config.REDIS_URL is set and reachable, otherwise the same in-memory
# behavior this had before - see store.py for the full rationale. Either
# way, FastAPI runs sync endpoints in a threadpool, so even a single uvicorn
# worker hits these from multiple threads at once; both backends handle that
# internally (a lock for in-memory, atomicity of Redis commands for Redis).
KV_STORE, RATE_LIMITER = create_stores()


def _check_rate_limit(client_ip: str):
    if not RATE_LIMITER.hit(f"ip:{client_ip}", config.RATE_LIMIT_WINDOW_SECONDS, config.RATE_LIMIT_MAX_REQUESTS):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {config.RATE_LIMIT_MAX_REQUESTS} requests per "
                   f"{config.RATE_LIMIT_WINDOW_SECONDS}s. Try again shortly."
        )


def require_api_key(request: Request, x_api_key: str = Header(default="")) -> Optional[dict]:
    """No-op (returns None, no auth enforced) when config.API_KEYS is empty
    - preserves the local-dev default. When configured, validates the key
    AND enforces its per-client daily quota (a cost-control budget per
    integration - distinct from the per-IP burst-abuse limit above, which
    applies regardless of auth). Returns the matched client's info dict so
    callers that want to know who's calling (e.g. to record it on a job)
    can take it as a dependency parameter instead of a bare
    dependencies=[...] entry.
    """
    if not config.API_KEYS:
        return None
    client_info = config.API_KEYS.get(x_api_key)
    if client_info is None:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")
    quota = client_info.get("daily_quota")
    if quota and request.method == "POST" and request.url.path in ("/api/jobs", "/api/analyze") and not RATE_LIMITER.hit(f"quota:{x_api_key}", 86400, quota):
        raise HTTPException(
            status_code=429,
            detail=f"Daily quota exceeded for this API key ({quota}/day). Resets on a rolling 24h window."
        )
    return dict(client_info, owner=client_info.get("client") or hashlib.sha256(x_api_key.encode()).hexdigest())

# Pre-configured enterprise targets (Canadian & Global)
PRESETS = [
    {
        "name": "Shopify Inc.",
        "clean_name": "Shopify",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.shopify.com",
        "ticker": "SHOP",
        "badge": "TSX: SHOP • Ottawa"
    },
    {
        "name": "BlackBerry Limited",
        "clean_name": "BlackBerry",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.blackberry.com",
        "ticker": "BB",
        "badge": "TSX: BB • Waterloo"
    },
    {
        "name": "CGI Inc.",
        "clean_name": "CGI",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.cgi.com",
        "ticker": "GIB.A",
        "badge": "TSX: GIB.A • Montreal"
    },
    {
        "name": "OpenText Corporation",
        "clean_name": "OpenText",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.opentext.com",
        "ticker": "OTEX",
        "badge": "TSX: OTEX • Waterloo"
    },
    {
        "name": "Royal Bank of Canada (RBC)",
        "clean_name": "Royal Bank of Canada",
        "industry": "Banking, Financial & FinTech",
        "country": "Canada",
        "domain": "https://www.rbc.com",
        "ticker": "RY",
        "badge": "TSX: RY • Toronto"
    },
    {
        "name": "Constellation Software Inc.",
        "clean_name": "Constellation Software",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.csisoftware.com",
        "ticker": "CSU",
        "badge": "TSX: CSU • Toronto"
    },
    {
        "name": "Thomson Reuters",
        "clean_name": "Thomson Reuters",
        "industry": "Telecommunications & Media",
        "country": "Canada",
        "domain": "https://www.thomsonreuters.com",
        "ticker": "TRI",
        "badge": "TSX: TRI • Toronto"
    },
    {
        "name": "Bombardier Inc.",
        "clean_name": "Bombardier",
        "industry": "Manufacturing & Supply Chain",
        "country": "Canada",
        "domain": "https://www.bombardier.com",
        "ticker": "BBD.B",
        "badge": "TSX: BBD.B • Montreal"
    }
]


class AnalyzeRequest(BaseModel):
    vendor: str = Field(..., max_length=250, description="Legal or trade name to analyze, e.g. 'Shopify Inc.'. Required.", examples=["Shopify Inc."])
    # Section 4.1: "NIVETA shall not assume any additional context beyond
    # what is explicitly provided." Defaulting to a specific named industry
    # (the old default was "Technology & SaaS") isn't just cosmetically
    # wrong for a non-tech vendor — it also feeds ai_engine.py's cyber-score
    # heuristic, silently inflating an unrelated company's baseline cyber
    # risk score. Empty here lets services.py/ai_engine.py's existing
    # neutral fallback ("General Commercial Services") actually apply.
    industry: Optional[str] = Field("", description="Known industry, if any. Left blank rather than guessed - an assumed industry biases the cyber-risk heuristic.")
    province: str = Field("", max_length=100)
    refresh: bool = False
    country: Optional[str] = Field("Canada", description="Registration/operating jurisdiction.")
    concerns: Optional[str] = Field("", max_length=5000, description="Free-text specific concerns to focus the analysis on, if any.")
    company_url: Optional[str] = Field("", description="Corporate website, if known - improves profile/domain-based lookups.")
    business_number: Optional[str] = Field("", description="9-digit CRA Business Number, if known.")
    ticker: Optional[str] = Field("", description="Stock ticker, if publicly traded - skips ticker discovery and improves yfinance accuracy.")
    # Section 4.3 Optional Context Parameters
    duns_number: Optional[str] = Field("", description="D-U-N-S number, if known.")
    naics_code: Optional[str] = Field("", description="NAICS industry classification code, if known.")
    # /api/jobs only: if set, the completed job (success or failure) is
    # POSTed here as JSON so the caller doesn't have to poll. Best-effort -
    # a failed delivery doesn't fail the job, and the result stays available
    # via GET /api/jobs/{job_id} regardless.
    callback_url: Optional[str] = Field(
        "", description="POST /api/jobs only. If set, the finished JobRecord (success or failure) is POSTed "
                         "here as JSON once - a best-effort delivery; a failed callback never fails the job, "
                         "and GET /api/jobs/{job_id} remains the source of truth regardless."
    )


class PdfRequest(BaseModel):
    result: Dict[str, Any] = Field(..., description="A completed analysis result, exactly as returned by POST /api/analyze or a JobRecord's `result` field.")
    vendor_name: Optional[str] = "Vendor Entity"


class HealthResponse(BaseModel):
    status: str
    deployment_commit: Optional[str] = None
    groq_configured: bool
    gemini_configured: bool
    openai_configured: bool
    serper_configured: bool
    state_backend: str = Field(description="'redis' (shared/durable across restarts and replicas) or 'in-memory' (single-instance only) - see store.py.")
    api_key_auth_enabled: bool
    skill_id: str
    platform: str


class PresetItem(BaseModel):
    name: str
    clean_name: str
    industry: str
    country: str
    domain: str
    ticker: str
    badge: str


class NormalizeResponse(BaseModel):
    raw_name: str
    normalized_name: str
    variants: List[str]
    french_variant: Optional[str] = None


class JobRecord(BaseModel):
    job_id: str
    status: str = Field(description="One of: pending, running, complete, failed.")
    vendor: str
    client: Optional[str] = Field(None, description="Identified API-key client that submitted this job, if API-key auth is configured.")
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = Field(
        None, description="The full analysis result once status is 'complete' - same shape as POST /api/analyze's "
                           "response. Not strictly typed here: this object has grown organically across the SK-VDD-001 "
                           "pipeline's dimensions and is large; treat it as a JSON object rather than a fixed schema."
    )
    error: Optional[str] = Field(None, description="Failure detail once status is 'failed'.")
    stage: Optional[str] = None


@app.get("/api/health", response_model=HealthResponse, tags=["Meta"], summary="Service and configuration status")
def health():
    return {
        "status": "healthy",
        "deployment_commit": os.getenv('RENDER_GIT_COMMIT') or None,
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "serper_configured": bool(os.getenv("SERPER_API_KEY")),
        # "redis" means the cache/job-store/rate-limiter are shared and
        # durable across restarts and replicas; "in-memory" means they're
        # not - see store.py. Surfaced here so an operator can tell at a
        # glance whether this instance is safe to run behind more than one
        # replica without it, rather than discovering it the hard way.
        "state_backend": "redis" if isinstance(KV_STORE, RedisKVStore) else "sqlite" if isinstance(KV_STORE, SQLiteKVStore) else "in-memory",
        "api_key_auth_enabled": bool(config.API_KEYS),
        "skill_id": "SK-VDD-001",
        "platform": "DRiskify - NIVETA"
    }


@app.get("/api/presets", response_model=List[PresetItem], tags=["Meta"], summary="Pre-configured enterprise targets")
def get_presets():
    return PRESETS


@app.post("/api/normalize", response_model=NormalizeResponse, tags=["Meta"],
          summary="Preview name normalization without running an analysis")
def normalize_input(data: Dict[str, str]):
    vendor = data.get("vendor", "")
    return normalize_vendor_name(vendor)


def _owner(client_info):
    return (client_info or {}).get('owner') or (client_info or {}).get('client') or 'local'


def _content_hash(result):
    return hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _cache_key_for(req: AnalyzeRequest, clean_name: str, owner='local') -> str:
    payload = req.model_dump(exclude={'callback_url', 'refresh'})
    payload.update(owner=owner, normalized_vendor=clean_name, policy_version='provisional-v2',
                   parameters={k: getattr(config, k) for k in (
                       'LOOKBACK_MONTHS', 'RECENCY_MULTIPLIER_12M', 'CRITICAL_SCORE_THRESHOLD',
                       'HIGH_SCORE_THRESHOLD', 'MIN_CVSS_SCORE', 'AMP_MATERIALITY_THRESHOLD_CAD',
                       'MAX_NEWS_ARTICLES_LOGGED')})
    return _content_hash(payload)


def _render_pdf(result):
    # Unique server-generated paths prevent vendor-controlled path traversal and concurrent file collisions.
    with tempfile.TemporaryDirectory(prefix='driskify-report-') as directory:
        path = os.path.join(directory, 'report.pdf')
        generate_pdf(result, filename=path, vendor_name=result.get('vendor_name', 'Vendor'))
        with open(path, 'rb') as report:
            return report.read()


def _run_analysis(req: AnalyzeRequest, owner='local', progress=None, state=None) -> dict:
    state = state or KV_STORE
    clean_name = normalize_vendor_name(req.vendor)['normalized_name']
    key = _cache_key_for(req, clean_name, owner)
    cached = state.get_json(f'analysis:{key}') if not req.refresh else None
    if cached:
        return cached['result']
    kwargs = req.model_dump(exclude={'callback_url', 'refresh'})
    kwargs = {k: (v or '') for k, v in kwargs.items()}
    kwargs['country'] = req.country or 'Canada'
    if progress:
        kwargs['progress'] = progress
    result, _ = get_vendor_analysis(**kwargs)
    if 'error' in result and not result.get('risk_scores'):
        raise RuntimeError(result['error'])
    result.setdefault('run_id', uuid.uuid4().hex)
    result.setdefault('schema_version', '2.0')
    result.setdefault('review_status', 'pending')
    entry = {'result': result, 'owner': owner, 'content_hash': _content_hash(result)}
    if config.AUTO_GENERATE_PDF_REPORT:
        try:
            entry['pdf_bytes_b64'] = base64.b64encode(_render_pdf(result)).decode('ascii')
        except Exception:
            result.setdefault('data_gaps', []).append('PDF generation failed; JSON retained. Retry PDF export.')
            result['report_status'] = 'pdf_failed'
            entry['content_hash'] = _content_hash(result)
    # Immutable run records keep older reports and review history addressable independently of analysis cache.
    if progress:
        progress('saving_report')
    state.set_json(f'run:{result["run_id"]}', entry)
    if result.get('run_status') in (None, 'complete', 'awaiting_review') and result.get('report_status') != 'pdf_failed':
        state.set_json(f'analysis:{key}', entry, ttl_seconds=config.CACHE_TTL_SECONDS)
    return result


@app.post(
    "/api/analyze", dependencies=[Depends(require_api_key)], tags=["Analysis"],
    summary="Run the due-diligence pipeline (blocking)",
    description="Blocks until the full analysis completes - observed live anywhere from ~90s to 15+ minutes "
                 "depending on upstream LLM/search latency. For an embedded/automated integration, prefer "
                 "POST /api/jobs instead. Response body is the full SK-VDD-001 result object (same shape as "
                 "a JobRecord's `result` field) - not strictly typed here as it's large and has grown "
                 "organically across the pipeline's dimensions.",
)
def analyze_vendor(req: AnalyzeRequest, request: Request, client_info: Optional[dict] = Depends(require_api_key)):
    if not req.vendor or not req.vendor.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")

    _check_rate_limit(request.client.host if request.client else "unknown")

    try:
        return _run_analysis(req, _owner(client_info))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Async job pattern ─────────────────────────────────────────────────────
# /api/analyze above blocks for the whole pipeline run - anywhere from ~90s
# to 15+ minutes depending on upstream LLM/search latency, entirely outside
# this service's control. That's fine for the bundled UI, which shows its
# own loading state, but it's not viable for another system calling this as
# an embedded feature: a caller's own HTTP client, gateway, or load balancer
# will almost certainly time out well before a slow run finishes. This is
# the intended integration surface instead: submit a job, then either poll
# GET /api/jobs/{job_id} or supply callback_url for a one-shot webhook.
#
# Backed by KV_STORE (Redis when configured, in-memory otherwise - see
# store.py), so a job survives regardless of which replica later serves the
# GET, and a restart doesn't silently drop an in-flight job. Every write to
# a job record refreshes its TTL (JOB_RETENTION_SECONDS), so a job that's
# never terminal (e.g. the worker crashed before reaching `finally`) still
# ages out on its own rather than lingering forever - there's no separate
# manual sweep to keep in sync with that.

# cache_key -> job_id, only while that job is pending/running. Lets a
# duplicate submission for the same (vendor, country, industry, ticker,
# company_url, duns, naics) while one is already in flight return the
# EXISTING job instead of paying for and running a second one in parallel -
# cheap idempotency piggybacked on the same key the analysis cache uses.
# Claimed via try_claim (atomic set-if-absent), not a plain get-then-set:
# under Redis, two near-simultaneous submissions each doing their own
# get_json/set_json could BOTH see "nothing in flight yet" and both start
# the pipeline - try_claim closes that race for both backends.
_INFLIGHT_TTL_SECONDS = max(config.JOB_RETENTION_SECONDS, 3600)


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    poll_url: str


def _send_webhook(callback_url: str, job: dict):
    try:
        public_https_url(callback_url, config.CALLBACK_ALLOWED_HOSTS)
        requests.post(callback_url, json=job, timeout=10, allow_redirects=False)
    except Exception:
        _safe_print(f"[!] Job {job['job_id']}: callback delivery failed.")


def _execute_job(job_id: str, req: AnalyzeRequest, cache_key: str, job: dict, state=None, owns_lease=lambda: True):
    state = state or KV_STORE
    job_key = f"job:{job_id}"
    job["status"] = "running"
    job["started_at"] = _now_iso()
    state.set_json(job_key, job)

    try:
        def progress(stage):
            if not owns_lease():
                raise RuntimeError('Execution lease expired; another worker will resume this job.')
            if state.get_json(f'cancel:{job_id}') or (state.get_json(job_key) or {}).get('cancel_requested'):
                raise RuntimeError('Cancelled by reviewer.')
            job['stage'] = stage
            state.set_json(job_key, job)
        result = _run_analysis(req, job.get('owner', 'local'), progress, state)
        job["status"] = 'complete' if result.get('run_status') in (None, 'complete') else 'needs_review'
        job["result"] = result
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        if not owns_lease():
            return
        if state.get_json(f'cancel:{job_id}') or (state.get_json(job_key) or {}).get('cancel_requested'):
            job['status'] = 'cancelled'
            job['cancel_requested'] = True
        job["completed_at"] = _now_iso()
        state.set_json(job_key, job)
        state.delete(f"inflight:{cache_key}")
        if req.callback_url:
            _send_webhook(req.callback_url, JobRecord(**job).model_dump())


_RUNNERS = {}
_RUNNER_LOCK = threading.Lock()

def _runner():
    with _RUNNER_LOCK:
        key = id(KV_STORE)
        if key not in _RUNNERS:
            def execute(job, state, owns_lease):
                _execute_job(job['job_id'], AnalyzeRequest(**job['request']), job['cache_key'], job, state, owns_lease)
            _RUNNERS[key] = JobRunner(KV_STORE, execute, config.MAX_CONCURRENT_JOBS)
            _RUNNERS[key].start()
        return _RUNNERS[key]


@app.on_event('startup')
def recover_jobs():
    from review_api import apply_settings
    apply_settings(sys.modules[__name__])
    _runner()


@app.on_event('shutdown')
def close_workers():
    for runner in list(_RUNNERS.values()):
        runner.shutdown()
    _RUNNERS.clear()


@app.post(
    "/api/jobs", dependencies=[Depends(require_api_key)], status_code=202, response_model=JobSubmitResponse,
    tags=["Jobs"], summary="Submit an analysis job (non-blocking)",
    description="Returns immediately with a job_id - the pipeline runs in the background. Poll "
                 "GET /api/jobs/{job_id} for status/result, or set callback_url for a one-shot webhook instead. "
                 "A duplicate submission (same vendor + country + industry + ticker + company_url + duns_number "
                 "+ naics_code) while a matching job is already pending/running returns that existing job_id "
                 "rather than starting duplicate work.",
)
def submit_job(req: AnalyzeRequest, request: Request, client_info: Optional[dict] = Depends(require_api_key)):
    if not req.vendor or not req.vendor.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")

    _check_rate_limit(request.client.host if request.client else "unknown")

    clean_name = normalize_vendor_name(req.vendor)["normalized_name"]
    if req.callback_url:
        try:
            public_https_url(req.callback_url, config.CALLBACK_ALLOWED_HOSTS)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
    cache_key = _cache_key_for(req, clean_name, _owner(client_info))
    inflight_key = f"inflight:{cache_key}"

    job_id = uuid.uuid4().hex
    claimed = KV_STORE.try_claim(inflight_key, {"job_id": job_id}, ttl_seconds=_INFLIGHT_TTL_SECONDS)
    if not claimed:
        existing_inflight = KV_STORE.get_json(inflight_key)
        existing_job_id = existing_inflight["job_id"] if existing_inflight else None
        existing_job = KV_STORE.get_json(f"job:{existing_job_id}") if existing_job_id else None
        if existing_job:
            return JobSubmitResponse(
                job_id=existing_job_id, status=existing_job["status"], poll_url=f"/api/jobs/{existing_job_id}",
            )
        # The in-flight claim raced with the job record itself expiring/
        # being cleaned up (narrow window) - fall through and start a fresh
        # job rather than surfacing a confusing dead end to the caller.

    job = {
        "job_id": job_id,
        "status": "pending",
        "vendor": clean_name,
        "client": client_info.get("client") if client_info else None,
        "owner": _owner(client_info),
        "request": req.model_dump(),
        "cache_key": cache_key,
        "stage": "queued",
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    KV_STORE.set_json(f"job:{job_id}", job)

    _runner().submit(job_id)

    return JobSubmitResponse(job_id=job_id, status="pending", poll_url=f"/api/jobs/{job_id}")


@app.get(
    "/api/jobs/{job_id}", dependencies=[Depends(require_api_key)], response_model=JobRecord, tags=["Jobs"],
    summary="Poll a job's status/result", responses={404: {"description": "Unknown or expired job_id."}},
)
def get_job(job_id: str, client_info: Optional[dict] = Depends(require_api_key)):
    job = KV_STORE.get_json(f"job:{job_id}")
    if job is None or job.get('owner', 'local') != _owner(client_info):
        raise HTTPException(status_code=404, detail="Unknown or expired job_id.")
    return job


def _find_cached_pdf(result: dict, owner='local'):
    run_id = result.get('run_id')
    if not run_id:
        return None
    entry = KV_STORE.get_json(f'run:{run_id}')
    if not entry or entry.get('owner') != owner or entry.get('content_hash') != _content_hash(result):
        return None
    return base64.b64decode(entry['pdf_bytes_b64']) if entry.get('pdf_bytes_b64') else None


@app.post('/api/download-pdf', response_class=Response, tags=['Reports'])
def download_pdf(req: PdfRequest, client_info: Optional[dict] = Depends(require_api_key)):
    result = req.result
    if result.get('run_id'):
        entry = KV_STORE.get_json(f'run:{result["run_id"]}')
        if not entry or entry.get('owner') != _owner(client_info):
            raise HTTPException(status_code=404, detail='Unknown assessment.')
        if entry['content_hash'] != _content_hash(result):
            raise HTTPException(status_code=409, detail='Report content differs from its saved assessment. Reload the run.')
    elif config.API_KEYS:
        raise HTTPException(status_code=400, detail='A saved assessment run_id is required.')
    try:
        pdf = _find_cached_pdf(result, _owner(client_info)) or _render_pdf(result)
        filename = re.sub(r'[^a-zA-Z0-9_-]', '_', str(result.get('vendor_name', 'vendor')))[:80]
        return Response(content=pdf, media_type='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="DRiskify_{filename}.pdf"'})
    except Exception:
        raise HTTPException(status_code=500, detail='PDF generation failed. The saved JSON remains available.')


# Register API routes before the static frontend catch-all.
import sys
from review_api import register
register(app, sys.modules[__name__])

# Serve frontend static build if present
dist_path = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting DRiskify NIVETA REST API on http://localhost:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
