"""
config.py - NIVETA Configurable Skill Parameters (SK-VDD-001 Section 11)
-------------------------------------------------------------------------
Centralises every parameter the spec designates as administrator-configurable.
There is no admin console in this codebase, so each parameter is instead
read from an environment variable (with the spec's documented default),
which lets an operator retune the skill without a code change — the same
intent as Section 11, implemented via .env / process environment instead
of a UI.
"""

import os


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# Intelligence horizon in months applied to all source queries. Range 12-60.
LOOKBACK_MONTHS = max(12, min(60, _env_int("LOOKBACK_MONTHS", 36)))

# Overall score at which auto-escalation to Senior Review is triggered. Range 50-90.
CRITICAL_SCORE_THRESHOLD = max(50, min(90, _env_int("CRITICAL_SCORE_THRESHOLD", 75)))

# Overall score triggering enhanced due diligence recommendation. Range 30-74.
HIGH_SCORE_THRESHOLD = max(30, min(74, _env_int("HIGH_SCORE_THRESHOLD", 50)))

# Weight multiplier applied to signals from the most recent 12 months. Range 1.0-3.0.
RECENCY_MULTIPLIER_12M = max(1.0, min(3.0, _env_float("RECENCY_MULTIPLIER_12M", 2.0)))

# Flag output confidence as 'Reduced' for private companies when true.
PRIVATE_CO_CONFIDENCE_FLAG = _env_bool("PRIVATE_CO_CONFIDENCE_FLAG", True)

# Automatically generate the PDF Vendor Intelligence Summary Report.
AUTO_GENERATE_PDF_REPORT = _env_bool("AUTO_GENERATE_PDF_REPORT", True)

# Maximum number of adverse media articles retained in the output. Range 10-200.
MAX_NEWS_ARTICLES_LOGGED = max(10, min(200, _env_int("MAX_NEWS_ARTICLES_LOGGED", 50)))

# Minimum CVSS base score for NVD CVEs to be included as signals. Range 4.0-10.0.
MIN_CVSS_SCORE = max(4.0, min(10.0, _env_float("MIN_CVSS_SCORE", 7.0)))

# BitSight score below which a rating is classified as Elevated risk. Range 300-700.
BITSIGHT_THRESHOLD_ELEVATED = max(300, min(700, _env_int("BITSIGHT_THRESHOLD_ELEVATED", 500)))

# AMP value (CAD) above which a compliance penalty is flagged as material. Range 10000-1000000.
AMP_MATERIALITY_THRESHOLD_CAD = max(10000, min(1_000_000, _env_int("AMP_MATERIALITY_THRESHOLD_CAD", 100000)))

# Not one of the spec's own Section 11 parameters, but required to actually
# satisfy Section 2.1's "periodic due diligence reviews" and "event-triggered
# reviews upon identification of material adverse events" use cases — an
# in-memory cache with no expiry would otherwise serve the same result
# forever, silently missing anything that happened after the first run.
# Default: 1 hour.
CACHE_TTL_SECONDS = max(60, _env_int("CACHE_TTL_SECONDS", 3600))

# ── API hardening (not spec-derived — operational hygiene) ───────────────────

# Comma-separated list of origins allowed to call the API. Defaults to the
# local Vite dev server + same-origin production serving, not "*" — the
# previous wildcard combined with allow_credentials=True was already an
# invalid combination browsers reject, so this is a strict improvement, not
# a behavior change for any request that was actually working before.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000"
    ).split(",") if o.strip()
]

# Optional shared-secret API key. When unset (the default), no auth is
# enforced — preserves today's local-dev behavior. When set, /api/analyze and
# /api/download-pdf require a matching X-API-Key header; /api/health and
# /api/presets stay open.
API_KEY = os.getenv("API_KEY", "").strip()

# Simple per-IP rate limit on /api/analyze — the expensive endpoint that
# burns LLM + search quota per call. Sliding window, in-memory (single
# process only; see the thread-safety note on ANALYSIS_CACHE for why that's
# an acceptable scope for now).
RATE_LIMIT_MAX_REQUESTS = max(1, _env_int("RATE_LIMIT_MAX_REQUESTS", 20))
RATE_LIMIT_WINDOW_SECONDS = max(1, _env_int("RATE_LIMIT_WINDOW_SECONDS", 60))
