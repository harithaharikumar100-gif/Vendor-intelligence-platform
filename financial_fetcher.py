"""
financial_fetcher.py - Resilient Corporate Financial & Profile Intelligence
--------------------------------------------------------------------------
Features:
- Windows cp1252 safe logging (no raw emojis in stdout)
- Unicode/international name validation (Tobias Lütke, François, etc.)
- Multi-source profile extraction:
  * yfinance ticker info & officer list
  * Wikipedia infobox & Google Serper Knowledge
  * Direct company /about page scraping
  * Dual Groq snippet & factual knowledge extraction fallback
- Comprehensive financial metrics extraction (Revenue, Profit, Margins, D/E, ROCE, Current Ratio, Market Cap)
"""

import os
import re
import requests
import ssl
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

# ─── SSL Adapter ─────────────────────────────────────────────────────────────
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT')
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")


def _safe_print(msg: str):
    """Safely print messages preventing cp1252 Windows crashes."""
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


# ─── low-level helpers ────────────────────────────────────────────────────────

def _serper(query: str, num: int = 5) -> list:
    if not SERPER_API_KEY:
        return []
    try:
        session = requests.Session()
        session.mount('https://', SSLAdapter())
        r = session.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=12,
        )
        return r.json().get("organic", [])
    except Exception as e:
        _safe_print(f"  [!] Serper [{query[:40]}]: {e}")
        return []


