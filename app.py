import streamlit as st
import html as _html


# Inside your existing tab layout:

# ── Safe imports ──────────────────────────────────────────────────────────────
_import_errors = []

try:
    from services import get_vendor_analysis, calculate_weighted_score
except Exception as _e:
    _import_errors.append(f"services.py: {_e}")
    get_vendor_analysis = calculate_weighted_score = None

try:
    from charts import plot_overall_gauge, plot_all_risk_gauges, plot_overall_risk_pie
except Exception as _e:
    _import_errors.append(f"charts.py: {_e}")
    plot_overall_gauge = plot_all_risk_gauges = plot_overall_risk_pie = None

try:
    from pdf_generator import generate_pdf
except Exception as _e:
    _import_errors.append(f"pdf_generator.py: {_e}")
    generate_pdf = None

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vendor Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar toggle fix (Streamlit 1.57) ───────────────────────────────────────
st.markdown("""
<style>
[data-testid="stHeader"] {
    pointer-events: auto !important;
    background: transparent !important;
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999990 !important;
}
[data-testid="stToolbar"] {
    pointer-events: auto !important;
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
}
[data-testid="stExpandSidebarButton"] {
    pointer-events: auto !important;
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
}
[data-testid="stExpandSidebarButton"] button {
    background: rgba(0,230,118,0.10) !important;
    border: 1px solid rgba(0,230,118,0.30) !important;
    border-radius: 8px !important;
    width: 36px !important;
    height: 36px !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
}
[data-testid="stExpandSidebarButton"] button:hover {
    background: rgba(0,230,118,0.22) !important;
    border-color: rgba(0,230,118,0.60) !important;
}
[data-testid="stExpandSidebarButton"] button span,
[data-testid="stExpandSidebarButton"] button svg,
[data-testid="stExpandSidebarButton"] button [data-testid="stIconMaterial"] {
    color: #00e676 !important;
    fill: #00e676 !important;
    opacity: 1 !important;
}
[data-testid="stSidebarCollapseButton"] {
    visibility: visible !important;
    opacity: 1 !important;
    display: flex !important;
}
.eelgd2m10 {
    display: inline !important;
    visibility: visible !important;
    opacity: 1 !important;
}
section[data-testid="stSidebar"] { transition: width 0.3s ease !important; }
[data-testid="stSidebarContent"]  { overflow: visible !important; }
</style>
""", unsafe_allow_html=True)

# ── Import errors ─────────────────────────────────────────────────────────────
if _import_errors:
    st.error("⚠️ Import errors detected:")
    for err in _import_errors:
        st.code(err)
    st.info("pip install streamlit plotly pandas reportlab tavily-python groq python-dotenv")
    st.stop()

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --bg-base:       #0b0f1a;
  --bg-card:       #111827;
  --bg-card-hover: #16202f;
  --bg-sidebar:    #080c16;
  --accent-green:  #00e676;
  --accent-blue:   #6ea8ff;
  --accent-amber:  #ffc56a;
  --accent-red:    #ff7070;
  --accent-purple: #d89dff;
  --text-primary:  #ffffff;
  --text-secondary:#b0bfd8;
  --text-muted:    #6b7fa3;
  --border:        #1a2540;
  --border-hover:  #283758;
  --radius:        14px;
  --radius-sm:     8px;
  --shadow:        0 4px 24px rgba(0,0,0,0.5);
  --font:          'DM Sans', 'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji', sans-serif;
  --mono:          'JetBrains Mono', monospace;
}
*,*::before,*::after{box-sizing:border-box;}
html,body,[data-testid="stAppViewContainer"]{
  background:var(--bg-base) !important;
  font-family:'DM Sans','Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;
  color:var(--text-primary) !important;
}
html{scroll-behavior:smooth;}

[data-testid="stSidebar"]{
  background:var(--bg-sidebar) !important;
  border-right:1px solid var(--border) !important;
}
[data-testid="stSidebar"]>div:first-child{padding:1.25rem 1rem 2rem !important;}

.brand-wrap{display:flex;align-items:center;gap:10px;padding-bottom:1.25rem;
  border-bottom:1px solid var(--border);margin-bottom:1.5rem;}
