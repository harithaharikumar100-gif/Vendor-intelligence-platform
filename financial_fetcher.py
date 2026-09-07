"""
financial_fetcher.py  v6  — COMPLETE FILE
-----------------------------------------

- SSL adapter added for Windows SSL EOF error
- Dollar-format revenue/profit patterns added for global firms (e.g. Deloitte, Amazon)
- Employee cap raised to 5,000,000 for large firms
- Added operating_margin, revenue_growth, market_cap scraping
- Groq financial fallback now always runs for private companies with no metrics
- Wikipedia direct fetch added in _scrape_profile
- Headquarters patterns expanded
"""

import os, re, requests, ssl
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

# ─── SSL Adapter (fixes Windows SSL EOF error) ────────────────────────────────
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT')
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")


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
        print(f"  ⚠  Serper [{query[:40]}]: {e}")
        return []


def _webpage(url: str, chars: int = 8000) -> str:
    """Fetch a webpage via Serper's /webpage endpoint."""
    if not SERPER_API_KEY or not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        session = requests.Session()
        session.mount('https://', SSLAdapter())
        r = session.post(
            "https://google.serper.dev/webpage",
            json={"url": url},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=20,
        )
        d = r.json()
        return (d.get("text") or d.get("content") or "")[:chars]
    except Exception as e:
        print(f"  ⚠  webpage [{url[:50]}]: {e}")
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
        print(f"  ⚠  Groq fallback: {e}")
        return ""



# ─── ticker lookup ────────────────────────────────────────────────────────────

def _find_ticker(vendor: str, country: str) -> str:
    queries = [
        f'"{vendor}" NSE BSE ticker symbol stock exchange listed',
        f'"{vendor}" NYSE NASDAQ stock ticker symbol',
    ]
    results_combined = ""
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(_serper, q, 4) for q in queries]
        for fut in futures:
            for r in fut.result():
                results_combined += f" {r.get('title','')} {r.get('snippet','')} {r.get('link','')}"

    text = results_combined.upper()
    m = re.search(r'\b(NSE|BSE):\s*([A-Z0-9]{2,12})\b', text)
    if m:
        suffix = ".NS" if m.group(1) == "NSE" else ".BO"
        t = m.group(2) + suffix
        print(f"  🎯 Ticker: {t}")
        return t
    m2 = re.search(r'\b(NYSE|NASDAQ):\s*([A-Z]{1,6})\b', text)
    if m2:
        t = m2.group(2)
        print(f"  🎯 Ticker: {t}")
        return t
    return ""


# ─── yfinance ─────────────────────────────────────────────────────────────────

def _yfinance(ticker: str) -> dict:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}

        td   = info.get("totalDebt")
        eq   = info.get("stockholdersEquity") or info.get("bookValue")
        ebit = info.get("ebit") or info.get("operatingIncome")
        ta   = info.get("totalAssets")
        cl   = info.get("totalCurrentLiabilities")

        roce = None
        if ebit and ta and cl:
            ce = float(ta) - float(cl)
            if ce > 0:
                roce = _fmt(float(ebit) / ce, "pct")

        de = None
        if td and eq and float(eq) != 0:
            de = _fmt(float(td) / float(eq), "x")

# Broader CEO title matching: catches "CEO & MD", "Group CEO", "Interim CEO" etc.
        ceo = None
        CEO_TITLES = ("chief executive", "ceo", "managing director", "md & ceo", "ceo & md")
        for o in info.get("companyOfficers", []):
            title = (o.get("title") or "").lower().strip()
            if any(t in title for t in CEO_TITLES):
                name = o.get("name", "")
                if _is_valid_name(name):
                    ceo = name
                    break
        hq_parts = [info.get("city",""), info.get("state",""), info.get("country","")]
        hq = ", ".join(p for p in hq_parts if p) or None

        emp_raw = info.get("fullTimeEmployees")
        employees = None
        if emp_raw:
            try:
                emp_int = int(emp_raw)
                if 1 <= emp_int <= 5_000_000:
                    employees = f"{emp_int:,}"
            except Exception:
                pass

        out = {
            "ticker":           ticker.upper(),
            "revenue":          _fmt(info.get("totalRevenue") or info.get("revenue")),
            "net_income":       _fmt(info.get("netIncomeToCommon")),
            "eps":              _fmt(info.get("trailingEps"), "f"),
            "pe_ratio":         _fmt(info.get("trailingPE"),  "f"),
            "debt_equity":      de,
            "net_margin":       _fmt(info.get("profitMargins"),    "pct"),
            "operating_margin": _fmt(info.get("operatingMargins"), "pct"),
            "roce":             roce,
            "revenue_growth":   _fmt(info.get("revenueGrowth"), "pct"),
            "current_ratio":    _fmt(info.get("currentRatio"),  "f"),
            "market_cap":       _fmt(info.get("marketCap")),
            "employees":        employees,
            "headquarters":     hq,
            "ceo":              ceo,
            "source":           "yfinance",
        }
        return {k: v for k, v in out.items() if v}
    except Exception as e:
        print(f"  ⚠  yfinance [{ticker}]: {e}")
        return {}


