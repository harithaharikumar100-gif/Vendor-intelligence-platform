"""
app.py - DRiskify (NIVETA Platform) — SK-VDD-001 Vendor Intelligence
---------------------------------------------------------------------
AI-Native Vendor Due Diligence & Intelligence Scraping Interface
Compliant with Skill Document SK-VDD-001 (Canadian & Global Scope)
"""

import streamlit as st
import html as _html
import json
import time
from normalizer import normalize_vendor_name, validate_business_number

# ── Safe Imports ──────────────────────────────────────────────────────────────
_import_errors = []

try:
    from services import get_vendor_analysis
except Exception as _e:
    _import_errors.append(f"services.py: {_e}")
    get_vendor_analysis = None

try:
    from charts import (
        plot_overall_gauge,
        plot_risk_radar,
        plot_all_risk_gauges,
        plot_overall_risk_pie
    )
except Exception as _e:
    _import_errors.append(f"charts.py: {_e}")
    plot_overall_gauge = plot_risk_radar = plot_all_risk_gauges = plot_overall_risk_pie = None

try:
    from pdf_generator import generate_pdf
except Exception as _e:
    _import_errors.append(f"pdf_generator.py: {_e}")
    generate_pdf = None

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DRiskify — NIVETA Vendor Intelligence (SK-VDD-001)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Cached Pipeline Runner ───────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def cached_vendor_analysis(vendor, industry, country, concerns, company_url, business_number, ticker):
    if not get_vendor_analysis:
        return {"error": "Services module failed to load."}, {}
    return get_vendor_analysis(
        vendor=vendor,
        industry=industry,
        country=country,
        concerns=concerns,
        company_url=company_url,
        business_number=business_number,
        ticker=ticker
    )

# ── Minimalist Modern Styling ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
  --bg-base:        #060911;
  --bg-card:        #0d1322;
  --bg-card-hover:  #141c30;
  --bg-sidebar:     #04060c;
  --tier-low:       #10b981;
  --tier-medium:    #f59e0b;
  --tier-high:      #f97316;
  --tier-critical:  #ef4444;
  --accent-blue:    #38bdf8;
  --text-primary:   #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted:     #64748b;
  --border:         #1a233a;
  --border-light:   #283554;
  --radius:         12px;
  --radius-sm:      8px;
}

html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg-base) !important;
  font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
  color: var(--text-primary) !important;
}

[data-testid="stSidebar"] {
  background: var(--bg-sidebar) !important;
  border-right: 1px solid var(--border) !important;
}

/* Brand Banner */
.brand-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 0 18px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 18px;
}
.brand-badge {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: 0 4px 14px rgba(2, 132, 199, 0.3);
}
.brand-name {
  font-size: 18px;
  font-weight: 800;
  color: #fff;
  letter-spacing: -0.3px;
}
.brand-skill {
  font-size: 10.5px;
  color: #38bdf8;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 1px;
}

/* Quick Search Badges */
.quick-chip {
  display: inline-block;
  background: #0d1322;
  border: 1px solid var(--border);
  color: #94a3b8;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  margin-right: 6px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-chip:hover {
  border-color: #38bdf8;
  color: #38bdf8;
}

/* Inputs */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] > div > div {
  background: #0d1322 !important;
  border: 1px solid var(--border-light) !important;
  border-radius: var(--radius-sm) !important;
  color: #f8fafc !important;
  font-size: 13.5px !important;
}

/* Buttons */
[data-testid="stButton"] button {
  background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
  color: #fff !important;
  font-weight: 700 !important;
  font-size: 13.5px !important;
  border: none !important;
  border-radius: 8px !important;
  padding: 0.65rem 1.25rem !important;
  box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25) !important;
  transition: all 0.2s ease !important;
}
[data-testid="stButton"] button:hover {
  transform: translateY(-1px) !important;
  opacity: 0.95 !important;
}

[data-testid="stDownloadButton"] button {
  background: rgba(56, 189, 248, 0.1) !important;
  color: #38bdf8 !important;
  border: 1px solid rgba(56, 189, 248, 0.3) !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
}