.brand-icon{width:36px;height:36px;background:linear-gradient(135deg,#00e676 0%,#448aff 100%);
  border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0;
  font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}
.brand-name{font-size:17px;font-weight:700;color:#fff;}
.brand-tag{font-size:10px;color:#00e676;font-family:monospace;letter-spacing:1.2px;margin-top:1px;}

.sb-label{font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--text-muted);padding:0 4px;margin-bottom:8px;margin-top:1.5rem;}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea{
  background:#0f1726 !important;border:1px solid var(--border) !important;
  border-radius:var(--radius-sm) !important;color:#fff !important;font-size:15px !important;}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus{
  border-color:#00e676 !important;box-shadow:0 0 0 2px rgba(0,230,118,0.12) !important;}
[data-testid="stSelectbox"]>div>div{
  background:#0f1726 !important;border:1px solid var(--border) !important;
  border-radius:var(--radius-sm) !important;color:#fff !important;}
label,[data-testid="stSidebar"] label{
  color:var(--text-secondary) !important;font-size:13px !important;font-weight:600 !important;}

[data-testid="stButton"] button{
  background:linear-gradient(135deg,#00e676 0%,#00c853 100%) !important;
  color:#040d18 !important;border:none !important;border-radius:10px !important;
  font-weight:700 !important;font-size:14px !important;width:100% !important;
  padding:0.6rem 1rem !important;transition:opacity 0.2s !important;}
[data-testid="stButton"] button:hover{opacity:0.85 !important;}

[data-testid="stDownloadButton"] button{
  background:rgba(68,138,255,0.12) !important;color:#6ea8ff !important;
  border:1px solid rgba(68,138,255,0.35) !important;border-radius:10px !important;
  font-weight:600 !important;font-size:14px !important;width:100% !important;}

.main .block-container{padding:1.75rem 2.5rem !important;max-width:100% !important;}

.page-header{display:flex;align-items:flex-start;justify-content:space-between;
  margin-bottom:2rem;padding-bottom:1.25rem;border-bottom:1px solid var(--border);
  animation:fadeDown 0.45s ease both;}
.ph-title{font-size:28px;font-weight:700;color:#fff;letter-spacing:-0.3px;}
.ph-sub{font-size:15px;color:var(--text-secondary);margin-top:3px;}
.badge{background:rgba(0,230,118,0.09);border:1px solid rgba(0,230,118,0.28);
  color:#00e676;padding:6px 15px;border-radius:20px;font-size:13px;font-weight:600;}

.risk-banner{display:flex;align-items:center;gap:14px;padding:18px 24px;
  border-radius:var(--radius);font-size:17px;font-weight:700;letter-spacing:0.4px;
  margin-bottom:1.75rem;animation:fadeDown 0.5s ease both;}
.risk-banner.low   {background:rgba(0,230,118,0.08); border:1px solid rgba(0,230,118,0.3); color:#00e676;}
.risk-banner.medium{background:rgba(255,171,64,0.08);border:1px solid rgba(255,171,64,0.3);color:#ffc56a;}
.risk-banner.high  {background:rgba(255,82,82,0.08); border:1px solid rgba(255,82,82,0.3); color:#ff7070;}
.rb-score{margin-left:auto;font-family:monospace;font-size:34px;font-weight:700;}
.rb-meta{font-size:11px;opacity:0.75;letter-spacing:1.4px;margin-bottom:2px;font-weight:500;}

.kpi-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:2rem;}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(3,1fr);}}
.kpi-card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px 16px;position:relative;overflow:hidden;
  transition:transform 0.22s,border-color 0.22s,box-shadow 0.22s;animation:fadeUp 0.5s ease both;}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2.5px;
  border-radius:var(--radius) var(--radius) 0 0;}
.kpi-card.g::before{background:linear-gradient(90deg,#00e676,transparent);}
.kpi-card.b::before{background:linear-gradient(90deg,#6ea8ff,transparent);}
.kpi-card.a::before{background:linear-gradient(90deg,#ffc56a,transparent);}
.kpi-card.r::before{background:linear-gradient(90deg,#ff7070,transparent);}
.kpi-card.p::before{background:linear-gradient(90deg,#d89dff,transparent);}
.kpi-card:hover{transform:translateY(-3px);border-color:var(--border-hover);box-shadow:var(--shadow);}
.kpi-ico{position:absolute;top:14px;right:14px;font-size:22px;opacity:0.4;font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}
.kpi-lbl{font-size:12px;font-weight:600;letter-spacing:0.9px;text-transform:uppercase;
  color:var(--text-muted);margin-bottom:9px;}
.kpi-val{font-size:30px;font-weight:700;font-family:monospace;line-height:1;margin-bottom:4px;}
.kpi-val.g{color:#00e676;}.kpi-val.b{color:#6ea8ff;}
.kpi-val.a{color:#ffc56a;}.kpi-val.r{color:#ff7070;}.kpi-val.p{color:#d89dff;}
.kpi-sub{font-size:12.5px;color:var(--text-muted);}

.sec-anchor{padding-top:8px;}
.sec-heading{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:700;
  color:#fff;margin-bottom:1rem;padding-bottom:10px;border-bottom:1px solid var(--border);}
.sh-icon{width:32px;height:32px;border-radius:7px;display:flex;align-items:center;
  justify-content:center;font-size:16px;
  font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}
.sh-icon.g{background:rgba(0,230,118,0.12);}
.sh-icon.b{background:rgba(68,138,255,0.12);}
.sh-icon.a{background:rgba(255,171,64,0.12);}
.sh-icon.r{background:rgba(255,82,82,0.12);}
.sh-icon.p{background:rgba(199,125,255,0.12);}

.dsec{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);
  padding:22px;margin-bottom:22px;animation:fadeUp 0.5s ease both;transition:border-color 0.2s;}
.dsec:hover{border-color:var(--border-hover);}

/* ── Risk card (types of risk section) ── */
.risk-card{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--radius);padding:20px 22px;margin-bottom:14px;
  transition:border-color 0.2s,transform 0.2s;animation:fadeUp 0.4s ease both;
}
.risk-card:hover{border-color:var(--border-hover);transform:translateY(-2px);}
.rc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}
.rc-title{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700;color:#fff;}
.rc-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
.rc-badge{font-family:monospace;font-size:15px;font-weight:700;
  padding:5px 14px;border-radius:20px;flex-shrink:0;}
.rc-bar-wrap{height:4px;background:var(--border);border-radius:3px;
  margin-bottom:12px;overflow:hidden;}
.rc-bar-fill{height:100%;border-radius:3px;transition:width 0.6s ease;}
.rc-summary{font-size:14px;color:var(--text-secondary);line-height:1.6;margin-bottom:10px;}
.rc-severity{font-size:12px;color:var(--text-muted);font-style:italic;margin-bottom:10px;}
.rc-events{margin-top:8px;}
.rc-event{display:flex;align-items:flex-start;gap:8px;padding:7px 10px;
  margin-bottom:5px;border-radius:6px;font-size:13px;color:var(--text-secondary);
  background:rgba(255,255,255,0.03);border-left:3px solid transparent;}
.rc-event-icon{flex-shrink:0;margin-top:1px;font-size:12px;font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}
.rc-sources{margin-top:10px;padding-top:10px;border-top:1px solid var(--border);}
.rc-sources-label{font-size:11px;font-weight:600;letter-spacing:1px;
  text-transform:uppercase;color:var(--text-muted);margin-bottom:6px;}
.rc-source-link{display:inline-block;font-size:12px;color:#6ea8ff;
  text-decoration:none;margin-right:10px;margin-bottom:4px;
  word-break:break-all;opacity:0.85;}
.rc-source-link:hover{opacity:1;text-decoration:underline;}

/* ── Other shared components ── */
.sig-item{display:flex;align-items:flex-start;gap:11px;padding:12px 16px;
  margin-bottom:9px;background:rgba(255,82,82,0.06);
  border:1px solid rgba(255,82,82,0.18);border-radius:var(--radius-sm);
  font-size:14px;color:#fff;line-height:1.5;}
.sig-ico{color:#ff7070;font-size:14px;flex-shrink:0;margin-top:2px;font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}

.gi{display:flex;align-items:flex-start;gap:10px;padding:11px 0;
  border-bottom:1px solid var(--border);font-size:14px;
  color:var(--text-secondary);line-height:1.6;}
.gi:last-child{border-bottom:none;}
.gi-dot-a{color:#ffc56a;flex-shrink:0;margin-top:3px;}
.gi-dot-g{color:#00e676;flex-shrink:0;margin-top:3px;}

.prof-row{display:flex;padding:12px 0;border-bottom:1px solid var(--border);font-size:15px;}
.prof-row:last-child{border-bottom:none;}
.prof-key{width:160px;flex-shrink:0;color:var(--text-muted);font-weight:500;}
.prof-val{color:#fff;font-weight:500;}

.filing-box{background:rgba(68,138,255,0.06);border:1px solid rgba(68,138,255,0.22);
  border-radius:var(--radius-sm);padding:16px 20px;font-size:15px;
  color:var(--text-secondary);line-height:1.8;}

.empty-state{text-align:center;padding:6rem 2rem;animation:fadeUp 0.6s ease both;}
.empty-state .es-icon{font-size:68px;margin-bottom:1.25rem;font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}
.empty-state h2{font-size:24px;color:#fff;margin-bottom:8px;}
.empty-state p{font-size:16px;color:var(--text-muted);max-width:420px;margin:0 auto;line-height:1.7;}

.snav-wrap{display:flex;flex-direction:column;gap:2px;}
.snav-item{display:flex;align-items:center;gap:12px;padding:10px 12px;
  border-radius:8px;text-decoration:none !important;cursor:pointer;transition:background 0.18s;}
.snav-item:hover{background:rgba(255,255,255,0.06);}
.snav-icon{width:30px;height:30px;border-radius:7px;display:flex;align-items:center;
  justify-content:center;font-size:15px;flex-shrink:0;
  font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif !important;}
.snav-lbl{font-size:15px;font-weight:500;line-height:1;}

/* gauge container — each cell gets fixed height so rows never overlap */
.gauge-cell{height:280px;overflow:hidden;}

/* Force emoji rendering everywhere */
*{font-variant-emoji:text;}
.sh-icon,.snav-icon,.brand-icon,.kpi-ico,.sig-ico,.es-icon,.rc-event-icon,
.gi-dot-a,.gi-dot-g,.badge span{
  font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',
    'Segoe UI Symbol','Symbola',sans-serif !important;
}
#MainMenu,footer{visibility:hidden !important;}
[data-testid="stDecoration"]{display:none !important;}
.js-plotly-plot .plotly{background:transparent !important;}

::-webkit-scrollbar{width:5px;}
::-webkit-scrollbar-track{background:var(--bg-base);}
::-webkit-scrollbar-thumb{background:var(--border-hover);border-radius:4px;}

@keyframes fadeDown{from{opacity:0;transform:translateY(-14px);}to{opacity:1;transform:translateY(0);}}
@keyframes fadeUp  {from{opacity:0;transform:translateY(18px); }to{opacity:1;transform:translateY(0);}}
.kpi-card:nth-child(1){animation-delay:.04s}.kpi-card:nth-child(2){animation-delay:.08s}
.kpi-card:nth-child(3){animation-delay:.12s}.kpi-card:nth-child(4){animation-delay:.16s}
.kpi-card:nth-child(5){animation-delay:.20s}.kpi-card:nth-child(6){animation-delay:.24s}
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def score_cls(s):
    return "g" if s <= 40 else ("a" if s <= 70 else "r")

def score_hex(s):
    return "#00e676" if s <= 40 else ("#ffc56a" if s <= 70 else "#ff7070")

def safe_str(val):
    """Guarantee a plain string — never let a dict leak into HTML."""
    if isinstance(val, dict):
        return val.get("summary", val.get("text", str(val)))
    return str(val) if val else ""

def clean_list(lst):
    """
    Return plain strings from whatever the LLM returned.
    Handles: plain str, bracketed str, simple dict, nested dict
    {'id':1,'description':'...','actions':[...]}, stringified dicts.
    """
    import re as _re, ast as _ast

    def _extract_dict(d):
        for key in ("description","recommendation","gap","signal","summary","text"):
            if key in d and isinstance(d[key], str) and d[key].strip():
                return d[key].strip()
        parts = [str(v) for v in d.values() if isinstance(v, str) and v.strip()]
        return " — ".join(parts) if parts else ""

    out = []
    for item in (lst or []):
        if isinstance(item, dict):
            t = _extract_dict(item)
            if t: out.append(t)
        elif isinstance(item, str):
            text = item.strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    parsed = _ast.literal_eval(text)
                    if isinstance(parsed, dict):
                        t = _extract_dict(parsed)
                        if t: out.append(t)
                        continue
                    elif isinstance(parsed, list):
                        out.extend(clean_list(parsed))
                        continue
                except Exception:
                    pass
            text = _re.sub(r"^\[|\]$", "", text).strip().strip("\'\"")
            if text: out.append(text)
        else:
            s = str(item).strip()
            if s: out.append(s)
    return out


# ── Financial table renderer ──────────────────────────────────────────────────
import re as _re, pandas as pd

def render_financial_table(result: dict):
    fm = result.get("financial_metrics") or \
         result.get("company_profile", {}).get("financial_metrics") or {}
    km = result.get("explanations", {}).get("financial", {}).get("key_metrics", {})

    FIELDS = [
        ("ticker",           "Ticker"),
        ("market_cap",       "Market Cap"),
        ("revenue",          "Revenue"),
        ("net_income",       "Net Income"),
        ("eps",              "EPS (Trailing)"),
        ("pe_ratio",         "P/E Ratio"),
        ("debt_equity",      "Debt / Equity"),
        ("net_margin",       "Net Margin"),
        ("operating_margin", "Operating Margin"),
        ("roce",             "ROCE"),
        ("revenue_growth",   "Revenue Growth YoY"),
        ("current_ratio",    "Current Ratio"),
        ("employees",        "Employees"),
    ]

    rows = []
    for key, label in FIELDS:
        val = fm.get(key) or (km.get(key) if key in ("debt_equity","eps","roce","net_margin") else None)
        if not val or str(val).strip() in ("","None","Not Available","N/A","unknown"):
            continue

        display = str(val)

        # Colour-code EPS
        if key == "eps":
            try:
                fv = float(_re.sub(r"[^\d.\-]", "", display))
                display = ("🔴 " if fv < 0 else "🟢 ") + display
            except: pass

        # Colour-code Debt/Equity
        elif key == "debt_equity":
            try:
                fv = float(_re.sub(r"[^\d.\-]", "", display))
                if fv > 2:   display = f"🔴 {display} (High)"
                elif fv > 1: display = f"🟡 {display} (Moderate)"
                else:        display = f"🟢 {display}"
            except: pass

        # Colour-code revenue growth
        elif key == "revenue_growth":
            display = ("🔴 " if ("-" in display or "−" in display) else "🟢 ") + display

        rows.append({"Metric": label, "Value": display})

    if not rows:
        return  # silent — no table shown if truly no data

    rows_html = ""
    for r in rows:
        rows_html += (
            f'<tr>'
            f'<td style="padding:10px 16px;color:#6b7fa3;font-size:13px;'
            f'font-weight:600;border-bottom:1px solid #1a2540;width:200px;">'
            f'{r["Metric"]}</td>'
            f'<td style="padding:10px 16px;color:#ffffff;font-size:14px;'
            f'font-weight:500;border-bottom:1px solid #1a2540;">'
            f'{r["Value"]}</td>'
            f'</tr>'
        )

    src = fm.get("source","")
    src_note = (
        "Source: Yahoo Finance (real-time)" if src == "yfinance"
        else ("Source: Web scrape — verify with official filings" if src == "web_scrape"
              else "Source: LLM interpretation")
    )

    trend = km.get("revenue_trend","")
    trend_badge = ""
    if trend and trend != "unknown":
        color_map   = {"growing":"#00e676","declining":"#ff7070","stable":"#ffc56a"}
        trend_color = color_map.get(trend,"#6b7fa3")
        trend_badge = (
            f'<span style="background:{trend_color}22;color:{trend_color};'
            f'padding:3px 10px;border-radius:10px;font-size:12px;font-weight:700;'
            f'margin-left:12px;">Revenue: {trend.title()}</span>'
        )

    table_html = f"""
<div style="background:#111827;border:1px solid #1a2540;border-radius:14px;
            overflow:hidden;margin-bottom:22px;">
  <div style="padding:14px 18px;border-bottom:1px solid #1a2540;
              display:flex;align-items:center;justify-content:space-between;">
    <span style="font-size:15px;font-weight:700;color:#fff;">📊 Financial Metrics</span>
    {trend_badge}
  </div>
  <table style="width:100%;border-collapse:collapse;">
    {rows_html}
  </table>
  <div style="padding:10px 16px;font-size:11px;color:#6b7fa3;
              border-top:1px solid #1a2540;">{src_note}</div>
</div>
"""
    st.markdown(table_html, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="brand-wrap">
      <div class="brand-icon">&#128737;&#65039;</div>
      <div>
        <div class="brand-name">VendorIQ</div>
        <div class="brand-tag">INTELLIGENCE PLATFORM</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-label">Vendor Inputs</div>', unsafe_allow_html=True)
    vendor      = st.text_input("Vendor Name",     placeholder="e.g. Acme Corp")
    industry    = st.selectbox("Industry", ["IT","Finance","Healthcare","Retail","Manufacturing","Other"])
    country     = st.text_input("Country",         placeholder="e.g. Hyderabad, India")
    company_url = st.text_input("Company Website", placeholder="e.g. acmecorp.com  (optional)",
                                help="Helps identify exact company, useful for small startups")
    concerns    = st.text_area("Known Concerns",   placeholder="Optional notes...", height=80)

    manual_profile = {}

    analyze_btn = st.button("Run Analysis")

    if st.session_state.get("analyzed"):
        st.markdown('<div class="sb-label">Jump to Section</div>', unsafe_allow_html=True)
        nav_items = [
            ("sec-charts",   "rgba(0,230,118,0.15)",  "#00e676", "Charts"),
            ("sec-filings",  "rgba(68,138,255,0.15)", "#6ea8ff", "Company Filings"),
            ("sec-fin-table","rgba(0,230,118,0.15)",  "#00e676", "Financial Metrics"),
            ("sec-risks",    "rgba(255,171,64,0.15)", "#ffc56a", "Types of Risk"),
            ("sec-gauges",   "rgba(199,125,255,0.15)","#d89dff", "Risk Gauges"),
            ("sec-signals",  "rgba(255,82,82,0.15)",  "#ff7070", "Key Signals"),
            ("sec-gaps",     "rgba(255,171,64,0.15)", "#ffc56a", "Gaps"),
            ("sec-recs",     "rgba(0,230,118,0.15)",  "#00e676", "Recommendations"),
            ("sec-download", "rgba(68,138,255,0.15)", "#6ea8ff", "Download"),
        ]
        nav_html = ""
        for sec_id, bg, fg, label in nav_items:
            nav_html += (f'<a class="snav-item" href="#{sec_id}">' +
                         f'<span class="snav-icon" style="background:{bg};color:{fg};"></span>' +
                         f'<span class="snav-lbl" style="color:{fg};">{label}</span></a>')
        st.markdown(f'<div class="snav-wrap">{nav_html}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div style="font-size:12px;color:#6b7fa3;text-align:center;line-height:1.7;">'
                'VendorIQ 2026 · AI-Powered Vendor Risk Analysis</div>', unsafe_allow_html=True)

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
  <div>
    <div class="ph-title">Vendor Intelligence</div>
    <div class="ph-sub">AI-powered risk analysis &amp; due diligence</div>
  </div>
  <span class="badge">AI LIVE</span>
</div>
""", unsafe_allow_html=True)

if not st.session_state.get("analyzed") and not analyze_btn:
    st.markdown("""
    <div class="empty-state">
      <div class="es-icon">&#128737;&#65039;</div>
      <h2>Ready to analyze</h2>
      <p>Enter vendor details in the sidebar and click
         <strong style="color:#00e676;">Run Analysis</strong>
         to generate a comprehensive risk report.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

if analyze_btn:
    if not vendor.strip():
        st.markdown("""<div style="background:rgba(255,82,82,0.09);border:1px solid rgba(255,82,82,0.28);
             border-radius:10px;padding:13px 17px;color:#ff7070;font-size:15px;font-weight:500;">
          Warning: Please enter a vendor name before running the analysis.</div>""", unsafe_allow_html=True)
        st.stop()

    progress_box = st.empty()

    def _show(icon, msg, pct):
        progress_box.markdown(f"""
        <div style="background:#111827;border:1px solid #1a2540;border-radius:12px;padding:20px 24px;">
          <div style="font-size:15px;font-weight:600;color:#fff;margin-bottom:12px;">{icon} {msg}</div>
          <div style="background:#1a2540;border-radius:6px;height:6px;overflow:hidden;">
            <div style="width:{pct}%;height:100%;background:linear-gradient(90deg,#00e676,#448aff);
                 border-radius:6px;"></div>
          </div>
          <div style="font-size:12px;color:#6b7fa3;margin-top:8px;">{pct}% complete</div>
        </div>""", unsafe_allow_html=True)

    try:
        _show("Searching", f" web for {_html.escape(vendor)} risk signals...", 20)
        result, raw_data = get_vendor_analysis(
            vendor, industry, country, concerns,
            company_url=company_url.strip(),
            manual_profile=manual_profile,
        )
        _show("Done", "Analysis complete!", 100)
        import time as _t; _t.sleep(0.4)
        progress_box.empty()
    except Exception as e:
        progress_box.empty()
        st.error(f"Analysis error: {e}")
        st.stop()

    if not result or "error" in result:
        st.error("❌ Analysis failed. Check your API keys and connection.")
        st.stop()

    st.session_state.update({
        "analyzed":       True,
        "result":         result,
        "vendor":         vendor,
        "industry":       industry,
        "company_url":    company_url.strip(),
        "manual_profile": manual_profile,
    })
    st.rerun()

# ── Display results ───────────────────────────────────────────────────────────
if "result" not in st.session_state:
    st.stop()

result   = st.session_state["result"]
vendor   = st.session_state["vendor"]
industry = st.session_state.get("industry", "")

profile         = result.get("company_profile", {})
risk_scores     = result.get("risk_scores", {})
explanations    = result.get("explanations", {})
signals         = clean_list(result.get("key_signals", []))
gaps            = clean_list(result.get("gaps", []))
recommendations = clean_list(result.get("recommendations", []))
filings_summary = safe_str(result.get("filings_summary", "Not available."))
risk_level      = result.get("risk_level", "Medium")
evidence_links  = result.get("evidence_links", {})

try:
    overall = calculate_weighted_score(risk_scores, profile=profile)
except Exception:
    overall = sum(risk_scores.values()) // max(len(risk_scores), 1)

sc = score_cls(overall)

# ── Risk banner ───────────────────────────────────────────────────────────────
b_cls   = "low" if overall <= 40 else ("medium" if overall <= 70 else "high")
b_icon  = "🟢"  if overall <= 40 else ("🟡"     if overall <= 70 else "🔴")
b_label = "LOW RISK" if overall <= 40 else ("MEDIUM RISK" if overall <= 70 else "HIGH RISK")

st.markdown(f"""
<div class="risk-banner {b_cls}">
  <span style="font-size:22px;">{b_icon}</span>
  <div>
    <div class="rb-meta">OVERALL STATUS</div>
    {_html.escape(vendor.upper())} — {b_label}
  </div>
  <div class="rb-score">{overall}</div>
</div>
""", unsafe_allow_html=True)

# ── KPI cards ─────────────────────────────────────────────────────────────────
risk_meta = {
    "financial":  ("💰","g","Financial"),
    "reputation": ("🌐","b","Reputation"),
    "key_person": ("👤","p","Key Person"),
    "cyber":      ("🔐","a","Cyber"),
    "compliance": ("📋","r","Compliance"),
}
kpi = '<div class="kpi-grid">'
kpi += f"""<div class="kpi-card {sc}">
  <div class="kpi-ico">🛡️</div>
  <div class="kpi-lbl">Overall Risk</div>
  <div class="kpi-val {sc}">{overall}</div>
  <div class="kpi-sub">{_html.escape(risk_level)} · {_html.escape(industry)}</div>
</div>"""
for key, (ico, col, lbl) in risk_meta.items():
    v   = int(risk_scores.get(key, 50))
    cls = score_cls(v)
    kpi += f"""<div class="kpi-card {cls}">
  <div class="kpi-ico">{ico}</div>
  <div class="kpi-lbl">{lbl} Risk</div>
  <div class="kpi-val {cls}">{v}</div>
  <div class="kpi-sub">out of 100</div>
</div>"""
kpi += '</div>'
st.markdown(kpi, unsafe_allow_html=True)

# ── Charts ────────────────────────────────────────────────────────────────────
st.markdown('<div id="sec-charts" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="sec-heading"><div class="sh-icon g">📊</div> Charts</div>',
            unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    try:
        fig1 = plot_overall_gauge(overall)
        fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font_color="#ffffff")
        st.plotly_chart(fig1, use_container_width=True)
    except Exception as e:
        st.error(f"Chart error: {e}")

with col2:
    try:
        fig2 = plot_overall_risk_pie(risk_scores)
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font_color="#ffffff")
        st.plotly_chart(fig2, use_container_width=True)
    except Exception as e:
        st.error(f"Chart error: {e}")

# ── Filings & profile ─────────────────────────────────────────────────────────
st.markdown('<div id="sec-filings" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="sec-heading"><div class="sh-icon b">📁</div> Company Filings &amp; Profile</div>',
            unsafe_allow_html=True)

col_p, col_f = st.columns(2)
with col_p:
    st.markdown('<div class="dsec">', unsafe_allow_html=True)
    ph = ""
    confidence = result.get("confidence_score", 50)
    total_hits = result.get("total_hits", 0)
    conf_color = "#00e676" if confidence >= 70 else ("#ffc56a" if confidence >= 45 else "#ff7070")
    conf_label = "High" if confidence >= 70 else ("Medium" if confidence >= 45 else "Low")

    for k, v in [
        ("CEO",          safe_str(profile.get("ceo",          "Not Available"))),
        ("Founder",      safe_str(profile.get("founder",       "Not Available"))),
        ("Founded",      safe_str(profile.get("founded",       "Not Available"))),
        ("Headquarters", safe_str(profile.get("headquarters",  "Not Available"))),
        ("Employees",    safe_str(profile.get("employees",     "Not Available"))),
        ("Industry",     safe_str(profile.get("industry",      industry))),
    ]:
        ph += (f'<div class="prof-row">'
               f'<div class="prof-key">{_html.escape(k)}</div>'
               f'<div class="prof-val">{_html.escape(v)}</div></div>')
    ph += f'''<div class="prof-row" style="border-bottom:none;margin-top:8px;padding-top:12px;border-top:1px solid var(--border);">
      <div class="prof-key" style="color:var(--text-muted);">Data Confidence</div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="background:{conf_color}22;color:{conf_color};padding:3px 10px;border-radius:12px;
          font-size:12px;font-weight:700;font-family:monospace;">{conf_label} {confidence}%</span>
        <span style="font-size:11px;color:var(--text-muted);">{total_hits} evidence hits</span>
      </div>
    </div>'''
    st.markdown(ph, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_f:
    st.markdown('<div class="dsec">', unsafe_allow_html=True)
    st.markdown(f'<div class="filing-box">{_html.escape(filings_summary)}</div>',
                unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Financial Metrics Table ───────────────────────────────────────────────────
# Rendered full-width below the two-column profile block
st.markdown('<div id="sec-fin-table" class="sec-anchor"></div>', unsafe_allow_html=True)
render_financial_table(result)

# ── Types of risk ─────────────────────────────────────────────────────────────
st.markdown('<div id="sec-risks" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="sec-heading"><div class="sh-icon a">⚠️</div> Types of Risk &amp; Evidence</div>',
            unsafe_allow_html=True)

RISK_DISPLAY = {
    "financial":  ("Financial Risk",  "#00e676"),
    "reputation": ("Reputation Risk", "#6ea8ff"),
    "key_person": ("Key Person Risk", "#d89dff"),
    "cyber":      ("Cyber Risk",      "#ffc56a"),
    "compliance": ("Compliance Risk", "#ff7070"),
}

for key, (lbl, hex_c) in RISK_DISPLAY.items():
    v    = int(risk_scores.get(key, 50))
    expl = explanations.get(key, {})
    urls = evidence_links.get(key, [])

    if isinstance(expl, dict):
        summary         = safe_str(expl.get("summary", "No summary available."))
        severity_reason = safe_str(expl.get("severity_reason", ""))
        events          = expl.get("observed_events", expl.get("events", []))
    else:
        raw_expl = safe_str(expl)
        if "▸" in raw_expl:
            parts           = raw_expl.split("▸", 1)
            summary         = parts[0].strip()
            severity_reason = ""
            events          = [e.strip() for e in parts[1].split("·") if e.strip()]
        else:
            summary         = raw_expl
            severity_reason = ""
            events          = []

    events_html = ""
    if events:
        events_html = '<div class="rc-events">'
        for evt in events[:4]:
            evt_clean = safe_str(evt)
            events_html += (
                f'<div class="rc-event" style="border-left-color:{hex_c};">'
                f'<span class="rc-event-icon" style="color:{hex_c};">▸</span>'
                f'{_html.escape(evt_clean)}</div>'
            )
        events_html += '</div>'

    sources_html = ""
    clean_urls = [u for u in (urls or []) if isinstance(u, str) and u.startswith("http")]
    if clean_urls:
        links_inner = ""
        for url in clean_urls[:4]:
            display = url.replace("https://","").replace("http://","")
            if len(display) > 55:
                display = display[:52] + "…"
            links_inner += (
                f'<a class="rc-source-link" href="{_html.escape(url)}" '
                f'target="_blank" rel="noopener">{_html.escape(display)}</a>'
            )
        sources_html = (
            f'<div class="rc-sources">'
            f'<div class="rc-sources-label">🔗 Evidence Sources</div>'
            f'{links_inner}'
            f'</div>'
        )

    severity_html = (
        f'<div class="rc-severity">{_html.escape(severity_reason)}</div>'
        if severity_reason else ""
    )

    st.markdown(f"""
<div class="risk-card">
  <div class="rc-header">
    <div class="rc-title">
      <div class="rc-dot" style="background:{hex_c};box-shadow:0 0 6px {hex_c}66;"></div>
      {_html.escape(lbl)}
    </div>
    <div class="rc-badge" style="background:{hex_c}1a;color:{hex_c};">{v}/100</div>
  </div>
  <div class="rc-bar-wrap">
    <div class="rc-bar-fill" style="width:{v}%;background:{hex_c};"></div>
  </div>
  <div class="rc-summary">{_html.escape(summary)}</div>
  {severity_html}
  {events_html}
  {sources_html}
</div>
""", unsafe_allow_html=True)

# ── Individual gauges ─────────────────────────────────────────────────────────
st.markdown('<div id="sec-gauges" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="sec-heading"><div class="sh-icon p">🔬</div> Individual Risk Gauges</div>',
            unsafe_allow_html=True)

try:
    charts    = plot_all_risk_gauges(risk_scores)
    chart_keys = list(charts.keys())
    row1 = st.columns(3)
    for i in range(min(3, len(chart_keys))):
        key = chart_keys[i]
        fig = charts[key]
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#ffffff")
        with row1[i]:
            st.plotly_chart(fig, use_container_width=True)
    if len(chart_keys) > 3:
        remaining = chart_keys[3:]
        n_rem = len(remaining)
        pad   = (3 - n_rem) // 2
        row2  = st.columns(3)
        for i, key in enumerate(remaining):
            fig = charts[key]
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ffffff")
            with row2[pad + i]:
                st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(f"Gauge error: {e}")

# ── Key signals ───────────────────────────────────────────────────────────────
st.markdown('<div id="sec-signals" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="sec-heading"><div class="sh-icon r">🚨</div> Key Risk Signals</div>',
            unsafe_allow_html=True)
st.markdown('<div class="dsec">', unsafe_allow_html=True)
if signals:
    sig_html = "".join(
        f'<div class="sig-item"><span class="sig-ico">⚡</span>{_html.escape(s)}</div>'
        for s in signals
    )
    st.markdown(sig_html, unsafe_allow_html=True)
else:
    st.markdown(
        '<div style="background:rgba(0,230,118,0.07);border:1px solid rgba(0,230,118,0.2);'
        'border-radius:8px;padding:14px 18px;color:#00e676;font-size:15px;font-weight:500;">'
        '✅ No major risk signals detected.</div>',
        unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── Gaps & Recommendations ────────────────────────────────────────────────────
col_g, col_r = st.columns(2)

with col_g:
    st.markdown('<div id="sec-gaps" class="sec-anchor"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-heading"><div class="sh-icon a">🕳️</div> Identified Gaps</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="dsec">', unsafe_allow_html=True)
    if gaps:
        st.markdown(
            "".join(f'<div class="gi"><span class="gi-dot-a">◆</span>'
                    f'<span>{_html.escape(g)}</span></div>' for g in gaps),
            unsafe_allow_html=True)
    else:
        st.markdown('<div class="gi" style="color:#6b7fa3;">No major gaps identified.</div>',
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_r:
    st.markdown('<div id="sec-recs" class="sec-anchor"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-heading"><div class="sh-icon g">✅</div> Recommendations</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="dsec">', unsafe_allow_html=True)
    if recommendations:
        st.markdown(
            "".join(f'<div class="gi"><span class="gi-dot-g">▶</span>'
                    f'<span>{_html.escape(r)}</span></div>' for r in recommendations),
            unsafe_allow_html=True)
    else:
        st.markdown('<div class="gi" style="color:#6b7fa3;">No recommendations available.</div>',
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Download ──────────────────────────────────────────────────────────────────
st.markdown('<div id="sec-download" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="sec-heading"><div class="sh-icon b">📥</div> Download Report</div>',
            unsafe_allow_html=True)
st.markdown('<div class="dsec">', unsafe_allow_html=True)
st.markdown(f"""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
  <div style="width:48px;height:48px;border-radius:10px;background:rgba(68,138,255,0.12);
       display:flex;align-items:center;justify-content:center;font-size:24px;">📄</div>
  <div>
    <div style="font-size:16px;font-weight:600;color:#fff;">{_html.escape(vendor)} — Full Risk Report</div>
    <div style="font-size:13px;color:#6b7fa3;margin-top:3px;">
      All risk scores, filings, gaps and recommendations</div>
  </div>
</div>
""", unsafe_allow_html=True)
try:
    pdf_file = generate_pdf(result)
    with open(pdf_file, "rb") as f:
        st.download_button(
            "📥  Download PDF Report", f,
            file_name=f"vendor_report_{vendor.lower().replace(' ','_')}.pdf",
            mime="application/pdf",
        )
except Exception as e:
    st.error(f"PDF error: {e}")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    '<div style="text-align:center;padding:2.5rem 0 1rem;font-size:13px;color:#6b7fa3;">'
    'VendorIQ 2026 · AI-Powered Vendor Risk Analysis &amp; Due Diligence</div>',
    unsafe_allow_html=True)