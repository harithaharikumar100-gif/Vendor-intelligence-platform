# DRiskify 🛡️ (NIVETA Platform)

**AI-Native Vendor Due Diligence & Risk Intelligence Platform (SK-VDD-001)**

DRiskify autonomously scores vendors across 5 risk dimensions in parallel — Financial Viability (30%), Reputational Risk (20%), Key-Person & Governance (20%), Technology & Cyber (20%), and Regulatory Compliance (10%) — using public intelligence from authoritative Canadian and international registries, live balance sheet metrics, and a multi-provider (Gemini → Groq → OpenAI) LLM synthesis layer with a deterministic rule-engine fallback.

## Architecture

```
vendoriq/
├── frontend/             # Modern React 18 + Tailwind CSS + Recharts Web UI
│   ├── src/
│   │   ├── components/   # RadarChart, GaugeMeter, DimensionCard, EscalationBanner
│   │   ├── App.jsx       # Hero search, quick presets, 5-dimension tabs, export
│   │   └── index.css     # Premium minimal dark theme tokens (deep-black canvas, hairline borders, single accent color)
│   ├── package.json
│   └── vite.config.js
├── server.py             # FastAPI REST backend (serves /api and static build)
├── run_platform.py       # Unified platform launcher
├── services.py           # Orchestration — SK-VDD-001 scoring math & 4-tier rating
├── ai_engine.py          # Multi-provider LLM dispatch + Autonomous Rule Engine fallback
├── scraper.py            # Parallel scraping: SEDAR+, CBCA, CBC, Globe & Mail, CCCS, CISA, CanLII
├── registry_lookup.py    # Direct Corporations Canada / provincial registry lookup
├── canlii_search.py      # Direct CanLII (canlii.org) litigation search
├── sedarplus_lookup.py   # Direct SEDAR+ (sedarplus.ca) filing search
├── normalizer.py         # Suffix stripping, acronym expansion & BN validation
├── financial_fetcher.py  # yfinance & public filing ratio extraction
├── cyber_intel.py        # Real NVD CVE + CISA KEV + CCCS advisory feed integrations
├── sanctions_check.py    # Real OFAC SDN sanctions list cross-reference
├── licensed_sources.py   # Licensed-source (BitSight/Refinitiv/etc.) gap disclosure
├── frameworks.py         # Named regulatory framework alignment (OSFI Corporate Governance
│                         #   Guideline, OSFI Guideline E-13, FINTRAC Guidance, OPC Guidelines)
├── store.py              # Swappable job/cache/rate-limit store — in-memory or Redis (REDIS_URL)
├── config.py             # Section 11 configurable skill parameters (env-driven)
├── pdf_generator.py      # Official SK-VDD-001 PDF Summary Report generator
└── .env                  # API keys (GROQ_API_KEY, GEMINI_API_KEY, SERPER_API_KEY)
```

## 5 Risk Dimensions (SK-VDD-001)

| Dimension | Weight | Primary Sources | Focus & Thresholds |
|---|---|---|---|
| Financial Viability | 30% | SEDAR+, CBCA, Provincial Registries, CRA, yfinance | Solvency (D/E > 3.0x), Liquidity (Current Ratio < 1.0), EBITDA trends, Going-concern opinions |
| Reputational Risk | 20% | CBC News, Globe & Mail, Financial Post, Google News, CanLII | Trailing 36m adverse media, 2.0x 12m recency multiplier, Tier-1 Canadian outlets, litigation |
| Key-Person Risk | 20% | SEDI Insiders, LinkedIn, CBCA Registry, OFAC/OSFI Sanctions | Sanctions match, PEP, director disqualifications, single-person dependency, thin bench |
| Technology & Cyber | 20% | CCCS (`cyber.gc.ca`), CISA KEV, NVD (CVSS ≥ 7.0) — free; HaveIBeenPwned & BitSight require a paid key, see Known Limitations | Confirmed breaches (past 3y), active CVEs, ransomware |
| Regulatory Compliance | 10% | OSFI, FINTRAC AMPs, CSA, OPC PIPEDA, CRTC CASL | Enforcement orders, AMP penalties > $100k CAD, cease-trade orders. Active prohibition triggers Critical |

## Named Regulatory Framework Alignment

Beyond the 5 weighted dimensions, the Key-Person/Governance and Compliance dimensions are additionally checked against a specific, named set of supplied regulatory frameworks — rather than open-ended "regulation in general" reasoning:

