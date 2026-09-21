"""
server.py - DRiskify (NIVETA Platform) REST API Server
------------------------------------------------------
Serves endpoints for:
- POST /api/analyze: Runs SK-VDD-001 Due Diligence Pipeline
- POST /api/download-pdf: Generates and streams official SK-VDD-001 PDF report
- GET  /api/presets: Returns pre-configured enterprise targets
- GET  /api/health: Status check for AI & Serper APIs
- Serves static production build from frontend/dist (if built)
"""

import os
import io
import json
import time
import threading
from fastapi import FastAPI, HTTPException, Response, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from services import get_vendor_analysis
from normalizer import normalize_vendor_name
from pdf_generator import generate_pdf
import config


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
    description="Skill SK-VDD-001: Vendor Intelligence Scraping for Due Diligence",
    version="1.0.0"
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

# In-memory analysis cache. FastAPI runs sync endpoints in a threadpool, so
# even a single uvicorn worker can hit this dict from multiple threads at
# once — the lock protects against a read/evict/write race, not against
# multi-process deployment (a real DB/cache would be needed for that).
ANALYSIS_CACHE = {}
_CACHE_LOCK = threading.Lock()

# Per-IP sliding-window rate limit on the expensive endpoint (see config.py).
_RATE_LIMIT_HITS: Dict[str, list] = {}
_RATE_LIMIT_LOCK = threading.Lock()


def _check_rate_limit(client_ip: str):
    now = time.time()
    with _RATE_LIMIT_LOCK:
        hits = [t for t in _RATE_LIMIT_HITS.get(client_ip, []) if now - t < config.RATE_LIMIT_WINDOW_SECONDS]
        if len(hits) >= config.RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {config.RATE_LIMIT_MAX_REQUESTS} requests per "
                       f"{config.RATE_LIMIT_WINDOW_SECONDS}s. Try again shortly."
            )
        hits.append(now)
        _RATE_LIMIT_HITS[client_ip] = hits


def require_api_key(x_api_key: str = Header(default="")):
    """No-op when config.API_KEY is unset (default local-dev behavior)."""
    if config.API_KEY and x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")

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
    vendor: str
    # Section 4.1: "NIVETA shall not assume any additional context beyond
    # what is explicitly provided." Defaulting to a specific named industry
    # (the old default was "Technology & SaaS") isn't just cosmetically
    # wrong for a non-tech vendor — it also feeds ai_engine.py's cyber-score
    # heuristic, silently inflating an unrelated company's baseline cyber
    # risk score. Empty here lets services.py/ai_engine.py's existing
    # neutral fallback ("General Commercial Services") actually apply.
    industry: Optional[str] = ""
    country: Optional[str] = "Canada"
    concerns: Optional[str] = ""
    company_url: Optional[str] = ""
    business_number: Optional[str] = ""
    ticker: Optional[str] = ""
    # Section 4.3 Optional Context Parameters
    duns_number: Optional[str] = ""
    naics_code: Optional[str] = ""


class PdfRequest(BaseModel):
    result: Dict[str, Any]
    vendor_name: Optional[str] = "Vendor Entity"


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "serper_configured": bool(os.getenv("SERPER_API_KEY")),
        "skill_id": "SK-VDD-001",
        "platform": "DRiskify - NIVETA"
    }


@app.get("/api/presets")
def get_presets():
    return PRESETS


@app.post("/api/normalize")
def normalize_input(data: Dict[str, str]):
    vendor = data.get("vendor", "")
    return normalize_vendor_name(vendor)


@app.post("/api/analyze", dependencies=[Depends(require_api_key)])
def analyze_vendor(req: AnalyzeRequest, request: Request):
    if not req.vendor or not req.vendor.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")

    _check_rate_limit(request.client.host if request.client else "unknown")

    norm = normalize_vendor_name(req.vendor)
    clean_name = norm["normalized_name"]

    cache_key = f"{clean_name}__{req.country}__{req.industry}__{req.ticker}__{req.company_url}__{req.duns_number}__{req.naics_code}"
    with _CACHE_LOCK:
        cached = ANALYSIS_CACHE.get(cache_key)
        if cached:
            age = time.time() - cached["cached_at"]
            if age < config.CACHE_TTL_SECONDS:
                _safe_print(f"[cache] Returning cached analysis for: {clean_name} (age {int(age)}s)")
                return cached["result"]
            # Section 2.1: periodic / event-triggered reviews require the cache
            # to actually expire, otherwise a new adverse event would never be
            # reflected. Evict and fall through to a fresh run.
            _safe_print(f"[cache] Expired for: {clean_name} (age {int(age)}s >= TTL {config.CACHE_TTL_SECONDS}s) - re-running")
            del ANALYSIS_CACHE[cache_key]

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
        raise HTTPException(status_code=500, detail=result["error"])

    cache_entry = {"result": result, "cached_at": time.time()}

    # Section 11 auto_generate_pdf_report: previously defined but not wired to
    # any behavior. Generating it eagerly here (instead of only on-demand in
    # /api/download-pdf) both honors the flag and means the later download
    # call can serve these bytes straight from cache instead of re-rendering.
    if config.AUTO_GENERATE_PDF_REPORT:
        try:
            _tmp_path = os.path.join(os.getcwd(), f"_autogen_{cache_key.__hash__() & 0xffffffff}.pdf")
            generate_pdf(result, filename=_tmp_path, vendor_name=clean_name)
            with open(_tmp_path, "rb") as f:
                cache_entry["pdf_bytes"] = f.read()
            os.remove(_tmp_path)
        except Exception as e:
            _safe_print(f"[!] Auto-PDF generation failed for {clean_name}: {e}")

    with _CACHE_LOCK:
        ANALYSIS_CACHE[cache_key] = cache_entry
    return result


def _find_cached_pdf(result: dict):
    """Match an incoming /api/download-pdf result back to an analysis cache
    entry by (vendor_name, query_date) to reuse an eagerly-generated PDF
    instead of re-rendering one that already exists."""
    vendor_name = result.get("vendor_name")
    query_date = result.get("query_date")
    if not vendor_name or not query_date:
        return None
    with _CACHE_LOCK:
        for entry in ANALYSIS_CACHE.values():
            cached_result = entry.get("result", {})
            if (cached_result.get("vendor_name") == vendor_name
                    and cached_result.get("query_date") == query_date
                    and entry.get("pdf_bytes")):
                return entry["pdf_bytes"]
    return None


@app.post("/api/download-pdf", dependencies=[Depends(require_api_key)])
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
