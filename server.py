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
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Response, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from services import get_vendor_analysis
from normalizer import normalize_vendor_name
from pdf_generator import generate_pdf
from store import create_stores, RedisKVStore
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


def require_api_key(x_api_key: str = Header(default="")) -> Optional[dict]:
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
    if quota and not RATE_LIMITER.hit(f"quota:{x_api_key}", 86400, quota):
        raise HTTPException(
            status_code=429,
            detail=f"Daily quota exceeded for this API key ({quota}/day). Resets on a rolling 24h window."
        )
    return client_info

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
    vendor: str = Field(..., description="Legal or trade name to analyze, e.g. 'Shopify Inc.'. Required.", examples=["Shopify Inc."])
    # Section 4.1: "NIVETA shall not assume any additional context beyond
    # what is explicitly provided." Defaulting to a specific named industry
    # (the old default was "Technology & SaaS") isn't just cosmetically
    # wrong for a non-tech vendor — it also feeds ai_engine.py's cyber-score
    # heuristic, silently inflating an unrelated company's baseline cyber
    # risk score. Empty here lets services.py/ai_engine.py's existing
    # neutral fallback ("General Commercial Services") actually apply.
    industry: Optional[str] = Field("", description="Known industry, if any. Left blank rather than guessed - an assumed industry biases the cyber-risk heuristic.")
    country: Optional[str] = Field("Canada", description="Registration/operating jurisdiction.")
    concerns: Optional[str] = Field("", description="Free-text specific concerns to focus the analysis on, if any.")
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