/* Rating Banner */
.rating-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-radius: var(--radius);
  margin-bottom: 20px;
  border: 1px solid;
}
.rating-banner.low {
  background: rgba(16, 185, 129, 0.07);
  border-color: rgba(16, 185, 129, 0.3);
  color: #10b981;
}
.rating-banner.medium {
  background: rgba(245, 158, 11, 0.07);
  border-color: rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}
.rating-banner.high {
  background: rgba(249, 115, 22, 0.07);
  border-color: rgba(249, 115, 22, 0.3);
  color: #f97316;
}
.rating-banner.critical {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.35);
  color: #ef4444;
}

.score-display {
  font-size: 42px;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
  line-height: 1;
}

/* Escalation Alert */
.escalation-box {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: var(--radius);
  padding: 14px 18px;
  margin-bottom: 20px;
  color: #fca5a5;
  font-size: 13.5px;
}
.escalation-box b { color: #ef4444; }

/* 5-Dimension KPI Grid */
.dim-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 22px;
}
@media(max-width: 1100px) {
  .dim-grid { grid-template-columns: repeat(3, 1fr); }
}
@media(max-width: 768px) {
  .dim-grid { grid-template-columns: repeat(2, 1fr); }
}

.dim-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  position: relative;
  overflow: hidden;
  transition: transform 0.2s, border-color 0.2s;
}
.dim-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-light);
}
.dim-card-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.dim-card-score {
  font-size: 28px;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 2px;
}
.dim-card-sub {
  font-size: 11.5px;
  color: var(--text-secondary);
}