- **OSFI Corporate Governance Guideline** — board risk oversight, independent risk committee, chair/CEO separation, code of conduct, whistleblower policy, succession planning
- **OSFI Guideline E-13 (Regulatory Compliance Management)** — named compliance function, compliance framework, monitoring/testing, board reporting, remediation process, enforcement history
- **FINTRAC Guidance (AML/ATF Compliance Program)** — compliance officer, written program, risk assessment, training, independent effectiveness review, AMP history
- **OPC Guidelines (PIPEDA Privacy Program)** — accountability, breach notification process, public privacy policy, safeguards, PIPEDA finding history

Each principle resolves to `evidence_found`, `evidence_of_concern`, or `not_disclosed_in_available_sources` (negation-aware keyword matching against the evidence corpus) — absence of evidence is never assumed to pass or fail. Additional named frameworks can be added the same way in `frameworks.py`.

## 4-Tier Rating Bands

| Range | Rating | Meaning |
|---|---|---|
| 0 – 24 | 🟢 Low | No material concerns detected. Standard onboarding may proceed. |
| 25 – 49 | 🟡 Medium | Some risk signals present. Enhanced due diligence recommended. |
| 50 – 74 | 🟠 High | Significant risk signals. Senior review and conditional onboarding. |
| 75 – 100 | 🔴 Critical | Severe risk signals. Escalation required; onboarding suspended. |

## Quick Start

**1. Clone**

```bash
git clone https://github.com/harithaharikumar100-gif/Vendor-intelligence-platform.git
cd Vendor-intelligence-platform
```

**2. Create virtual environment**

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure `.env`**

```env
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
SERPER_API_KEY=your_serper_api_key
```

**5. Launch the Web Platform**

Run the unified launcher:

```bash
python run_platform.py
```

Open `http://localhost:8000` in your browser.

Optional, for a Vite dev server during active UI development:

```bash
cd frontend
npm run dev
```

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/jobs` | **Recommended for integration.** Returns `job_id` immediately (202); the pipeline runs in the background. A duplicate submission (same vendor + params) while one is already pending/running returns the existing `job_id` instead of duplicating work. |
| `GET` | `/api/jobs/{job_id}` | Poll for status/result. 404 once the job's `JOB_RETENTION_SECONDS` window has elapsed. |
| `POST` | `/api/analyze` | Blocking variant of the same pipeline — observed live anywhere from ~90s to 15+ minutes depending on upstream LLM/search latency. Prefer `/api/jobs` for anything embedded or automated. |
| `POST` | `/api/download-pdf` | Streams the SK-VDD-001 PDF report for a given result (reuses an eagerly-generated one when available). |
| `GET` | `/api/health` | Service/config status — which AI providers and state backend are active. |
| `GET` | `/api/presets` | Pre-configured enterprise targets. |
| `POST` | `/api/normalize` | Vendor-name normalization utility (suffix stripping, acronym expansion). |

Authentication is optional and off by default (local-dev convenience). Set `API_KEYS_JSON` (or the
legacy single-key `API_KEY`) to require an `X-API-Key` header, with each key independently
identifiable and independently daily-quota-capped. State (job records, analysis cache, rate-limit
counters) lives in-process by default; set `REDIS_URL` to share it across replicas and survive a
restart — see `store.py`.

## Automatic Escalation Triggers (Section 10.1)

The platform automatically flags senior risk review escalations for:

- Overall Vendor Risk Score ≥ 75 (Critical rating)
- Match on OFAC / OSFI / UN / EU sanctions list
- Going-concern opinion in audited statements
- Confirmed data breach within the configured lookback window
- Active regulatory prohibition or cease-and-desist order
- 2+ named executives showing departure language in evidence (key-person attrition)
- Multiple distinct entities matching the supplied vendor name (disambiguation required)
- Jurisdiction unconfirmed against Corporations Canada / a provincial registry

Each LLM-sourced trigger above (sanctions match, breach, prohibition order, attrition) is backed by
a deterministic check in `ai_engine.py` that only ever clears the flag, never sets it — the model's
own claim isn't enough on its own to fire a client-facing escalation; it must be corroborated by a
specific, severity-tagged, sourced finding in the same response.

## Tech Stack

| Layer | Technology |
|---|---|
| UI | React 18 + Tailwind CSS + Recharts |
| Backend | FastAPI |
| AI Model | Gemini → Groq → OpenAI auto-failover (dynamic model discovery) |
| Web Search | Serper API |
| Financial Data | yfinance (listed) / web scrape (private) |
| Charts | Recharts |
| PDF Export | ReportLab (two-pass canvas for page numbering) |
| Parallelism | `concurrent.futures.ThreadPoolExecutor` |

## Requirements

```
groq
reportlab
yfinance
requests
python-dotenv
fastapi
uvicorn
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Recommended | Google Gemini API key — first in the LLM auto-failover chain |
| `GROQ_API_KEY` | ✅ | Groq API key for LLM inference (fallback if Gemini unavailable) |
| `SERPER_API_KEY` | ✅ | Serper API key for web search grounding |
| `OPENAI_API_KEY` | Optional | Final fallback in the LLM auto-failover chain |
| `REDIS_URL` | Optional | Shared/durable state backend for job records, analysis cache, and rate limits (e.g. `redis://localhost:6379/0`). Unset = in-memory, single-process only. An unreachable Redis logs a warning and falls back to in-memory rather than crashing. |
| `API_KEYS_JSON` | Optional | `{"<key>": {"client": "<name>", "daily_quota": <int or null>}, ...}` — per-client API key auth with independent quotas. Unset = auth disabled. |
| `API_KEY` | Optional | Legacy single shared-secret key, used only if `API_KEYS_JSON` is unset. |
| `JOB_RETENTION_SECONDS` | Optional | How long a completed `/api/jobs` record stays pollable before eviction. Default 3600. |
| `REFINITIV_API_KEY` / `DNB_API_KEY` / `FACTIVA_API_KEY` / `WORLDCHECK_API_KEY` / `BITSIGHT_API_KEY` / `SHODAN_API_KEY` / `HIBP_API_KEY` | Optional, unconfigured by default | Licensed data sources (see Known Limitations). Each one set removes its corresponding entry from the report's data-gaps disclosure and from the confidence-score deduction. |

