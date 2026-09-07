DRiskify 🛡️ (NIVETA Platform)
AI-Native Vendor Due Diligence & Risk Intelligence Platform (SK-VDD-001)
DRiskify autonomously scores vendors across 5 risk dimensions in parallel — Financial Viability (30%), Reputational Risk (20%), Key-Person & Governance (20%), Technology & Cyber (20%), and Regulatory Compliance (10%) — using public intelligence from authoritative Canadian and international registries, live balance sheet metrics, and a dynamic Groq LLM synthesis layer.
---
Architecture
```
vendoriq/
├── frontend/             # Modern React 18 + Tailwind CSS + Recharts Web UI
│   ├── src/
│   │   ├── components/   # RadarChart, GaugeMeter, DimensionCard, EscalationBanner
│   │   ├── App.jsx       # Hero search, quick presets, 5-dimension tabs, export
│   │   └── index.css     # Glassmorphism & dark-theme tokens
│   ├── package.json
│   └── vite.config.js
├── server.py             # FastAPI REST backend (serves /api and static build)
├── run_platform.py       # Unified platform launcher
├── services.py           # Orchestration — SK-VDD-001 scoring math & 4-tier rating
├── ai_engine.py          # Groq dynamic model discovery + Signal Library synthesis
├── scraper.py            # Parallel scraping: SEDAR+, CBCA, CBC, Globe & Mail, CCCS, CISA, CanLII
├── normalizer.py         # Suffix stripping, acronym expansion & BN validation
├── financial_fetcher.py  # yfinance & public filing ratio extraction
├── charts.py             # Plotly charts (Radar, Gauges, Donut)
├── pdf_generator.py      # Official SK-VDD-001 PDF Summary Report generator
├── app.py                # (Optional) Legacy Streamlit UI
└── .env                  # API keys (GROQ_API_KEY, SERPER_API_KEY)
```
---
5 Risk Dimensions (SK-VDD-001)
Dimension	Weight	Primary Sources	Focus & Thresholds
Financial Viability	30%	SEDAR+, CBCA, Provincial Registries, CRA, yfinance	Solvency ($D/E > 3.0x$), Liquidity (Current Ratio $< 1.0$), EBITDA trends, Going-concern opinions
Reputational Risk	20%	CBC News, Globe & Mail, Financial Post, Google News, CanLII	Trailing 36m adverse media, 2.0x 12m recency multiplier, Tier-1 Canadian outlets, litigation
Key-Person Risk	20%	SEDI Insiders, LinkedIn, CBCA Registry, OFAC/OSFI Sanctions	Sanctions match, PEP, director disqualifications, single-person dependency, thin bench
Technology & Cyber	20%	CCCS (`cyber.gc.ca`), CISA KEV, NVD ($CVSS \ge 7.0$), HaveIBeenPwned	Confirmed breaches (past 3y), active CVEs, ransomware, BitSight indicators, exposed assets
Regulatory Compliance	10%	OSFI, FINTRAC AMPs, CSA, OPC PIPEDA, CRTC CASL	Enforcement orders, AMP penalties $> $100\text{k CAD}$, cease-trade orders. Active prohibition triggers Critical
---
4-Tier Rating Bands
0 – 24: 🟢 Low — No material concerns detected. Standard onboarding may proceed.
25 – 49: 🟡 Medium — Some risk signals present. Enhanced due diligence recommended.
50 – 74: 🟠 High — Significant risk signals. Senior review and conditional onboarding.
75 – 100: 🔴 Critical — Severe risk signals. Escalation required; onboarding suspended.
---
Quick Start
1. Clone
```bash
git clone https://github.com/harithaharikumar100-gif/Vendor-intelligence-platform.git
cd Vendor-intelligence-platform
```
2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```
3. Install dependencies
```bash
pip install -r requirements.txt
```
4. Configure `.env`
```env
GROQ_API_KEY=your_groq_api_key
SERPER_API_KEY=your_serper_api_key
```
5. Launch the Web Platform
Run the unified launcher:
```bash
python run_platform.py
```
Open `http://localhost:8000` in your browser.
(Optional for Vite Dev server during active UI development):
```bash
cd frontend
npm run dev
```
---
Automatic Escalation Triggers (Section 10.1)
The platform automatically flags senior risk review escalations for:
Overall Vendor Risk Score $\ge 75$ (Critical rating)
Match on OFAC / OSFI / UN / EU sanctions list
Going-concern opinion in audited statements
Confirmed data breach within past 12 months
Active regulatory prohibition or cease-and-desist order
---
Tech Stack
Layer	Technology
UI	React 18 + Tailwind CSS + Recharts (primary) · Streamlit (legacy, optional)
Backend	FastAPI
AI Model	Groq — dynamic model discovery (e.g. `openai/gpt-oss-120b`)
Web Search	Serper API
Financial Data	yfinance (listed) / web scrape (private)
Charts	Plotly / Recharts
PDF Export	ReportLab (two-pass canvas for page numbering)
Parallelism	`concurrent.futures.ThreadPoolExecutor`
---
Requirements
```
streamlit
groq
plotly
pandas
reportlab
yfinance
requests
python-dotenv
fastapi
uvicorn
```
---
Environment Variables
Variable	Required	Description
`GROQ_API_KEY`	✅	Groq API key for LLM inference
`SERPER_API_KEY`	✅	Serper API key for web search
---
Notes
PDF reports are generated locally and not committed (see `.gitignore`)
The SSL adapter in `scraper.py` and `financial_fetcher.py` handles Windows SSL EOF errors
Data confidence score (20–95%) reflects evidence hit count + whether financial metrics were found
---
License
Proprietary. Do not distribute without permission.