def _webpage(url: str, chars: int = 8000) -> str:
    """Fetch a webpage via Serper's /webpage endpoint or direct requests."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    if SERPER_API_KEY:
        try:
            session = requests.Session()
            session.mount('https://', SSLAdapter())
            r = session.post(
                "https://google.serper.dev/webpage",
                json={"url": url},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=15,
            )
            d = r.json()
            txt = d.get("text") or d.get("content") or ""
            if txt:
                return txt[:chars]
        except Exception as e:
            _safe_print(f"  [!] webpage serper [{url[:50]}]: {e}")

    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return r.text[:chars]
    except Exception:
        return ""


def _fmt(v, kind="money"):
    if v is None:
        return None
    try:
        f = float(v)
        if kind == "money":
            if abs(f) >= 1_000_000_000: return f"${f/1_000_000_000:.2f}B"
            if abs(f) >= 1_000_000:     return f"${f/1_000_000:.2f}M"
            return f"${f:,.0f}"
        if kind == "pct": return f"{f*100:.2f}%"
        if kind == "x":   return f"{f:.2f}x"
        if kind == "f":   return f"{f:.2f}"
        return str(f)
    except Exception:
        return None


def _groq(prompt: str, max_tokens: int = 150) -> str:
    """Call Groq with a short prompt using resilient multi-tier fallback ladder."""
    try:
        from ai_engine import _groq as _ai_groq
        return _ai_groq(prompt, max_tokens=max_tokens).strip()
    except Exception as e:
        _safe_print(f"  [!] Groq fallback: {e}")
        return ""


# ─── Ticker Search ────────────────────────────────────────────────────────────

KNOWN_TICKERS = {
    "shopify": "SHOP.TO",
    "blackberry": "BB.TO",
    "cgi": "GIB-A.TO",
    "opentext": "OTEX.TO",
    "royal bank of canada": "RY.TO",
    "rbc": "RY.TO",
    "td bank": "TD.TO",
    "bank of montreal": "BMO.TO",
    "bmo": "BMO.TO",
    "scotiabank": "BNS.TO",
    "constellation software": "CSU.TO",
    "thomson reuters": "TRI.TO",
    "bombardier": "BBD-B.TO",
    "air canada": "AC.TO",
    "bell canada": "BCE.TO",
    "telus": "T.TO",
    "rogers": "RCI-B.TO",
    "canadian pacific kansas city": "CP.TO",
    "enbridge": "ENB.TO",
    "canadian natural resources": "CNQ.TO",
    "suncor": "SU.TO",
    "couche-tard": "ATD.TO",
    "magna international": "MG.TO",
    "waste connections": "WCN.TO",
    "nutrien": "NTR.TO",
    "lululemon": "LULU",
    "microsoft": "MSFT",
    "apple": "AAPL",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "crowdstrike": "CRWD",
    "boeing": "BA",
    "palantir": "PLTR",
    "snowflake": "SNOW",
    "salesforce": "CRM",
}

def _find_ticker(vendor: str, country: str = "Canada") -> str:
    v_clean = re.sub(r'\b(inc|corp|ltd|limited|corporation|llc|co)\b\.?', '', vendor, flags=re.I).strip().lower()
    if v_clean in KNOWN_TICKERS:
        return KNOWN_TICKERS[v_clean]
    for k, t in KNOWN_TICKERS.items():
        if k in v_clean or v_clean in k:
            return t

    q = f'"{vendor}" stock ticker symbol TSX NYSE NASDAQ'
    hits = _serper(q, 3)
    text = " ".join([h.get("title", "") + " " + h.get("snippet", "") for h in hits])
    
    # Check for TSX: XYZ or NYSE: XYZ
    m = re.search(r'\b(?:TSX|TSE):\s*([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b', text)
    if m:
        t = m.group(1).replace(".", "-")
        return f"{t}.TO"
    m = re.search(r'\b(?:NYSE|NASDAQ):\s*([A-Z]{1,5})\b', text)
    if m:
        return m.group(1)
    return ""


# ─── yfinance fetcher ─────────────────────────────────────────────────────────

def _yfinance(ticker: str) -> dict:
    if not ticker:
        return {}
    try:
        import yfinance as yf
        t_obj = yf.Ticker(ticker)
        info = t_obj.info or {}
        if not info or len(info) < 5:
            if not ticker.endswith(".TO") and ("-" not in ticker):
                t_obj = yf.Ticker(f"{ticker}.TO")
                info = t_obj.info or {}

        if not info:
            return {}

        de = _fmt(info.get("debtToEquity"), "f")
        if de:
            de = f"{float(de):.2f}x"

        roce = _fmt(info.get("returnOnEquity"), "pct")

        hq = ""
        city = info.get("city", "")
        country = info.get("country", "")
        state = info.get("state", "")
        if city and country:
            hq = f"{city}, {state + ', ' if state else ''}{country}"
        elif city:
            hq = city

        employees = ""
        emp_raw = info.get("fullTimeEmployees")
        if emp_raw:
            try:
                emp_int = int(emp_raw)
                if 1 <= emp_int <= 5_000_000:
                    employees = f"{emp_int:,}"
            except Exception:
                pass

        ceo = ""
        try:
            officers = info.get("companyOfficers", []) or info.get("officers", [])
            for off in officers:
                title = str(off.get("title", "")).lower()
                name = str(off.get("name", "")).strip()
                if any(k in title for k in ["ceo", "chief executive", "managing director", "president"]) and not ceo:
                    ceo = name
                    break
        except Exception:
            pass

        out = {
            "ticker": ticker.upper(),
            "revenue": _fmt(info.get("totalRevenue") or info.get("revenue")),
            "net_income": _fmt(info.get("netIncomeToCommon")),
            "eps": _fmt(info.get("trailingEps"), "f"),
            "pe_ratio": _fmt(info.get("trailingPE"), "f"),
            "debt_equity": de,
            "net_margin": _fmt(info.get("profitMargins"), "pct"),
            "operating_margin": _fmt(info.get("operatingMargins"), "pct"),
            "roce": roce,
            "revenue_growth": _fmt(info.get("revenueGrowth"), "pct"),
            "current_ratio": _fmt(info.get("currentRatio"), "f"),
            "market_cap": _fmt(info.get("marketCap")),
            "employees": employees,
            "headquarters": hq,
            "ceo": ceo,
            "source": "yfinance",
        }
        return {k: v for k, v in out.items() if v}
    except Exception as e:
        _safe_print(f"  [!] yfinance [{ticker}]: {e}")
        return {}


# ─── Name Validation Helpers ──────────────────────────────────────────────────

BAD_TOKENS = {
    "ceo","chief","executive","officer","founder","co-founder","chairman",
    "president","director","md","managing","vice","svp","evp","coo","cfo",
    "cto","cpo","head","partner","principal","ltd","inc","corp","pvt","llc",
    "group","company","limited","plc","technologies","solutions","services",
    "systems","ventures","holdings","not","available","unknown","n/a","none",
}

def _is_valid_name(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    if len(s) < 4 or len(s) > 60:
        return False
    parts = s.split()
    if len(parts) < 2 or len(parts) > 5:
        return False

    for p in parts:
        clean_p = p.lower().strip(".,;:\"'()")
        if clean_p in BAD_TOKENS:
            return False

    # Check for reasonable alphabetic structure supporting international unicode characters
    alpha_chars = sum(1 for c in s if c.isalpha())
    if alpha_chars < 4:
        return False

    return True


# ─── CEO Fetcher ─────────────────────────────────────────────────────────────

def _fetch_ceo(vendor: str, company_url: str = "") -> str:
    # 1. Wikipedia Direct
    wiki_url = f"https://en.wikipedia.org/wiki/{vendor.replace(' ', '_')}"
    wiki_page = _webpage(wiki_url, 5000)
    if wiki_page:
        for pat in [
            r'\|\s*key_people\s*=\s*(?:\{\{ubl\|)?([^\n\|\}]+)',
            r'\|\s*chief_executive\s*=\s*([^\n\|\}]+)',
            r'(?:CEO|Chief Executive Officer)\s*[:=]\s*([A-Z][^\n,\(\)<]+)',
        ]:
            m = re.search(pat, wiki_page)
            if m:
                cand = re.sub(r'\[\[|\]\]|\{\{|\}\}|<[^>]+>', '', m.group(1)).strip()
                cand = cand.split("(")[0].split(",")[0].strip()
                if _is_valid_name(cand):
                    return cand

    # 2. Serper Search
    q = f'"{vendor}" CEO current Chief Executive Officer'
    hits = _serper(q, 4)
    snippets = " ".join([h.get("title", "") + " " + h.get("snippet", "") for h in hits])
    
    # 3. Groq Snippet & Factual Knowledge Extraction
    prompt = (
        f"Who is the current CEO of {vendor}?\n"
        f"EVIDENCE: {snippets[:1500]}\n"
        f"Return ONLY the person's full name (e.g. 'Tobias Lütke' or 'David McKay'). "
        f"If completely unknown, return 'Not Available'."
    )
    res = _groq(prompt, max_tokens=25)
    if res and "not available" not in res.lower() and _is_valid_name(res):
        return res

    return ""


# ─── Corporate Profile Scraper ───────────────────────────────────────────────

def _scrape_profile(vendor: str, country: str = "Canada", company_url: str = "") -> dict:
    p = {}
    combined = ""
    urls = []

    # 1. Wikipedia
    wiki_url = f"https://en.wikipedia.org/wiki/{vendor.replace(' ', '_')}"
    wiki_page = _webpage(wiki_url, 6000)
    if wiki_page and vendor.lower().split()[0] in wiki_page.lower()[:800]:
        combined += "\n" + wiki_page

    # 2. Serper Corporate Intelligence
    q_list = [
        f'"{vendor}" founded headquarters employees founder CEO overview',
        f'"{vendor}" site:en.wikipedia.org',
    ]
    for q in q_list:
        for r in _serper(q, 4):
            combined += f" {r.get('title','')} {r.get('snippet','')}"
            urls.append(r.get("link", ""))

    tl = combined.lower()

    # Founded year regex
    m = re.search(r'(?:founded|established|incorporated)[^\d]*((?:18|19|20)\d{2})', tl)
    if m:
        p["founded"] = m.group(1)

    # Founder regex
    m = re.search(r'(?:founded by|co-founded by|founders?:)[^\w\n]*([A-Z][a-zA-Z\u00C0-\u024F\.\-]{1,25}(?: [A-Z][a-zA-Z\u00C0-\u024F\.\-]{1,25}){1,3})', combined)
    if m and _is_valid_name(m.group(1)):
        p["founder"] = m.group(1).strip()

    # Headquarters regex
    m = re.search(r'(?:headquartered in|headquarters[:\s]+|based in)\s+([A-Za-z\s,\.\-]+?)(?:\.|\n|;|<)', combined)
    if m:
        hq_val = m.group(1).strip()
        if 3 < len(hq_val) < 60 and not any(k in hq_val.lower() for k in ["http", "www", "overview", "history"]):
            p["headquarters"] = hq_val

    # Employees regex
    m = re.search(r'\b(\d{1,3}(?:,\d{3})+|\d{2,6})\s+(?:employees|people|workforce|staff)\b', tl)
    if m:
        p["employees"] = m.group(1)

    # 3. Groq Dual Knowledge + Context Synthesis
    missing = [f for f in ("founded", "founder", "headquarters", "employees", "ceo") if f not in p]
    if missing:
        ask = ", ".join(missing)
        prompt = (
            f"Provide authoritative corporate facts for '{vendor}' ({country}): {ask}.\n"
            f"Use the context below if helpful, or your verified knowledge base.\n"
            f"Return ONLY a JSON object with string values:\n"
            f'{{"founded": "<4-digit year>", "founder": "<Name>", "headquarters": "<City, Country>", "employees": "<Number>", "ceo": "<Name>"}}\n'
            f"Use null if unknown.\n\n"
            f"CONTEXT:\n{combined[:2000]}"
        )
        answer = _groq(prompt, max_tokens=160)
        if answer:
            import json as _json
            clean_json = re.sub(r"^```(?:json)?|```$", "", answer.strip(), flags=re.MULTILINE).strip()
            try:
                data = _json.loads(clean_json)
                for field in missing:
                    val = data.get(field)
                    if val and str(val).lower() not in ("null", "none", "n/a", "unknown", "not available", ""):
                        if field in ("founder", "ceo") and not _is_valid_name(str(val)):
                            continue
                        p[field] = str(val)
            except Exception:
                pass

    return p


# ─── Public API ──────────────────────────────────────────────────────────────

def fetch_financial_and_profile(
    vendor: str,
    country: str = "Canada",
    ticker: str = "",
    web_snippets: str = "",
    company_url: str = "",
) -> tuple[dict, dict]:
    """
    Fetches comprehensive financial metrics and authoritative corporate profile details.
    """
    _safe_print(f"  [+] Ingesting Corporate Profile & Financials: {vendor} ({country})")

    financial_metrics = {}
    profile_extras = {}

    cu = company_url.strip()
    if cu and not cu.startswith("http"):
        cu = "https://" + cu

    # Parallel retrieval
    with ThreadPoolExecutor(max_workers=3) as ex:
        ticker_future = ex.submit(_find_ticker, vendor, country) if not ticker.strip() else None
        profile_future = ex.submit(_scrape_profile, vendor, country, cu)
        ceo_future = ex.submit(_fetch_ceo, vendor, cu)

        resolved_ticker = ticker.strip() or (ticker_future.result() if ticker_future else "")
        prof = profile_future.result()
        ceo_from_web = ceo_future.result()

    profile_extras.update(prof)
    if ceo_from_web:
        profile_extras["ceo"] = ceo_from_web

    # Pull yfinance for public companies
    if resolved_ticker:
        yf_data = _yfinance(resolved_ticker)
        for k in ("revenue", "net_income", "eps", "pe_ratio", "debt_equity",
                  "net_margin", "operating_margin", "roce", "revenue_growth",
                  "current_ratio", "market_cap", "ticker"):
            if yf_data.get(k):
                financial_metrics[k] = yf_data[k]

        # Use yfinance profile if missing from web
        for pk in ("employees", "headquarters", "ceo"):
            if yf_data.get(pk) and (pk not in profile_extras or not profile_extras[pk]):
                profile_extras[pk] = yf_data[pk]

    _safe_print(f"  [+] Ingested Profile: {profile_extras}")
    _safe_print(f"  [+] Ingested Financial Metrics: {list(financial_metrics.keys())}")

    return financial_metrics, profile_extras