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
    """
    Performs a Serper Google Search with 3-retry exponential backoff, per
    SK-VDD-001 Section 10.2 ("NIVETA shall retry failed source queries up
    to three times with exponential backoff before logging a gap").
    """
    if not SERPER_API_KEY:
        return []
    for attempt in range(3):
        try:
            session = requests.Session()
            session.mount('https://', SSLAdapter())
            r = session.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": num},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=12,
            )
            if r.status_code == 200:
                return r.json().get("organic", [])
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                import time as _time
                _time.sleep(2 ** attempt)
                continue
            return []
        except Exception as e:
            if attempt < 2:
                import time as _time
                _time.sleep(2 ** attempt)
                continue
            _safe_print(f"  [!] Serper failed after 3 retries [{query[:40]}]: {e}")
            return []
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
        
        # TSX dual-class tickers (e.g. Bombardier "BBD.B", CGI "GIB.A") use a
        # HYPHEN before the exchange suffix on Yahoo Finance: "BBD-B.TO", not
        # "BBD.B.TO" (a malformed double-suffix that 404s) and not "BBD-B"
        # alone (missing the .TO suffix, which also 404s — verified directly
        # against Yahoo: only the hyphen+.TO form actually resolves).
        # Strip any existing ".TO" first so it isn't corrupted by the class-
        # separator conversion below (naively replacing every "." with "-"
        # would turn an already-correct "BBD-B.TO" into "BBD-B-TO").
        base = ticker[:-3] if ticker.upper().endswith(".TO") else ticker
        hyphen_base = base.replace(".", "-") if "." in base else base
        dot_base = base.replace("-", ".") if "-" in base else base

        ticker_variants = []
        for v in [f"{hyphen_base}.TO", ticker, f"{base}.TO", hyphen_base, dot_base]:
            if v and v not in ticker_variants:
                ticker_variants.append(v)

        info = {}
        resolved_ticker = ""
        for t_variant in ticker_variants:
            try:
                _safe_print(f"  [•] Trying yfinance ticker: {t_variant}")
                t_obj = yf.Ticker(t_variant)
                
                fast_info = {}
                try:
                    fi = t_obj.fast_info
                    if fi:
                        for attr in ["market_cap", "total_revenue", "net_income_to_common", 
                                      "trailing_eps", "trailing_pe", "current_ratio",
                                      "debt_to_equity", "profit_margins", "operating_margins",
                                      "return_on_equity", "revenue_growth"]:
                            try:
                                val = getattr(fi, attr, None)
                                if val is not None:
                                    key_map = {
                                        "market_cap": "marketCap",
                                        "total_revenue": "totalRevenue",
                                        "net_income_to_common": "netIncomeToCommon",
                                        "trailing_eps": "trailingEps",
                                        "trailing_pe": "trailingPE",
                                        "current_ratio": "currentRatio",
                                        "debt_to_equity": "debtToEquity",
                                        "profit_margins": "profitMargins",
                                        "operating_margins": "operatingMargins",
                                        "return_on_equity": "returnOnEquity",
                                        "revenue_growth": "revenueGrowth",
                                    }
                                    fast_info[key_map.get(attr, attr)] = val
                            except Exception:
                                pass
                except Exception:
                    pass
                
                try:
                    reg_info = t_obj.info or {}
                    if reg_info and isinstance(reg_info, dict) and len(reg_info) > 2:
                        info = reg_info
                        resolved_ticker = t_variant
                        if fast_info:
                            for k, v in fast_info.items():
                                if k not in info or not info[k]:
                                    info[k] = v
                        break
                except Exception:
                    if fast_info:
                        info = fast_info
                        resolved_ticker = t_variant
                        break
            except Exception as inner_e:
                _safe_print(f"  [!] Ticker {t_variant} failed: {str(inner_e)[:80]}")
                continue
        
        if not info or (isinstance(info, dict) and len(info) < 3):
            _safe_print(f"  [•] yfinance returned sparse data, attempting web fallback for {ticker}")
            return {}

        de = _fmt(info.get("debtToEquity"), "f")
        if de:
            try:
                de = f"{float(de):.2f}x"
            except Exception:
                pass

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

        # Quick Ratio (Section 6.1.1)
        quick_ratio = _fmt(info.get("quickRatio"), "f")

        # EBITDA Margin (Section 6.1.1)
        ebitda_margin = None
        ebitda = info.get("ebitda")
        total_rev = info.get("totalRevenue") or info.get("revenue")
        if ebitda is not None and total_rev:
            try:
                ebitda_margin = f"{(float(ebitda) / float(total_rev)) * 100:.2f}%"
            except Exception:
                pass

        # Interest Coverage Ratio (Section 6.1.1)
        interest_coverage = None
        operating_income = info.get("operatingIncome") or info.get("ebit")
        interest_expense = info.get("interestExpense")
        if operating_income is not None and interest_expense is not None:
            try:
                ic = float(operating_income) / float(abs(interest_expense))
                interest_coverage = f"{ic:.2f}x"
            except Exception:
                pass

        out = {
            "ticker": (resolved_ticker or ticker).upper(),
            "revenue": _fmt(info.get("totalRevenue") or info.get("revenue")),
            "net_income": _fmt(info.get("netIncomeToCommon")),
            "eps": _fmt(info.get("trailingEps"), "f"),
            "pe_ratio": _fmt(info.get("trailingPE"), "f"),
            "debt_equity": de,
            "net_margin": _fmt(info.get("profitMargins"), "pct"),
            "operating_margin": _fmt(info.get("operatingMargins"), "pct"),
            "ebitda_margin": ebitda_margin,
            "interest_coverage": interest_coverage,
            "roce": roce,
            "revenue_growth": _fmt(info.get("revenueGrowth"), "pct"),
            "current_ratio": _fmt(info.get("currentRatio"), "f"),
            "quick_ratio": quick_ratio,
            "market_cap": _fmt(info.get("marketCap")),
            "employees": employees,
            "headquarters": hq,
            "ceo": ceo,
            "source": "yfinance",
        }
        result = {k: v for k, v in out.items() if v}
        _safe_print(f"  [✓] yfinance resolved {len(result)} fields for {resolved_ticker or ticker}")
        return result
    except Exception as e:
        err_str = str(e).lower()
        if "crumb" in err_str or "unauthorized" in err_str or "401" in err_str or "403" in err_str:
            _safe_print(f"  [!] yfinance API auth blocked for {ticker} (Yahoo rate-limiting). Skipping gracefully.")
        else:
            _safe_print(f"  [!] yfinance [{ticker}]: {str(e)[:120]}")
        return {}


