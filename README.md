# DRiskify — Vendor Intelligence Platform

Canadian vendor due-diligence evidence collection, provisional risk analysis, and analyst review, developed against the supplied SK-VDD-001 draft.

Assessments cover financial viability (30%), reputation (20%), key persons (20%), technology/cybersecurity (20%), and compliance (10%). A missing or failed check is **not** a clean screening result. Incomplete runs have no final overall score. All scoring remains provisional until the separate CFG-VDD-001 policy is available and approved by the risk owner.

## Development setup

Python 3.12 and Node.js 24 were used for validation. Work in the existing checkout; a separate worktree is not required.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

The backend serves the built frontend. For UI development, run `npm run dev` in `frontend` alongside the backend; Vite proxies `/api` to port 8000.

```bash
.venv/bin/python -m pytest -q
cd frontend
npm run build
```

Configure credentials in environment settings or an ignored local `.env`. Search needs `SERPER_API_KEY`; source-linked model extraction needs at least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENAI_API_KEY`. No credentials are needed for the offline test suite. Without provider access, the application can start and report unavailable evidence, but cannot produce a complete assessment.

## Evidence and scoring

- Web results retain full URLs, excerpts, retrieval timestamps, publication dates and source identifiers. Extraction uses batches of records rather than an 800-character evidence cutoff.
- Model-proposed quotations must occur in a supplied record. Unsubstantiated citations are rejected. An unsupported event date stays unknown and does not enter scoring. A valid citation does not establish that the publisher's claim is true: analyst verification is still required.
- Name matches from OFAC and product/domain matches from cyber feeds are candidates, not confirmed sanctions or compromise. User concerns guide extraction; they are never evidence.
- Registry discovery is separate from verification. A fetched government registry record must match the normalized legal name and an identifying number; a supplied BN must also match. Conflicting records require confirmation.
- Provisional event points are Low 0, Elevated 15, High 35 and Critical 75, capped at 100 per dimension. Recent reputation events use the configured 12-month multiplier; resolved events receive a 0.5 multiplier. Each contribution is exported. Unknown severity, date, identity or provenance cannot contribute.
- Empty findings remain empty. Dimension scores without qualifying evidence are `null`; they do not default to Low. Source availability is shown as successful checks / total checks, not a fabricated probability of correctness.
- Up to three annual periods from available yfinance statements include fiscal dates, six ratios and provenance. Two-year signals require adjacent fiscal periods. Quote and aggregator data do not verify audited statements or auditor opinions.

## Assessment and review workflow

Submit an analysis, monitor its real processing stage, then review the saved run and its evidence. The UI supports an API key held in memory, province/territory input, reassessment, cancellation, resuming a persisted job, a review queue, reviewer notes/history, source health and administrator settings.

Assessment `run_status` may be `out_of_scope`, `paused_source_unavailable`, `awaiting_entity_confirmation`, `insufficient_evidence` or `awaiting_review`. Job execution status is separate: `pending`, `running`, `needs_review`, `complete`, `failed` or `cancelled`. Finishing collection does not approve a vendor.

Reviews are append-only records. `reviewed` records an observation; `approve` is rejected while evidence or policy blockers remain. The current implementation always includes the missing CFG-VDD-001 approval blocker. Importing/approving that policy requires a separately reviewed implementation, not an administrator toggle.

Reports carry a unique run ID. Their content hash and tenant ownership must match the stored run. Reviews do not silently rewrite an exported assessment. Refresh bypasses the assessment cache; individual source caches use their own TTLs and retain retrieval timestamps. Cancellation takes effect at pipeline checkpoints; an external request already in progress may finish first.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Configuration presence and state backend |
| GET | `/api/presets` | Example inputs; no automatic assessment |
| POST | `/api/normalize` | Normalize a vendor name |
| POST | `/api/jobs` | Submit an assessment and receive a poll URL |
| GET | `/api/jobs/{job_id}` | Read an owned job and result |
| POST | `/api/jobs/{job_id}/cancel` | Request cancellation |
| POST | `/api/analyze` | Blocking analysis; jobs are preferred |
| POST | `/api/download-pdf` | Export the exact saved assessment |
| GET | `/api/reviews` | Owned assessment review queue |
| GET | `/api/runs/{run_id}` | Original assessment JSON |
| GET / POST | `/api/runs/{run_id}/reviews` | Read history / record a review |
| GET / PUT | `/api/admin/settings` | Read / save bounded policy parameters |

Administrator parameter changes apply on restart, before job recovery. Existing reports retain their original results. API documentation is served at `/docs`.

## Persistence, access and deployment

| Variable | Behavior |
|---|---|
| `STATE_DB_PATH` | SQLite state path, default `.state/vendor.sqlite3`; use a persistent volume for a single instance. |
| `REDIS_URL` | Optional shared store for jobs, reports, leases and quota counters. Configured Redis failure prevents startup; there is no silent memory fallback. Configure Redis persistence/backups separately. |
| `MAX_CONCURRENT_JOBS` | Bounded async worker count, default 2 per process. |
| `API_KEYS_JSON` | Map keys to `{ "client": "tenant-name", "role": "viewer|reviewer|admin", "daily_quota": 20 }`. Keys with the same client share a tenant's runs. |
| `API_KEY` | Legacy single key; use the JSON configuration for reviewer/admin roles. |
| `ALLOWED_ORIGINS` | Explicit CORS origins. |
| `CALLBACK_ALLOWED_HOSTS` | Exact allowed public HTTPS callback hosts; callbacks disabled when empty. |
| `CACHE_TTL_SECONDS` | Assessment/source cache TTL. |

When no API keys are configured, local development mode permits unauthenticated access, including administration. On Render, review decisions and administrator settings require configured reviewer/admin keys even when the public demo has no authentication. Configure authentication before shared deployment. Quotas are charged for analysis submissions, not polling/reviews/downloads. Without Redis, quota counters are process-local while SQLite preserves assessment state. Use Redis for shared state and quotas across replicas.

Persisted queued/running jobs are recovered on startup and execute under renewable leases. Recovery may repeat external retrieval after a process crash; it is not an exactly-once external task system. Reports, review records and jobs are retained without automatic deletion; define a retention/backup policy for production. `JOB_RETENTION_SECONDS` remains a legacy setting and does not expire audit records.

A Render filesystem without a persistent disk is ephemeral: local SQLite cannot survive machine replacement. Configure a persistent disk or durable Redis before relying on recovery across redeployments. Source fixes in this checkout do not deploy themselves to Render.

## Remaining limits

- **Scoring policy:** CFG-VDD-001 has not been provided/approved. Provisional weights and rules are not a certified policy implementation; no calibrated confidence percentage is claimed.
- **Source access:** there is no licensed-provider access in this environment. BitSight, World-Check, Refinitiv, D&B, Factiva and Shodan metadata do not constitute working connectors; adding a key does not remove their disclosure. HIBP has a request path, but its public breach catalog is not organization-wide email exposure monitoring.
- **Incomplete public coverage:** OFAC is the direct sanctions integration; full Canadian/UN/EU lists, comprehensive PEP/alias/identity resolution, direct CRA tax-status verification and full SEDI coverage remain additional integration work. Unknown coverage is not a clean result.
- **Filing verification:** SEDAR+/CanLII discovery is search-index based. A successful index query is not proof of direct filing retrieval, a verified auditor opinion or complete litigation coverage. Registry parsers may require manual verification when pages are dynamic, gated or change format. Three years of audited financial statements still require document ingestion and review.
- **Human verification:** source-linked extraction can misinterpret a real quotation, and public reports can be inaccurate. Independent analyst review is required, particularly for entity matching, event classification and current legal status. The UI records review decisions; it does not replace a regulated approval process.
- **Additional workflow:** assigned-reviewer routing, external notifications, scheduled reassessments and event subscriptions are not implemented. The saved review queue and source-health view support manual follow-up.
- **Live validation:** offline regression tests and local HTTP/PDF checks do not establish live provider availability or behavior of the deployed Render site. The workspace proxy blocked access to the supplied public demo during the audit.

## Main implementation modules

`analysis_pipeline.py` validates extracted evidence; `evidence.py` handles dates and provisional contributions; `services.py` applies completion gates. `financial_history.py` computes dated annual ratios. `registry_verification.py` distinguishes records from search hits. `server.py`, `job_runner.py`, `store.py` and `review_api.py` implement jobs, saved reports, access and review. `pdf_generator.py` and `frontend/src` display the same saved assessment.

## License

Proprietary. Do not distribute without permission.