@app.get("/api/health", response_model=HealthResponse, tags=["Meta"], summary="Service and configuration status")
def health():
    return {
        "status": "healthy",
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "serper_configured": bool(os.getenv("SERPER_API_KEY")),
        # "redis" means the cache/job-store/rate-limiter are shared and
        # durable across restarts and replicas; "in-memory" means they're
        # not - see store.py. Surfaced here so an operator can tell at a
        # glance whether this instance is safe to run behind more than one
        # replica without it, rather than discovering it the hard way.
        "state_backend": "redis" if isinstance(KV_STORE, RedisKVStore) else "in-memory",
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


def _cache_key_for(req: AnalyzeRequest, clean_name: str) -> str:
    return f"{clean_name}__{req.country}__{req.industry}__{req.ticker}__{req.company_url}__{req.duns_number}__{req.naics_code}"


def _run_analysis(req: AnalyzeRequest) -> dict:
    """The actual SK-VDD-001 pipeline run, shared by the synchronous
    /api/analyze endpoint and the async /api/jobs worker below. Raises
    RuntimeError on failure rather than HTTPException - this runs from a
    background thread for the job path, which isn't a FastAPI request
    context, so HTTPException there would just be a confusingly-named plain
    exception rather than doing anything HTTP-specific."""
    norm = normalize_vendor_name(req.vendor)
    clean_name = norm["normalized_name"]

    cache_key = _cache_key_for(req, clean_name)
    cache_storage_key = f"analysis:{cache_key}"
    # Expiry is handled by the store's own ttl_seconds (both backends) -
    # a hit here is, by construction, within config.CACHE_TTL_SECONDS.
    cached = KV_STORE.get_json(cache_storage_key)
    if cached:
        _safe_print(f"[cache] Returning cached analysis for: {clean_name}")
        return cached["result"]

    result, raw_signals = get_vendor_analysis(
        vendor=clean_name,
        industry=req.industry or "",
        country=req.country or "Canada",
        concerns=req.concerns or "",
        company_url=req.company_url or "",
        business_number=req.business_number or "",
        ticker=req.ticker or "",
        duns_number=req.duns_number or "",
        naics_code=req.naics_code or "",
    )

    if "error" in result and not result.get("risk_scores"):
        raise RuntimeError(result["error"])

    cache_entry = {"result": result}

    # Section 11 auto_generate_pdf_report: previously defined but not wired to
    # any behavior. Generating it eagerly here (instead of only on-demand in
    # /api/download-pdf) both honors the flag and means the later download
    # call can serve these bytes straight from cache instead of re-rendering.
    if config.AUTO_GENERATE_PDF_REPORT:
        try:
            _tmp_path = os.path.join(os.getcwd(), f"_autogen_{cache_key.__hash__() & 0xffffffff}.pdf")
            generate_pdf(result, filename=_tmp_path, vendor_name=clean_name)
            with open(_tmp_path, "rb") as f:
                pdf_bytes = f.read()
            os.remove(_tmp_path)
            # bytes don't survive JSON encoding, so store them base64'd
            # inside the same cache entry rather than adding a separate
            # bytes-store primitive just for this one field.
            cache_entry["pdf_bytes_b64"] = base64.b64encode(pdf_bytes).decode("ascii")
            # Secondary index so _find_cached_pdf below can look this up by
            # (vendor_name, query_date) in O(1) instead of scanning every
            # cache entry - the latter only worked at all because the old
            # in-memory dict was iterable; Redis has no efficient equivalent
            # at scale, so an explicit index replaces the scan for both
            # backends rather than only fixing it for one.
            if result.get("vendor_name") and result.get("query_date"):
                KV_STORE.set_json(
                    f"pdf_index:{result['vendor_name']}:{result['query_date']}",
                    {"cache_key": cache_key},
                    ttl_seconds=config.CACHE_TTL_SECONDS,
                )
        except Exception as e:
            _safe_print(f"[!] Auto-PDF generation failed for {clean_name}: {e}")

    KV_STORE.set_json(cache_storage_key, cache_entry, ttl_seconds=config.CACHE_TTL_SECONDS)
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
def analyze_vendor(req: AnalyzeRequest, request: Request):
    if not req.vendor or not req.vendor.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")

    _check_rate_limit(request.client.host if request.client else "unknown")

    try:
        return _run_analysis(req)
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
        requests.post(callback_url, json=job, timeout=10)
    except Exception as e:
        _safe_print(f"[!] Job {job['job_id']}: callback to {callback_url} failed: {e}")


def _execute_job(job_id: str, req: AnalyzeRequest, cache_key: str, job: dict):
    job_key = f"job:{job_id}"
    job["status"] = "running"
    job["started_at"] = _now_iso()
    KV_STORE.set_json(job_key, job, ttl_seconds=config.JOB_RETENTION_SECONDS)

    try:
        result = _run_analysis(req)
        job["status"] = "complete"
        job["result"] = result
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        job["completed_at"] = _now_iso()
        KV_STORE.set_json(job_key, job, ttl_seconds=config.JOB_RETENTION_SECONDS)
        KV_STORE.delete(f"inflight:{cache_key}")
        if req.callback_url:
            _send_webhook(req.callback_url, job)


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
    cache_key = _cache_key_for(req, clean_name)
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
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    KV_STORE.set_json(f"job:{job_id}", job, ttl_seconds=config.JOB_RETENTION_SECONDS)

    threading.Thread(target=_execute_job, args=(job_id, req, cache_key, job), daemon=True).start()

    return JobSubmitResponse(job_id=job_id, status="pending", poll_url=f"/api/jobs/{job_id}")


@app.get(
    "/api/jobs/{job_id}", dependencies=[Depends(require_api_key)], response_model=JobRecord, tags=["Jobs"],
    summary="Poll a job's status/result", responses={404: {"description": "Unknown or expired job_id."}},
)
def get_job(job_id: str):
    job = KV_STORE.get_json(f"job:{job_id}")
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id.")
    return job


def _find_cached_pdf(result: dict):
    """Match an incoming /api/download-pdf result back to an analysis cache
    entry by (vendor_name, query_date) to reuse an eagerly-generated PDF
    instead of re-rendering one that already exists. Looks up the
    pdf_index:{vendor_name}:{query_date} entry _run_analysis writes rather
    than scanning every cache entry - the old scan only worked because the
    in-memory dict was iterable; Redis has no efficient equivalent to that
    at scale, so this index replaces the scan for both backends."""
    vendor_name = result.get("vendor_name")
    query_date = result.get("query_date")
    if not vendor_name or not query_date:
        return None
    idx = KV_STORE.get_json(f"pdf_index:{vendor_name}:{query_date}")
    if not idx:
        return None
    entry = KV_STORE.get_json(f"analysis:{idx['cache_key']}")
    if not entry or "pdf_bytes_b64" not in entry:
        return None
    return base64.b64decode(entry["pdf_bytes_b64"])


@app.post(
    "/api/download-pdf", dependencies=[Depends(require_api_key)], tags=["Reports"],
    summary="Generate/download the SK-VDD-001 PDF report",
    description="Reuses an eagerly-generated PDF from cache when the given result came from a recent "
                 "/api/analyze or /api/jobs call with AUTO_GENERATE_PDF_REPORT enabled; otherwise renders "
                 "on demand. Response is the raw PDF (application/pdf), not JSON.",
    response_class=Response,
)
def download_pdf(req: PdfRequest):
    try:
        vendor_name = req.vendor_name or req.result.get("vendor_name", "vendor")
        clean_filename = f"DRiskify_SK_VDD_001_{vendor_name.lower().replace(' ', '_')}.pdf"

        pdf_bytes = _find_cached_pdf(req.result)
        if pdf_bytes is None:
            temp_pdf_path = os.path.join(os.getcwd(), clean_filename)
            generate_pdf(req.result, filename=temp_pdf_path, vendor_name=vendor_name)
            with open(temp_pdf_path, "rb") as f:
                pdf_bytes = f.read()
            if os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path)
                except Exception:
                    pass

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{clean_filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF compilation failed: {e}")


# Serve frontend static build if present
dist_path = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting DRiskify NIVETA REST API on http://localhost:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