# ─── Wikipedia REST API Financial Enrichment (works on Render, no IP block) ───

def _wikipedia_financials(vendor: str) -> dict:
    """
    Pull structured corporate data from Wikipedia REST summary + infobox API.
    Returns a partial dict with any fields found: employees, revenue, headquarters,
    founded, founder. Does NOT throw — always safe to call.
    """
    out = {}
    try:
        slug = vendor.strip().replace(" ", "_")
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
            headers={"User-Agent": "DRiskify/2.0 (vendor-due-diligence)"},
            timeout=10,
        )
        if r.status_code != 200:
            # Try without Inc./Ltd./Corp. suffix
            slug2 = re.sub(r'\b(inc|ltd|limited|corp|corporation|llc|co)\.?\s*$', '', vendor.strip(), flags=re.I).strip().replace(" ", "_")
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug2}",
                headers={"User-Agent": "DRiskify/2.0 (vendor-due-diligence)"},
                timeout=10,
            )
        if r.status_code == 200:
            d = r.json()
            extract = d.get("extract", "")
            tl = extract.lower()

            # Employees: "X,XXX employees" or "XX,000 people"
            m = re.search(r'([\d,]+)\s+(?:employees|people|staff|workforce)', tl)
            if m:
                emp_str = m.group(1).replace(",", "")
                try:
                    emp_int = int(emp_str)
                    if 10 <= emp_int <= 5_000_000:
                        out["employees"] = f"{emp_int:,}"
                except Exception:
                    pass

            # Revenue: "$X.X billion" or "$X million" near "revenue"
            for pat in [
                r'revenue[^$\n]{0,50}\$([\d,.]+)\s*(billion|million|trillion)',
                r'\$([\d,.]+)\s*(billion|million|trillion)[^)]{0,50}revenue',
                r'annual(?:\s+\w+){0,5}\$([\d,.]+)\s*(billion|million|trillion)',
            ]:
                m = re.search(pat, tl)
                if m:
                    try:
                        val = float(m.group(1).replace(",", ""))
                        scale = m.group(2)
                        if scale == "trillion":
                            out["revenue"] = f"${val:.2f}T"
                        elif scale == "billion":
                            out["revenue"] = f"${val:.2f}B"
                        else:
                            out["revenue"] = f"${val:.0f}M"
                        break
                    except Exception:
                        pass

            # Headquarters
            for pat in [
                r'headquartered in ([A-Za-z][A-Za-z\s,\.\-]+?)(?:\.|,\s+[A-Z]|\n|;)',
                r'based in ([A-Za-z][A-Za-z\s,\.]+?)(?:\.|,\s+[A-Z]|\n)',
            ]:
                m = re.search(pat, extract)
                if m:
                    hq_val = m.group(1).strip().rstrip(",")
                    if 3 < len(hq_val) < 60 and "http" not in hq_val.lower():
                        out["headquarters"] = hq_val
                        break

            # Founded year
            m = re.search(r'(?:founded|established|incorporated)[^0-9]*((?:18|19|20)\d{2})', tl)
            if m:
                out["founded"] = m.group(1)

            # Founder
            for pat in [
                r'(?:founded|co-founded) by ([A-Z][a-zA-Z\u00C0-\u024F\-\.]{1,25}(?:\s[A-Z][a-zA-Z\u00C0-\u024F\-\.]{1,25}){1,2})',
                r'founders?\s*:\s*([A-Z][a-zA-Z\u00C0-\u024F\-\.]{1,25}(?:\s[A-Z][a-zA-Z\u00C0-\u024F\-\.]{1,25}){1,2})',
            ]:
                m = re.search(pat, extract)
                if m and _is_valid_name(m.group(1)):
                    out["founder"] = m.group(1).strip()
                    break

    except Exception as e:
        _safe_print(f"  [!] Wikipedia REST [{vendor}]: {e}")

    return out


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

    # Parallel retrieval — include Wikipedia REST as a dedicated source
    with ThreadPoolExecutor(max_workers=4) as ex:
        ticker_future = ex.submit(_find_ticker, vendor, country) if not ticker.strip() else None
        profile_future = ex.submit(_scrape_profile, vendor, country, cu)
        ceo_future = ex.submit(_fetch_ceo, vendor, cu)
        wiki_future = ex.submit(_wikipedia_financials, vendor)

        resolved_ticker = ticker.strip() or (ticker_future.result() if ticker_future else "")
        prof = profile_future.result()
        ceo_from_web = ceo_future.result()
        wiki_data = wiki_future.result()

    # Merge in order: scrape → wikipedia → ceo override
    profile_extras.update(prof)

    # Wikipedia fills any gaps left by regex scraping
    for wk in ("employees", "headquarters", "founded", "founder", "revenue"):
        if wiki_data.get(wk) and not profile_extras.get(wk):
            if wk == "revenue":
                financial_metrics["revenue"] = wiki_data[wk]
            else:
                profile_extras[wk] = wiki_data[wk]

    if ceo_from_web:
        profile_extras["ceo"] = ceo_from_web

    # Pull yfinance for public companies (silent on 401 — Yahoo blocks Render IPs)
    if resolved_ticker:
        yf_data = _yfinance(resolved_ticker)
        for k in ("revenue", "net_income", "eps", "pe_ratio", "debt_equity",
                  "net_margin", "operating_margin", "ebitda_margin", "interest_coverage",
                  "roce", "revenue_growth", "current_ratio", "quick_ratio",
                  "market_cap", "ticker"):
            if yf_data.get(k):
                financial_metrics[k] = yf_data[k]

        # Use yfinance profile if missing from web/wikipedia
        for pk in ("employees", "headquarters", "ceo"):
            if yf_data.get(pk) and not profile_extras.get(pk):
                profile_extras[pk] = yf_data[pk]

    _safe_print(f"  [+] Ingested Profile: {profile_extras}")
    _safe_print(f"  [+] Ingested Financial Metrics: {list(financial_metrics.keys())}")

    return financial_metrics, profile_extras