# ─── CEO helpers ─────────────────────────────────────────────────────────────

BAD_TOKENS = {
    "ceo","chief","executive","officer","founder","co-founder","chairman",
    "president","director","md","managing","vice","svp","evp","coo","cfo",
    "cto","cpo","head","partner","principal",
    "ltd","inc","corp","pvt","llc","group","company","limited","plc",
    "technologies","solutions","services","systems","ventures","holdings",
    "the","and","of","in","at","is","was","by","its","for","with","has",
    "not","available","unknown","n/a","none","new","india","global","international",
    "mr","ms","mrs","dr","sir","prof",
    "report","news","said","says","told","announces","appoints","names","joins",
    "leaves","resigns","steps","down","takes","over","urges","warns","calls",
    "leads","heads","joins","exits","quits","fires","hired","appointed",
}

def _is_valid_name(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    if len(s) < 7 or len(s) > 50:
        return False
    parts = s.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(p[0].isupper() for p in parts if p):
        return False

    # NEW: reject if any part is a known org/company/noise token
    BAD_EXTRA = {
        "sons", "group", "tata", "path", "key", "area", "served",
        "served", "overview", "history", "profile", "section",
        "business", "unit", "division", "segment", "region",
        "north", "south", "east", "west", "central",
        "see", "sees", "also", "note", "notes", "edit", "source",
        "external", "links", "references", "further", "reading",
    }
    if any(p.lower().rstrip('.') in BAD_TOKENS | BAD_EXTRA for p in parts):
        return False

    if not all(re.match(r"^[A-Za-z][A-Za-z'\-]*$", p) for p in parts):
        return False
    alpha_parts = [p for p in parts if p.isalpha() and len(p) >= 3]
    if len(alpha_parts) < 2:
        return False
    if any(p.isupper() and len(p) > 2 for p in parts):
        return False
    return True


def _extract_names_from_text(text: str) -> list:
    NAME_PAT = r'([A-Z][a-z]{1,20}(?:[ \-][A-Z][a-z]{1,20}){1,3})'
    patterns = [
        rf'(?:CEO|Chief Executive Officer)\s*(?:is\s+|:\s*|-\s*|–\s*)?{NAME_PAT}',
        rf'{NAME_PAT}\s*[,\(]\s*(?:CEO|Chief Executive Officer)\b',
        rf'\|\s*(?:chief_executive|ceo)\s*=\s*\[?\[?{NAME_PAT}',
        rf'appointed\s+{NAME_PAT}\s+as\s+(?:CEO|Chief Executive)',
        rf'{NAME_PAT}\s+(?:was|has been)\s+named\s+(?:CEO|Chief Executive)',
        rf'{NAME_PAT}\s+took\s+over\s+as\s+(?:CEO|Chief Executive)',
        rf'(?:Global CEO|Group CEO|CEO and|CEO &)[:\s]+{NAME_PAT}',
        rf'{NAME_PAT}\s+serves\s+as\s+(?:CEO|Chief Executive)',
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip()
            if _is_valid_name(name) and name not in found:
                found.append(name)
    return found


def _fetch_ceo(vendor: str, company_url: str = "") -> str | None:
    # ── Source 0: Company website ─────────────────────────────────────────────
    if company_url:
        about_urls = [
            company_url.rstrip("/") + "/about",
            company_url.rstrip("/") + "/about-us",
            company_url.rstrip("/") + "/team",
            company_url,
        ]
        for url in about_urls:
            page = _webpage(url, 5000)
            if page:
                names = _extract_names_from_text(page)
                if names:
                    print(f"  👤 CEO from company website: {names[0]}")
                    return names[0]

    # ── Source 1: Wikipedia page ──────────────────────────────────────────────
# ── Source 1: Wikipedia page ──────────────────────────────────────────────
    wiki_results = _serper(f'{vendor} company site:en.wikipedia.org', 3)
    # Use ALL significant words for validation, not just first word
    vendor_words = [w for w in vendor.lower().split() if len(w) > 3]
    for r in wiki_results:
        url = r.get("link", "")
        if "wikipedia.org/wiki/" not in url:
            continue
        if any(x in url.lower() for x in ("disambiguation", "list_of", "category:")):
            continue
        page = _webpage(url, 6000)
        if not page:
            continue
        page_lower = page.lower()
        # Require at least half of significant vendor words to appear in first 1000 chars
        intro = page_lower[:1000]
        match_count = sum(1 for w in vendor_words if w in intro)
        if vendor_words and match_count < max(1, len(vendor_words) // 2):
            print(f"  ⚠  Wikipedia page mismatch ({match_count}/{len(vendor_words)} words), skipping: {url[:55]}")
            continue
        names = _extract_names_from_text(page)
        if names:
            print(f"  👤 CEO from Wikipedia page: {names[0]}")
            return names[0]
        snippet = f"{r.get('title','')} {r.get('snippet','')}"
        names = _extract_names_from_text(snippet)
        if names:
            print(f"  👤 CEO from Wikipedia snippet: {names[0]}")
            return names[0]

    # ── Source 2: Business press ──────────────────────────────────────────────
    press_results = _serper(
        f'"{vendor}" CEO "chief executive" 2024 2025 '
        f'site:bloomberg.com OR site:forbes.com OR site:reuters.com '
        f'OR site:livemint.com OR site:economictimes.com OR site:businesstoday.in',
        5,
    )
    combined = " ".join(f"{r.get('title','')} {r.get('snippet','')}" for r in press_results)
    names = _extract_names_from_text(combined)
    if names:
        print(f"  👤 CEO from press: {names[0]}")
        return names[0]

    # ── Source 3: General web ─────────────────────────────────────────────────
    gen_results = _serper(f'"{vendor}" CEO founder "chief executive" who is', 5)
    gen_text    = " ".join(f"{r.get('title','')} {r.get('snippet','')}" for r in gen_results)
    names = _extract_names_from_text(gen_text)
    if names:
        print(f"  👤 CEO from general web: {names[0]}")
        return names[0]

# ── Source 4: Groq snippet-based fallback ─────────────────────────────────
    if gen_text.strip():
        prompt = (
            f"From the following web snippets about '{vendor}', extract the full name of the "
            f"current CEO or Managing Director. Reply with ONLY the person's full name "
            f"(first name + last name), nothing else. "
            f"If you cannot find a clear name, reply with exactly: Not Available\n\n"
            f"SNIPPETS:\n{gen_text[:1500]}"
        )
        answer = _groq(prompt, max_tokens=20)
        if answer and "not available" not in answer.lower() and _is_valid_name(answer):
            print(f"  👤 CEO from Groq snippet fallback: {answer}")
            return answer

    # ── Source 5: Groq direct knowledge fallback (fires when web yielded nothing) ──
    # Only used when we have NO name from any web source — avoids hallucination for
    # obscure companies but correctly fills well-known large companies.
    prompt_knowledge = (
        f"Who is the current CEO or Managing Director of {vendor}? "
        f"Reply with ONLY the person's full name (First Last). "
        f"If you are not certain, reply with exactly: Not Available"
    )
    answer_k = _groq(prompt_knowledge, max_tokens=20)
    if answer_k and "not available" not in answer_k.lower() and _is_valid_name(answer_k):
        print(f"  👤 CEO from Groq knowledge fallback: {answer_k}")
        return answer_k

    return None

# ─── scrape financials (unlisted / private companies) ─────────────────────────

def _scrape_financials(vendor: str, country: str, company_url: str = "") -> dict:
    metrics = {}

    # ── Step 1: Company website ───────────────────────────────────────────────
    if company_url:
        site_text = _webpage(company_url, 6000).lower()
        if site_text:
            for pat in [
                r'revenue[^\$₹\d]*[\$₹]?\s*([\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn|k)',
                r'annual\s+(?:revenue|turnover)[^\$₹\d]*[\$₹]?\s*([\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn)',
                r'\$([\d,]+\.?\d*)\s*(billion|million|trillion)\s+(?:in\s+)?(?:revenue|sales)',
                r'revenue\s+of\s+\$?([\d,]+\.?\d*)\s*(billion|million|trillion)',
            ]:
                m = re.search(pat, site_text)
                if m:
                    metrics["revenue"] = f"{m.group(1)} {m.group(2)}"
                    break

    # ── Step 2: Financial data sites ─────────────────────────────────────────
    india = "india" in country.lower()
    queries = [
        f'"{vendor}" revenue profit loss annual report 2024 2023',
        f'"{vendor}" financial results earnings turnover FY2024',
        f'"{vendor}" annual revenue employees fiscal year 2024',
        f'"{vendor}" revenue billion million 2024 annual report',          # NEW
        f'"{vendor}" total revenue net income fiscal 2024 2023',           # NEW
    ]
    if india:
        queries += [
            f'"{vendor}" site:screener.in OR site:moneycontrol.com revenue EPS',
            f'"{vendor}" site:tofler.in annual turnover net profit',
            f'"{vendor}" site:zauba.com revenue',
        ]
    else:
        queries += [
            f'"{vendor}" site:macrotrends.net OR site:wisesheets.io revenue',
            f'"{vendor}" annual report revenue net income 2024',
            f'"{vendor}" fiscal year revenue billion million 2024 2023',
            f'"{vendor}" site:annualreports.com OR site:wisesheets.io',    # NEW
        ]

    combined = ""
    for q in queries:
        for r in _serper(q, 5):
            combined += f" {r.get('title','')} {r.get('snippet','')}"
            link = r.get("link","")
            if any(d in link for d in ["screener.in","tofler.in","moneycontrol.com","macrotrends.net"]):
                page = _webpage(link, 4000)
                if page:
                    combined += "\n" + page
                    break

    if not combined.strip():
        return metrics

    tl = combined.lower()

    # ── Revenue ───────────────────────────────────────────────────────────────
    # Expanded: handles "$47.6 billion", "revenue: $67.0B", "US$3.2 trillion" etc.
    if not metrics.get("revenue"):
        for pat in [
            r'revenue[^\$₹\d]*[\$₹]?\s*([\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn)',
            r'turnover[^\$₹\d]*[\$₹]?\s*([\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn)',
            r'net\s+sales[^\$₹\d]*[\$₹]?\s*([\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn)',
            r'\$\s*([\d,]+\.?\d*)\s*(billion|million|trillion)\s+(?:in\s+)?(?:revenue|sales|net\s+sales)',
            r'revenue\s+(?:of\s+|was\s+|reached\s+|totaled?\s+)?\$?\s*([\d,]+\.?\d*)\s*(billion|million|trillion)',
            r'reported\s+\$?\s*([\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?(?:revenue|sales)',
            r'generated\s+\$?\s*([\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?revenue',
            r'revenue[:\s]+\$\s*([\d,]+\.?\d*)\s*([bBmMtT])\b',          # "$67.0B" short suffix
            r'(?:us\$|usd)\s*([\d,]+\.?\d*)\s*(billion|million|trillion)', # "US$3.2 billion"
            r'([\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?(?:annual\s+)?(?:revenue|sales|turnover)',
        ]:
            m = re.search(pat, tl)
            if m:
                val, unit = m.group(1), m.group(2)
                # normalise short suffixes b/m/t → billion/million/trillion
                unit = {"b":"billion","m":"million","t":"trillion"}.get(unit.lower(), unit)
                metrics["revenue"] = f"{val} {unit}"
                break

    # ── Net income / profit ───────────────────────────────────────────────────
    if not metrics.get("net_income"):
        for pat in [
            r'net\s+(?:profit|income)[^\$₹\d\-]*[\$₹]?\s*([\-\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn)',
            r'pat[^\$₹\d\-]*[\$₹]?\s*([\-\d,]+\.?\d*)\s*(crore|lakh|million|billion|cr|mn|bn)',
            r'net\s+(?:profit|income)\s+(?:of\s+)?\$?\s*([\-\d,]+\.?\d*)\s*(billion|million)',
            r'profit\s+(?:of\s+)?\$?\s*([\-\d,]+\.?\d*)\s*(billion|million)',
            r'earned\s+\$?\s*([\-\d,]+\.?\d*)\s*(billion|million)\s+(?:in\s+)?(?:profit|income|net\s+income)',
            r'net\s+income[:\s]+\$\s*([\-\d,]+\.?\d*)\s*([bBmMtT])\b',
        ]:
            m = re.search(pat, tl)
            if m:
                val, unit = m.group(1), m.group(2)
                unit = {"b":"billion","m":"million","t":"trillion"}.get(unit.lower(), unit)
                metrics["net_income"] = f"{val} {unit}"
                break

    # ── EPS ───────────────────────────────────────────────────────────────────
    if not metrics.get("eps"):
        for pat in [
            r'\beps\b[\s:of₹$]*\s*([-\d.]+)',
            r'earnings\s+per\s+share[\s:of₹$]*\s*([-\d.]+)',
            r'basic\s+eps[\s:of₹$]*\s*([-\d.]+)',
        ]:
            m = re.search(pat, tl)
            if m:
                metrics["eps"] = m.group(1)
                break

    # ── Net margin ────────────────────────────────────────────────────────────
    if not metrics.get("net_margin"):
        for pat in [
            r'net\s+(?:profit\s+)?margin[\s:of]*([\d.]+)\s*%',
            r'profit\s+margin[\s:of]*([\d.]+)\s*%',
            r'net\s+margin\s+(?:of\s+)?([\d.]+)\s*%',
            r'net\s+margin[:\s]+([\d.]+)%',
        ]:
            m = re.search(pat, tl)
            if m:
                metrics["net_margin"] = f"{m.group(1)}%"
                break

    # ── Operating margin ──────────────────────────────────────────────────────
    if not metrics.get("operating_margin"):
        for pat in [
            r'operating\s+margin[\s:of]*([\d.]+)\s*%',
            r'ebit\s+margin[\s:of]*([\d.]+)\s*%',
        ]:
            m = re.search(pat, tl)
            if m:
                metrics["operating_margin"] = f"{m.group(1)}%"
                break

    # ── Debt/Equity ───────────────────────────────────────────────────────────
    if not metrics.get("debt_equity"):
        for pat in [
            r'debt[\s/\\-]+(?:to[\s-]+)?equity[\s:of]*([\d.]+)',
            r'd/e\s+ratio[\s:of]*([\d.]+)',
        ]:
            m = re.search(pat, tl)
            if m:
                metrics["debt_equity"] = f"{m.group(1)}x"
                break

    # ── ROCE ──────────────────────────────────────────────────────────────────
    if not metrics.get("roce"):
        for pat in [
            r'\broce\b[\s:of]*([\d.]+)\s*%',
            r'return\s+on\s+capital\s+employed[\s:of]*([\d.]+)\s*%',
        ]:
            m = re.search(pat, tl)
            if m:
                metrics["roce"] = f"{m.group(1)}%"
                break

    # ── Revenue growth ────────────────────────────────────────────────────────
    if not metrics.get("revenue_growth"):
        for pat in [
            r'revenue\s+(?:grew|increased|declined|fell)\s+(?:by\s+)?([\d.]+)\s*%',
            r'(?:yoy|year.over.year)\s+(?:growth|decline)[\s:of]*([\d.]+)\s*%',
            r'revenue\s+growth[\s:of]*([\d.]+)\s*%',
        ]:
            m = re.search(pat, tl)
            if m:
                metrics["revenue_growth"] = f"{m.group(1)}%"
                break

    # ── Market cap ────────────────────────────────────────────────────────────
    if not metrics.get("market_cap"):
        for pat in [
            r'market\s+cap(?:itali[sz]ation)?[\s:of]*\$?\s*([\d,]+\.?\d*)\s*(billion|million|trillion)',
            r'valued\s+at\s+\$?\s*([\d,]+\.?\d*)\s*(billion|million|trillion)',
            r'market\s+cap(?:itali[sz]ation)?[:\s]+\$\s*([\d,]+\.?\d*)\s*([bBmMtT])\b',
        ]:
            m = re.search(pat, tl)
            if m:
                val, unit = m.group(1), m.group(2)
                unit = {"b":"billion","m":"million","t":"trillion"}.get(unit.lower(), unit)
                metrics["market_cap"] = f"${val} {unit}"
                break

    # ── Current ratio ─────────────────────────────────────────────────────────
    if not metrics.get("current_ratio"):
        m = re.search(r'current\s+ratio[\s:of]*([\d.]+)', tl)
        if m:
            metrics["current_ratio"] = m.group(1)

    if metrics:
        metrics["source"] = "web_scrape"
    return metrics

# ─── profile scrape ───────────────────────────────────────────────────────────

def _scrape_profile(vendor: str, country: str, company_url: str = "") -> dict:
    india = "india" in country.lower()
    p: dict = {}
    combined = ""
    urls = []

    # ── Step 0: Company website directly ─────────────────────────────────────
    if company_url:
        about_pages = [
            company_url.rstrip("/") + "/about",
            company_url.rstrip("/") + "/about-us",
            company_url,
        ]
        for url in about_pages:
            page = _webpage(url, 6000)
            if len(page) > 200:
                combined += "\n" + page
                print(f"  📄 Profile from site: {url[:55]}")
                break

    # ── Step 0b: Wikipedia direct fetch ──────────────────────────────────────
    wiki_url  = f"https://en.wikipedia.org/wiki/{vendor.replace(' ', '_')}"
    wiki_page = _webpage(wiki_url, 6000)
    if wiki_page and vendor.lower().split()[0] in wiki_page.lower()[:500]:
        combined += "\n" + wiki_page
        print(f"  📄 Profile from Wikipedia: {vendor}")

    # ── Step 1: Serper queries ────────────────────────────────────────────────
    q_list = [
        f'"{vendor}" founded headquarters employees CEO founder',
        f'"{vendor}" site:en.wikipedia.org',
        f'"{vendor}" site:crunchbase.com OR site:tracxn.com',
        f'"{vendor}" about company history overview',
    ]
    if india:
        q_list.append(f'"{vendor}" site:tofler.in OR site:zaubacorp.com')

    for q in q_list:
        for r in _serper(q, 5):
            combined += f" {r.get('title','')} {r.get('snippet','')}"
            urls.append(r.get("link", ""))

    # ── Step 2: Deep fetch best structured source ─────────────────────────────
    DEEP = ["wikipedia.org", "crunchbase.com", "tracxn.com", "tofler.in", "bloomberg.com"]
    for url in urls:
        if url and any(d in url for d in DEEP):
            page = _webpage(url, 6000)
            if len(page) > 300:
                combined += "\n" + page
                print(f"  📄 Deep profile: {url[:55]}")
                break

    if not combined.strip():
        return p

    t  = combined
    tl = combined.lower()

# ── Founded year ──────────────────────────────────────────────────────────
    for pat in [
        r'(?:founded|incorporated|established|launched)[^\d]*((?:19|20)\d{2})',
        r'(?:since|est\.?\s*|in\s+)((?:19|20)\d{2})\b',
    ]:
        m = re.search(pat, tl)
        if m:
            yr = int(m.group(1))
            if 1800 <= yr <= 2025:
                p["founded"] = str(yr)
                break

    # ── Founder — must be a real human name, not an org ───────────────────────
    FOUNDER_ORG_SKIP = {
        "tata sons", "tata group", "infosys ltd", "wipro ltd",
        "holding", "parent", "subsidiary", "group", "sons",
    }
    for pat in [
        r'(?:founded by|co-founded by|founder\s+is|founders?:)[^\w\n]*([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})',
        r'([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})[,\s]+(?:founder|co-founder)\b',
    ]:
        m = re.search(pat, t)
        if m:
            name = m.group(1).strip()
            # Reject if it looks like an org name
            if any(skip in name.lower() for skip in FOUNDER_ORG_SKIP):
                continue
            if _is_valid_name(name):
                p["founder"] = name
                break

    # ── Headquarters — reject Wikipedia noise labels ──────────────────────────
    HQ_NOISE = {
        "area served", "key", "overview", "history", "edit", "source",
        "see also", "external", "references", "products", "services",
        "subsidiaries", "parent", "founded", "revenue", "employees",
    }
    for pat in [
        r'headquartered?\s+in\s+([\w\s,]+?)(?:\.|,\s*(?:india|usa|uk|and|the|\n))',
        r'headquarters[:\s]+([\w\s,]+?)(?:\.|<|\n)',
        r'based\s+in\s+([\w\s,]+?)(?:\.|,\s*(?:india|usa|uk|\n))',
        r'global\s+headquarters[:\s]+([\w\s,]+?)(?:\.|<|\n)',
        r'principal\s+office[s]?\s*(?:in|at)[:\s]+([\w\s,]+?)(?:\.|<|\n)',
    ]:
        m = re.search(pat, tl)
        if m:
            hq = m.group(1).strip().title()
            # Reject if it matches any noise label
            if any(noise in hq.lower() for noise in HQ_NOISE):
                continue
            if 3 < len(hq) < 60 and not any(bad in hq.lower() for bad in ["http","www","ltd","pvt"]):
                p["headquarters"] = hq
                break
            
    # ── Employees ─────────────────────────────────────────────────────────────
    for pat in [
        r'\b(\d{1,6}(?:,\d{3})?)\s+(?:full[- ]time\s+)?employees\b',
        r'(?:employees|workforce|headcount|staff)[:\s]+(\d{1,6}(?:,\d{3})?)\b',
        r'team\s+of\s+(\d{1,5})\b',
        # large firms: "over 300,000 people" / "415,000 professionals"
        r'\b(\d{1,6}(?:,\d{3})?)\s+(?:people|professionals|associates|workers)\b',
        r'(?:more than|over|nearly|approximately)\s+(\d{1,6}(?:,\d{3})?)\s+(?:employees|people|professionals)',
    ]:
        m = re.search(pat, tl)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                n = int(raw)
                # Raised cap to 5M, still reject years
                if 2 <= n <= 5_000_000 and not (1800 <= n <= 2030):
                    p["employees"] = f"{n:,}"
                    break
            except Exception:
                pass

    # ── Groq fallback for missing fields ──────────────────────────────────────
    missing = [f for f in ("founded", "founder", "headquarters", "employees") if f not in p]
    if missing and combined.strip():
        ask = ", ".join(missing)
        prompt = (
            f"From the following web text about '{vendor}', extract these fields: {ask}.\n"
            f"Reply ONLY with a JSON object like: "
            f'{{ "founded": "2010", "founder": "Jane Smith", "headquarters": "Mumbai, India", "employees": "250" }}\n'
            f"Use null for any field you cannot find with confidence. No explanation.\n\n"
            f"TEXT:\n{combined[:2500]}"
        )
        answer = _groq(prompt, max_tokens=120)
        if answer:
            import json as _json
            answer = re.sub(r"^```(?:json)?|```$", "", answer.strip(), flags=re.MULTILINE).strip()
            try:
                data = _json.loads(answer)
                for field in missing:
                    val = data.get(field)
                    if val and str(val).lower() not in ("null","none","n/a","unknown",""):
                        if field in ("founder",) and not _is_valid_name(str(val)):
                            continue
                        p[field] = str(val)
                        print(f"  🤖 Groq filled '{field}': {val}")
            except Exception as e:
                print(f"  ⚠  Groq profile parse: {e} | raw: {answer[:80]}")

    p.pop("description", None)
    return p


# ─── main public entry ────────────────────────────────────────────────────────

def fetch_financial_and_profile(
    vendor: str,
    country: str,
    ticker: str = "",
    web_snippets: str = "",
    company_url: str = "",
) -> tuple[dict, dict]:
    """
    Returns (financial_metrics, profile_extras).
    Keys only present when they have real values.
    Description is never included in profile_extras.
    """
    print(f"\n💰 Fetching financials + profile: {vendor}")

    financial_metrics: dict = {}
    profile_extras:    dict = {}

    cu = company_url.strip()
    if cu and not cu.startswith("http"):
        cu = "https://" + cu

    # ── Run ticker-lookup + profile-scrape + CEO-fetch in parallel ────────────
    with ThreadPoolExecutor(max_workers=3) as ex:
        ticker_future  = ex.submit(_find_ticker, vendor, country) if not ticker.strip() else None
        profile_future = ex.submit(_scrape_profile, vendor, country, cu)
        ceo_future     = ex.submit(_fetch_ceo, vendor, cu)

        resolved_ticker = ticker.strip() or (ticker_future.result() if ticker_future else "")
        prof            = profile_future.result()
        ceo_from_web    = ceo_future.result()

    profile_extras.update(prof)

    if ceo_from_web:
        profile_extras["ceo"] = ceo_from_web

    # ── yfinance for listed companies ─────────────────────────────────────────
    if resolved_ticker:
        yf_data = _yfinance(resolved_ticker)
        for k in ("revenue", "net_income", "eps", "pe_ratio", "debt_equity",
                  "net_margin", "operating_margin", "roce", "revenue_growth",
                  "current_ratio", "market_cap"):
            if yf_data.get(k):
                financial_metrics[k] = yf_data[k]
        financial_metrics["ticker"] = resolved_ticker

        for k in ("employees", "headquarters"):
            if yf_data.get(k) and not profile_extras.get(k):
                profile_extras[k] = yf_data[k]

        if not profile_extras.get("ceo") and yf_data.get("ceo"):
            profile_extras["ceo"] = yf_data["ceo"]

    # ── Scrape financials if yfinance gave nothing ────────────────────────────
    if not financial_metrics:
        sc = _scrape_financials(vendor, country, cu)
        financial_metrics.update(sc)

    # ── Groq financial fallback — runs for ALL private companies ─────────────
    # Changed: no longer requires web_snippets — uses its own scrape data
    fin_keys = ("revenue","net_income","eps","net_margin","debt_equity","roce","market_cap")
    missing_fins = [k for k in fin_keys if not financial_metrics.get(k)]

    if missing_fins:
        # Use web snippets if provided, otherwise do a quick targeted search
        text_for_groq = web_snippets
        if not text_for_groq.strip():
            # Quick targeted search for financial figures
            results = _serper(f'"{vendor}" revenue billion million annual 2024 2023', 5)
            text_for_groq = " ".join(
                f"{r.get('title','')} {r.get('snippet','')}" for r in results
            )

        if text_for_groq.strip():
            prompt = (
                f"From the following web text about '{vendor}', extract any available financial figures.\n"
                f"Reply ONLY with a JSON object. Use null for missing fields. No explanation.\n"
                f'Example: {{ "revenue": "$67B", "net_income": "$3.8B", "net_margin": "5.6%", '
                f'"employees": "330,000", "headquarters": "New York, US" }}\n\n'
                f"TEXT:\n{text_for_groq[:2000]}"
            )
            answer = _groq(prompt, max_tokens=200)
            if answer:
                import json as _json
                answer = re.sub(r"^```(?:json)?|```$", "", answer.strip(), flags=re.MULTILINE).strip()
                try:
                    data = _json.loads(answer)
                    for k in fin_keys:
                        val = data.get(k)
                        if val and str(val).lower() not in ("null","none","n/a","unknown","") \
                                and not financial_metrics.get(k):
                            financial_metrics[k] = str(val)
                    # Fill profile gaps too
                    for k in ("employees","headquarters","founded","founder"):
                        val = data.get(k)
                        if val and str(val).lower() not in ("null","none","n/a","unknown","") \
                                and not profile_extras.get(k):
                            if k == "founder" and not _is_valid_name(str(val)):
                                continue
                            profile_extras[k] = str(val)
                    if financial_metrics:
                        financial_metrics.setdefault("source", "llm_web")
                except Exception as e:
                    print(f"  ⚠  Groq financial parse: {e}")

    profile_extras.pop("description", None)

    print(f"  ✅ metrics={list(financial_metrics.keys())} | profile={list(profile_extras.keys())}")
    return financial_metrics, profile_extras