/* Detail Card */
.detail-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  margin-bottom: 14px;
}
.detail-box-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.source-tag {
  display: inline-block;
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: #38bdf8;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  text-decoration: none;
  margin-right: 6px;
  margin-top: 5px;
}
.source-tag:hover {
  background: rgba(56, 189, 248, 0.18);
}
</style>
""", unsafe_allow_html=True)

if _import_errors:
    st.error("⚠️ Initialization errors detected:")
    for err in _import_errors:
        st.code(err)
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="brand-header">
      <div class="brand-badge">🛡️</div>
      <div>
        <div class="brand-name">DRiskify</div>
        <div class="brand-skill">NIVETA Platform • SK-VDD-001</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Preset vendor quick select
    preset_col = st.selectbox(
        "⚡ Quick Select Enterprise",
        options=[
            "— Select Preset or Type Below —",
            "Shopify Inc.",
            "BlackBerry Limited",
            "CGI Inc.",
            "OpenText Corporation",
            "Royal Bank of Canada (RBC)",
            "Constellation Software Inc.",
            "Thomson Reuters",
            "Bombardier Inc."
        ],
        index=0
    )

    default_name = "Shopify Inc."
    default_url = "https://www.shopify.com"
    default_ticker = "SHOP"
    default_industry = "Technology & SaaS"

    if preset_col == "BlackBerry Limited":
        default_name, default_url, default_ticker, default_industry = "BlackBerry Limited", "https://www.blackberry.com", "BB", "Technology & SaaS"
    elif preset_col == "CGI Inc.":
        default_name, default_url, default_ticker, default_industry = "CGI Inc.", "https://www.cgi.com", "GIB.A", "Technology & SaaS"
    elif preset_col == "OpenText Corporation":
        default_name, default_url, default_ticker, default_industry = "OpenText Corporation", "https://www.opentext.com", "OTEX", "Technology & SaaS"
    elif preset_col == "Royal Bank of Canada (RBC)":
        default_name, default_url, default_ticker, default_industry = "Royal Bank of Canada", "https://www.rbc.com", "RY", "Banking, Financial & FinTech"
    elif preset_col == "Constellation Software Inc.":
        default_name, default_url, default_ticker, default_industry = "Constellation Software", "https://www.csisoftware.com", "CSU", "Technology & SaaS"
    elif preset_col == "Thomson Reuters":
        default_name, default_url, default_ticker, default_industry = "Thomson Reuters", "https://www.thomsonreuters.com", "TRI", "Telecommunications & Media"
    elif preset_col == "Bombardier Inc.":
        default_name, default_url, default_ticker, default_industry = "Bombardier Inc.", "https://www.bombardier.com", "BBD.B", "Manufacturing & Supply Chain"

    with st.form("sk_vdd_form"):
        st.markdown("<p style='font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;'>Vendor Identification (Section 4)</p>", unsafe_allow_html=True)
        
        vendor_name_in = st.text_input("Vendor Entity Name *", value=default_name, help="Legal or trade name of Canadian/international entity")
        
        # Show normalized preview
        if vendor_name_in:
            norm_preview = normalize_vendor_name(vendor_name_in)
            if norm_preview["normalized_name"] != vendor_name_in.strip():
                st.caption(f"🔍 Normalised: `{norm_preview['normalized_name']}` | Suffix stripped")

        industry_opts = [
            "Technology & SaaS",
            "Banking, Financial & FinTech",
            "E-Commerce & Retail",
            "Healthcare & MedTech",
            "Telecommunications & Media",
            "Energy, Mining & Utilities",
            "Manufacturing & Supply Chain",
            "Professional Services & Consulting",
            "Public Sector & Non-Profit"
        ]
        ind_idx = industry_opts.index(default_industry) if default_industry in industry_opts else 0
        industry_in = st.selectbox("Industry Domain *", options=industry_opts, index=ind_idx)

        country_in = st.selectbox(
            "Primary Jurisdiction (CBCA / Provincial) *",
            options=["Canada", "Canada, Ontario", "Canada, Quebec", "Canada, British Columbia", "United States", "Global / International"],
            index=0
        )

        with st.expander("⚡ Optional Identifiers & Context (Section 4.3)", expanded=False):
            bn_in = st.text_input("CRA Business Number (9-digit BN)", value="", placeholder="e.g. 123456789")
            url_in = st.text_input("Primary Domain / URL", value=default_url, placeholder="e.g. https://www.vendor.com")
            ticker_in = st.text_input("Public Exchange Ticker (TSX/NYSE)", value=default_ticker, placeholder="e.g. SHOP, SHOP.TO")
            concerns_in = st.text_area("Due Diligence Mandate / Directives", value="", placeholder="e.g. Verify CCCS cyber advisories, OSFI compliance, or recent data breaches")

        submitted = st.form_submit_button("🚀 Run SK-VDD-001 Intelligence")

# ── Session State ─────────────────────────────────────────────────────────────
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "raw_signals" not in st.session_state:
    st.session_state.raw_signals = None

if submitted:
    if not vendor_name_in.strip():
        st.error("Please provide a valid Vendor Entity Name.")
    else:
        with st.status(f"Executing SK-VDD-001 Due Diligence on **{vendor_name_in}**...", expanded=True) as status:
            st.write("1️⃣ Input Normalisation & Jurisdiction Confirmation (CBCA / Provincial)...")
            time.sleep(0.2)
            st.write("2️⃣ Parallel Scraping: SEDAR+, CBCA, CBC, Globe & Mail, CanLII, LinkedIn...")
            time.sleep(0.2)
            st.write("3️⃣ Cyber & Compliance Checks: CCCS (cyber.gc.ca), CISA KEV, OSFI, FINTRAC, CSA...")
            
            result, raw_data = cached_vendor_analysis(
                vendor=vendor_name_in.strip(),
                industry=industry_in,
                country=country_in,
                concerns=concerns_in.strip(),
                company_url=url_in.strip(),
                business_number=bn_in.strip(),
                ticker=ticker_in.strip()
            )
            
            st.write("4️⃣ Gen-AI Signal Taxonomy Extraction & 5-Dimension Weighted Scoring...")
            st.session_state.analysis_result = result
            st.session_state.raw_signals = raw_data
            status.update(label=f"✅ SK-VDD-001 Complete: {result.get('vendor_name', vendor_name_in)}", state="complete", expanded=False)

# ── Main View ─────────────────────────────────────────────────────────────────
result = st.session_state.analysis_result

if not result:
    st.markdown("""
    <div style="text-align:center;padding:4.5rem 1.5rem;">
      <div style="font-size:56px;margin-bottom:0.75rem;">🛡️</div>
      <h1 style="font-size:28px;color:#fff;font-weight:800;letter-spacing:-0.5px;">DRiskify — NIVETA Platform</h1>
      <p style="color:#38bdf8;font-size:13px;font-family:'JetBrains Mono',monospace;letter-spacing:1px;margin-bottom:1.25rem;">
        SKILL SPECIFICATION: SK-VDD-001 | VENDOR INTELLIGENCE SCRAPING
      </p>
      <p style="color:#94a3b8;font-size:14.5px;max-width:620px;margin:0 auto 2rem auto;line-height:1.6;">
        AI-native autonomous vendor due diligence module querying <b>SEDAR+, CBCA, Tier-1 Canadian media, CCCS, CISA, OSFI, FINTRAC,</b> and <b>CanLII</b> across a 36-month lookback window.
      </p>
      <div style="display:inline-flex;gap:10px;background:#0d1322;border:1px solid #1a233a;padding:8px 18px;border-radius:30px;font-size:12.5px;color:#94a3b8;">
        <span>📊 Fin 30%</span>
        <span>•</span>
        <span>📰 Rep 20%</span>
        <span>•</span>
        <span>👤 KP 20%</span>
        <span>•</span>
        <span>🛡️ Cyber 20%</span>
        <span>•</span>
        <span>⚖️ Comp 10%</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    if "error" in result and not result.get("risk_scores"):
        st.error(f"Due diligence run failed: {result['error']}")
        st.stop()

    vendor_disp = result.get("vendor_name", "Target Vendor")
    overall_score = result.get("overall_score", 20)
    rating = result.get("overall_risk_rating", "Low")
    traffic = result.get("traffic_light", "Green")
    action = result.get("recommended_action", "Standard onboarding may proceed.")
    conf = result.get("confidence_score", 85)
    hits = result.get("total_hits", 0)
    scores = result.get("risk_scores", {})
    profile = result.get("company_profile", {})
    escalations = result.get("automatic_escalations", [])

    rating_class = rating.lower()
    color_map = {"Low": "#10b981", "Medium": "#f59e0b", "High": "#f97316", "Critical": "#ef4444"}
    tier_hex = color_map.get(rating, "#10b981")

    # 1. Automatic Escalation Alert (Section 10.1)
    if escalations:
        st.markdown(f"""
        <div class="escalation-box">
          <b>⚠️ AUTOMATIC SENIOR RISK REVIEW ESCALATIONS TRIGGERED (SK-VDD-001 Section 10.1):</b>
          <ul style="margin:6px 0 0 16px;padding:0;">
            {''.join(f'<li>{e}</li>' for e in escalations)}
          </ul>
        </div>
        """, unsafe_allow_html=True)

    # 2. Executive Rating Banner
    st.markdown(f"""
    <div class="rating-banner {rating_class}">
      <div>
        <h2 style="font-size:22px;font-weight:800;margin:0;color:#fff;">{vendor_disp}</h2>
        <p style="margin:4px 0 0 0;font-size:13px;color:#94a3b8;">
          Jurisdiction: <b>{result.get('registration_country', 'Canada')}</b> | Industry: <b>{profile.get('industry', 'Technology')}</b> | Scope: <b>Trailing 36m</b> | Data Confidence: <b>{conf}%</b>
        </p>
        <p style="margin:6px 0 0 0;font-size:12.5px;color:{tier_hex};font-weight:600;">
          Recommended Action: {action}
        </p>
      </div>
      <div style="text-align:right;">
        <div class="score-display" style="color:{tier_hex};">{overall_score}</div>
        <div style="font-size:11px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:{tier_hex};">
          {rating.upper()} RISK ({traffic.upper()})
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 3. 5-Dimension Scorecard Grid (Section 7.2)
    st.markdown(f"""
    <div class="dim-grid">
      <div class="dim-card">
        <div class="dim-card-header">Financial Viability</div>
        <div class="dim-card-score" style="color:#10b981;">{scores.get('financial', 20)}<span style="font-size:13px;color:#64748b;">/100</span></div>
        <div class="dim-card-sub">Weight: 30% • Solvency & Filings</div>
      </div>
      <div class="dim-card">
        <div class="dim-card-header">Reputational Risk</div>
        <div class="dim-card-score" style="color:#38bdf8;">{scores.get('reputation', 20)}<span style="font-size:13px;color:#64748b;">/100</span></div>
        <div class="dim-card-sub">Weight: 20% • Adverse Media (36m)</div>
      </div>
      <div class="dim-card">
        <div class="dim-card-header">Key-Person & Gov</div>
        <div class="dim-card-score" style="color:#c084fc;">{scores.get('key_person', 20)}<span style="font-size:13px;color:#64748b;">/100</span></div>
        <div class="dim-card-sub">Weight: 20% • Sanctions & Bench</div>
      </div>
      <div class="dim-card">
        <div class="dim-card-header">Technology & Cyber</div>
        <div class="dim-card-score" style="color:#f59e0b;">{scores.get('cyber', 20)}<span style="font-size:13px;color:#64748b;">/100</span></div>
        <div class="dim-card-sub">Weight: 20% • CCCS, CISA, CVEs</div>
      </div>
      <div class="dim-card">
        <div class="dim-card-header">Regulatory Compliance</div>
        <div class="dim-card-score" style="color:#f43f5e;">{scores.get('compliance', 20)}<span style="font-size:13px;color:#64748b;">/100</span></div>
        <div class="dim-card-sub">Weight: 10% • OSFI, FINTRAC, CSA</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 4. Interactive Tabs
    tab_overview, tab_signals, tab_entity, tab_mitigation, tab_export = st.tabs([
        "📊 Executive Overview",
        "🛡️ 5-Dimension Signal Taxonomy",
        "🏢 Corporate Registry & Filings",
        "🎯 Strategic Mitigations & Gaps",
        "📄 Official Reports & JSON Export"
    ])

    # ── TAB 1: Executive Overview ─────────────────────────────────────────────
    with tab_overview:
        col_g, col_r, col_d = st.columns([1, 1.2, 1])
        with col_g:
            if plot_overall_gauge:
                st.plotly_chart(plot_overall_gauge(overall_score), use_container_width=True)
        with col_r:
            if plot_risk_radar:
                st.plotly_chart(plot_risk_radar(scores), use_container_width=True)
        with col_d:
            if plot_overall_risk_pie:
                st.plotly_chart(plot_overall_risk_pie(scores), use_container_width=True)

        st.markdown("### 📝 Holistic Analyst Review (Section 8)")
        st.markdown(f"""
        <div style="background:#0d1322;border:1px solid #1a233a;padding:16px;border-radius:10px;font-size:14px;color:#cbd5e1;line-height:1.6;">
          {result.get('analyst_notes', 'Due diligence sweep executed per SK-VDD-001 specification.')}
        </div>
        """, unsafe_allow_html=True)

    # ── TAB 2: 5-Dimension Signal Taxonomy ────────────────────────────────────
    with tab_signals:
        st.markdown("### 🔍 Granular Signal Extraction & Attribution (Section 6 & 8)")

        explanations = result.get("explanations", {})
        evidence_links = result.get("evidence_links", {})

        dims_meta = [
            ("financial", "Financial Viability (30% Weight)", "#10b981", "SEDAR+, CBCA Registry, Solvency, Liquidity"),
            ("reputation", "Reputational Risk (20% Weight)", "#38bdf8", "CBC, Globe & Mail, Financial Post, CanLII Litigation"),
            ("key_person", "Key-Person & Governance (20% Weight)", "#c084fc", "SEDI Insiders, LinkedIn, OFAC/OSFI Sanctions"),
            ("cyber", "Technology & Cyber Risk (20% Weight)", "#f59e0b", "CCCS (cyber.gc.ca), CISA KEV, NVD CVSS >= 7.0"),
            ("compliance", "Regulatory Compliance (10% Weight)", "#f43f5e", "OSFI Orders, FINTRAC AMPs, CSA Enforcement, OPC"),
        ]

        for cat_k, title, color, sources in dims_meta:
            c_score = scores.get(cat_k, 20)
            exp = explanations.get(cat_k, {})
            links = evidence_links.get(cat_k, [])

            st.markdown(f"""
            <div class="detail-box">
              <div class="detail-box-hdr">
                <div style="font-size:15px;font-weight:700;color:#fff;display:flex;align-items:center;gap:8px;">
                  <span style="width:10px;height:10px;border-radius:50%;background:{color};display:inline-block;"></span>
                  {title}
                  <span style="font-size:11.5px;color:#64748b;font-weight:400;">({sources})</span>
                </div>
                <div style="background:#060911;border:1px solid {color};color:{color};font-family:monospace;font-weight:700;padding:3px 10px;border-radius:15px;font-size:12px;">
                  Score: {c_score}/100
                </div>
              </div>
              <p style="font-size:13.5px;color:#cbd5e1;line-height:1.5;margin-bottom:8px;">
                <b>Assessment:</b> {exp.get('summary', 'Standard operational posture.')}
              </p>
            """, unsafe_allow_html=True)

            # Render category specific structured signals
            if cat_k == "financial" and exp.get("signals"):
                for s in exp["signals"]:
                    st.markdown(f"• **[{s.get('category')}]** {s.get('indicator')} *(Severity: {s.get('severity')})*")
            elif cat_k == "reputation" and exp.get("articles"):
                for a in exp["articles"]:
                    st.markdown(f"• **[{a.get('source')}]** {a.get('headline')} *({a.get('date')})*")
            elif cat_k == "key_person" and exp.get("persons"):
                for p in exp["persons"]:
                    st.markdown(f"• **{p.get('name')}** ({p.get('role')}): Flags: {', '.join(p.get('flags', ['Clean']))}")
            elif cat_k == "cyber" and exp.get("signals"):
                for s in exp["signals"]:
                    st.markdown(f"• **[{s.get('category')}]** {s.get('indicator')} *(Severity: {s.get('severity')})*")
            elif cat_k == "compliance" and exp.get("signals"):
                for s in exp["signals"]:
                    st.markdown(f"• **[{s.get('authority')}]** {s.get('action')} *(Severity: {s.get('severity')})*")

            if links:
                chips = "".join([f'<a href="{u}" target="_blank" class="source-tag">🔗 {u.split("/")[2] if "://" in u else u[:25]}</a>' for u in links[:4]])
                st.markdown(f"<div style='margin-top:8px;'><span style='font-size:11px;color:#64748b;text-transform:uppercase;font-weight:700;'>Sources:</span> {chips}</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

    # ── TAB 3: Corporate Registry & Filings ───────────────────────────────────
    with tab_entity:
        col_c1, col_c2 = st.columns([1, 1.2])

        with col_c1:
            st.markdown("### 🏢 Corporate Registry Metadata")
            prof_dict = {
                "Normalized Entity Name": vendor_disp,
                "Raw Input Name": result.get("raw_vendor_name", vendor_disp),
                "Jurisdiction": result.get("registration_country", "Canada"),
                "CRA Business Number (BN)": result.get("business_number") or "Inferred from Registry",
                "Executive Leadership (CEO)": profile.get("ceo", "Not Available"),
                "Corporate Founder": profile.get("founder", "Not Available"),
                "Incorporation Year": profile.get("founded", "Not Available"),
                "Principal Hub / HQ": profile.get("headquarters", "Not Available"),
                "Estimated Employees": profile.get("employees", "Not Available"),
            }
            for k, v in prof_dict.items():
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1a233a;font-size:13.5px;">
                  <span style="color:#94a3b8;">{k}</span>
                  <span style="color:#fff;font-weight:600;">{v}</span>
                </div>
                """, unsafe_allow_html=True)

        with col_c2:
            st.markdown("### 📈 Verified Financial Ratios (SEDAR+ / Public Filings)")
            fin_metrics = profile.get("financial_metrics", {})
            if fin_metrics:
                for k, v in fin_metrics.items():
                    st.markdown(f"""
                    <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1a233a;font-size:13.5px;">
                      <span style="color:#94a3b8;">{k.replace('_', ' ').title()}</span>
                      <span style="color:#10b981;font-family:monospace;font-weight:700;">{v}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Private entity or unlisted vendor. Financial viability score computed from web intelligence disclosures.")

            st.markdown("#### 📚 Data Sources Queried (Section 5)")
            sources = result.get("data_sources_used", [])
            for s in sources:
                st.markdown(f"<span style='font-size:12.5px;color:#94a3b8;'>• {s}</span>", unsafe_allow_html=True)

    # ── TAB 4: Strategic Mitigations & Gaps ────────────────────────────────────
    with tab_mitigation:
        col_m1, col_m2 = st.columns([1.2, 1])

        with col_m1:
            st.markdown("### 🎯 Strategic Risk Mitigations (SK-VDD-001)")
            recs = result.get("recommendations", [])
            for i, r in enumerate(recs, 1):
                st.markdown(f"""
                <div style="display:flex;align-items:flex-start;gap:12px;padding:12px 14px;background:#0d1322;border:1px solid #1a233a;border-radius:8px;margin-bottom:8px;">
                  <div style="background:#0284c7;color:#fff;font-weight:800;border-radius:50%;width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;">{i}</div>
                  <div style="font-size:13.5px;color:#f8fafc;line-height:1.5;">{r}</div>
                </div>
                """, unsafe_allow_html=True)

        with col_m2:
            st.markdown("### ⚠️ Data Gaps & Verification Items (Section 9.2)")
            gaps = result.get("data_gaps", [])
            for g in gaps:
                st.markdown(f"""
                <div style="display:flex;align-items:flex-start;gap:8px;padding:10px 12px;background:rgba(245, 158, 11, 0.05);border:1px solid rgba(245, 158, 11, 0.2);border-radius:6px;margin-bottom:6px;font-size:13px;color:#cbd5e1;">
                  <span style="color:#f59e0b;">[ ]</span>
                  <span>{g}</span>
                </div>
                """, unsafe_allow_html=True)

    # ── TAB 5: Official Reports & JSON Export ──────────────────────────────────
    with tab_export:
        st.markdown("### 📄 Export Official SK-VDD-001 Deliverables")
        
        c_pdf, c_json = st.columns(2)

        with c_pdf:
            st.markdown("#### SK-VDD-001 PDF Summary Report")
            st.caption("Official two-pass report with Executive Scorecard, Escalation Flags, Signal Taxonomy, and Sign-off Table.")
            
            if generate_pdf:
                pdf_name = f"DRiskify_SK_VDD_001_{vendor_disp.lower().replace(' ', '_')}.pdf"
                try:
                    pdf_path = generate_pdf(result, filename=pdf_name, vendor_name=vendor_disp)
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="📥 Download Official SK-VDD-001 PDF Report",
                        data=pdf_bytes,
                        file_name=pdf_name,
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as ex:
                    st.error(f"Error compiling PDF: {ex}")

        with c_json:
            st.markdown("#### Canonical JSON Payload (Section 8)")
            st.caption("Full JSON data contract for enterprise GRC / SIEM integration.")
            
            json_payload = json.dumps(result, indent=2)
            st.download_button(
                label="📥 Export Canonical JSON Data",
                data=json_payload,
                file_name=f"DRiskify_SK_VDD_001_{vendor_disp.lower().replace(' ', '_')}.json",
                mime="application/json",
                use_container_width=True
            )

        with st.expander("🔍 View Canonical JSON Schema (Section 8)", expanded=False):
            st.json(result)