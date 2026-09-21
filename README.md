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
│                         #   Guideline, OSFI Guideline E-13) — evidence-based principle checks
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
| Technology & Cyber | 20% | CCCS (`cyber.gc.ca`), CISA KEV, NVD (CVSS ≥ 7.0), HaveIBeenPwned | Confirmed breaches (past 3y), active CVEs, ransomware, BitSight indicators, exposed assets |
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

## Automatic Escalation Triggers (Section 10.1)

The platform automatically flags senior risk review escalations for:

- Overall Vendor Risk Score ≥ 75 (Critical rating)
- Match on OFAC / OSFI / UN / EU sanctions list
- Going-concern opinion in audited statements
- Confirmed data breach within past 12 months
- Active regulatory prohibition or cease-and-desist order

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

## Notes

- PDF reports are generated locally and not committed (see `.gitignore`)
- The SSL adapter in `scraper.py` and `financial_fetcher.py` handles Windows SSL EOF errors
- Data confidence score (20–95%) reflects evidence hit count + whether financial metrics were found
- Search grounding integrity: a quota-exhausted or misconfigured `SERPER_API_KEY` is surfaced explicitly in the API response (`search_grounding.available`) and as the first `data_gaps` entry — it never silently looks identical to "searched and found nothing" (Section 10.2)

## License

Proprietary. Do not distribute without permission.