## Notes

- PDF reports are generated locally and not committed (see `.gitignore`)
- The SSL adapter in `scraper.py` and `financial_fetcher.py` handles Windows SSL EOF errors
- Data confidence score (30–98%) starts from evidence hit count + whether financial metrics were found, then deducts for this run's actual lookup failures (registry/profile/search grounding, capped at -20) and for the count of unconfigured licensed sources (capped at -7) — see `services.compute_confidence_score`
- Search grounding integrity: a quota-exhausted or misconfigured `SERPER_API_KEY` is surfaced explicitly in the API response (`search_grounding.available`) and as the first `data_gaps` entry — it never silently looks identical to "searched and found nothing" (Section 10.2)

## Known Limitations

- **LLM output is inherently non-deterministic.** Every dimension's findings and score come from a model given a strict JSON schema to fill, and it can still deviate — duplicated entries, off-list values, a claim unsupported by its own listed evidence. `ai_engine.py` runs a layer of deterministic backstops after every LLM call (score-vs-evidence clamping, duplicate/authority normalization, and validators that can only ever clear an escalation flag, never set one) that catch every failure pattern observed in testing so far — but a model swap or unusual evidence could still surface a new one. Treat this as substantially mitigated, not eliminated.
- **Response time depends on free-tier AI quota.** A single analysis has been observed taking anywhere from ~90 seconds to 15+ minutes depending on upstream Groq/Gemini rate limits that day. `/api/jobs` exists specifically so a caller doesn't have to hold a connection open for this.
- **Seven licensed data sources are unconfigured by default**: Refinitiv/Bloomberg, Dun & Bradstreet, Factiva/LexisNexis, World-Check, BitSight, Shodan, and HaveIBeenPwned all require a paid key the platform doesn't ship with. Every report discloses exactly which ones are missing and from which dimension (Section 9.2), and the confidence score reflects it — but financial ratings, structured adverse-media sentiment, PEP/sanctions screening, and continuous security-posture scoring are all working from free public alternatives until these are configured.
- **Regulatory framework alignment is narrow by design**: only 4 named frameworks (OSFI Corporate Governance Guideline, OSFI Guideline E-13, FINTRAC Guidance, OPC/PIPEDA Guidelines), covering 2 of the 5 risk dimensions (key-person, compliance). It is explicitly not a comprehensive legal/regulatory audit, and the PDF report states this plainly.
- **Canada-only scope.** A vendor that can't be confirmed as Canadian-registered against Corporations Canada or a provincial registry is flagged out-of-scope rather than analyzed as if it were in scope.
- **In-memory state by default.** Without `REDIS_URL` set, a backend restart drops any in-progress or cached job, and state isn't shared across multiple replicas.
- **Never fully autonomous, by design.** Per Section 9.3, the platform does not approve or reject a vendor — every report ends with a human sign-off section. This is a deliberate constraint given the limitation above, not a missing feature.

## License

Proprietary. Do not distribute without permission.
