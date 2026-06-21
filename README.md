# VendorIQ 🛡️
**AI-powered vendor due diligence and risk scoring platform.**

VendorIQ scores vendors across 5 risk dimensions in parallel — financial, reputation, cyber, compliance, and key person — using live web intelligence, real-time financial data, and an LLM synthesis layer. Results are displayed in a dark-themed Streamlit dashboard and exportable as a PDF report.

---

## Architecture

```
vendoriq/
├── app.py                # Streamlit UI — dashboard, charts, PDF download
├── services.py           # Orchestration — runs scrape + financials in parallel, applies keyword boosts
├── ai_engine.py          # Groq LLM calls — per-category risk prompts + synthesis
├── scraper.py            # Serper-based web scraping — 5 risk categories + company profile
├── financial_fetcher.py  # Financial data — yfinance (listed) + web scrape (private) + CEO extraction
├── charts.py             # Plotly gauges + donut chart
├── pdf_generator.py      # ReportLab PDF with two-pass page numbering
└── .env                  # API keys (not committed)
```

---

## How It Works

1. **Scrape** (`scraper.py`) — fires 12 parallel Serper queries across 5 risk categories + company profile
2. **Financials** (`financial_fetcher.py`) — runs concurrently with scraping:
   - Listed companies → yfinance (revenue, EPS, D/E, ROCE, market cap, etc.)
   - Private/unlisted → web scrape + Groq fallback
   - CEO extraction: company website → Wikipedia → press → Groq
3. **AI Analysis** (`ai_engine.py`) — 5 category prompts + 1 synthesis prompt, all parallelized via `ThreadPoolExecutor`
4. **Keyword Boost** (`services.py`) — bumps scores for confirmed high-signal terms (e.g. "ransomware", "regulatory fine")
5. **Display** (`app.py`) — renders KPI cards, gauges, risk cards with evidence links, and company profile

---

## Risk Categories

| Category | Weight | Focus Areas |
|---|---|---|
| Financial | 25% | Revenue decline, EPS, debt/equity, bankruptcy, layoffs |
| Cyber | 25% | Data breaches, ransomware, exposed databases |
| Reputation | 20% | Lawsuits, scandals, public backlash |
| Compliance | 15% | Regulatory fines, GDPR, sanctions, government investigations |
| Key Person | 15% | CEO/founder exits, leadership instability |

---

## Setup

### 1. Clone
```bash
git clone https://github.com/harithaharikumar100-gif/Vendor-intelligence-platform.git
cd Vendor-intelligence-platform
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create `.env`
```env
GROQ_API_KEY=your_groq_api_key
SERPER_API_KEY=your_serper_api_key
```

### 5. Run
```bash
streamlit run app.py
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| AI Model | Groq — `llama-3.3-70b-versatile` |
| Web Search | Serper API |
| Financial Data | yfinance (listed) / web scrape (private) |
| Charts | Plotly |
| PDF Export | ReportLab (two-pass canvas for page numbering) |
| Parallelism | `concurrent.futures.ThreadPoolExecutor` |

---

## Requirements

```
streamlit
groq
plotly
pandas
reportlab
yfinance
requests
python-dotenv
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Groq API key for LLM inference |
| `SERPER_API_KEY` | ✅ | Serper API key for web search |

---

## Notes

- PDF reports are generated locally and not committed (see `.gitignore`)
- The SSL adapter in `scraper.py` and `financial_fetcher.py` handles Windows SSL EOF errors
- Data confidence score (20–95%) reflects evidence hit count + whether financial metrics were found

---


## License

Proprietary. Do not distribute without permission.
