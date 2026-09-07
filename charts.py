"""
charts.py - Plotly Visualizations (SK-VDD-001 Compliant)
---------------------------------------------------------
Features:
- SK-VDD-001 4-Tier Color Mapping:
  * Low (0-24): Green #10b981
  * Medium (25-49): Amber #f59e0b
  * High (50-74): Orange #f97316
  * Critical (75-100): Red #ef4444
- 5-Dimension Radar (Spider) Chart with Category Weights
- Overall Risk Gauge Indicator
- Category Proportions Donut Chart
"""

import pandas as pd
import plotly.graph_objects as go

BG_TRANSPARENT = "rgba(0,0,0,0)"
FONT_FAMILY = "Plus Jakarta Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
FONT_COLOR = "#f1f5f9"
FONT_MUTED = "#94a3b8"

# 4-Tier Palette per SK-VDD-001 Section 7.3
TIER_COLORS = {
    "Low": "#10b981",      # Green (0-24)
    "Medium": "#f59e0b",   # Amber (25-49)
    "High": "#f97316",     # Orange (50-74)
    "Critical": "#ef4444"  # Red (75-100)
}

CATEGORY_COLORS = {
    "Financial (30%)": "#10b981",
    "Reputation (20%)": "#38bdf8",
    "Key Person (20%)": "#c084fc",
    "Tech & Cyber (20%)": "#f59e0b",
    "Compliance (10%)": "#f43f5e",
}

GAUGE_STEPS = [
    {"range": [0, 24], "color": "rgba(16, 185, 129, 0.12)"},
    {"range": [24, 49], "color": "rgba(245, 158, 11, 0.12)"},
    {"range": [49, 74], "color": "rgba(249, 115, 22, 0.14)"},
    {"range": [74, 100], "color": "rgba(239, 68, 68, 0.18)"},
]


def _get_tier_info(score: float) -> tuple:
    s = int(round(score))
    if s <= 24:
        return "LOW RISK", TIER_COLORS["Low"]
    elif s <= 49:
        return "MEDIUM RISK", TIER_COLORS["Medium"]
    elif s <= 74:
        return "HIGH RISK", TIER_COLORS["High"]
    else:
        return "CRITICAL RISK", TIER_COLORS["Critical"]


def _base_layout(**kw) -> dict:
    base = dict(
        paper_bgcolor=BG_TRANSPARENT,
        plot_bgcolor=BG_TRANSPARENT,
        font=dict(family=FONT_FAMILY, color=FONT_COLOR, size=12),
        showlegend=False,
    )
    base.update(kw)
    return base


# ── 1. Overall Risk Gauge ──────────────────────────────────────────────────────

def plot_overall_gauge(score: float) -> go.Figure:
    score = max(0.0, min(float(score), 100.0))
    label, color = _get_tier_info(score)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(
            font=dict(family="JetBrains Mono, monospace", size=52, color=color),
        ),
        title=dict(
            text="<b>Overall Vendor Risk Score</b>",
            font=dict(family=FONT_FAMILY, size=14, color=FONT_MUTED),
        ),
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=1,
                tickcolor=FONT_MUTED,
                tickfont=dict(color=FONT_MUTED, size=10, family=FONT_FAMILY),
                tickvals=[0, 25, 50, 75, 100],
                showticklabels=True,
            ),
            bgcolor="rgba(255,255,255,0.02)",
            borderwidth=1,
            bordercolor="rgba(255,255,255,0.08)",
            steps=GAUGE_STEPS,
            bar=dict(color=color, thickness=0.08),
            threshold=dict(
                line=dict(color=color, width=4),
                thickness=0.85,
                value=score,
            ),
        ),
    ))

    fig.add_annotation(
        x=0.5, y=0.08,
        text=f'<b style="color:{color};font-size:13px;letter-spacing:1.8px;">{label}</b>',
        showarrow=False, xref="paper", yref="paper",
    )

    fig.update_layout(**_base_layout(
        height=280,
        margin=dict(t=50, b=35, l=35, r=35),
    ))
    return fig


# ── 2. 5-Dimension Radar (Spider) Chart ───────────────────────────────────────

def plot_risk_radar(risk_scores: dict) -> go.Figure:
    categories = [
        "Financial<br>Viability (30%)",
        "Reputational<br>Media (20%)",
        "Key-Person &<br>Gov (20%)",
        "Technology &<br>Cyber (20%)",
        "Regulatory<br>Comp (10%)"
    ]
    raw_keys = ["financial", "reputation", "key_person", "cyber", "compliance"]
    values = [float(risk_scores.get(k, 20)) for k in raw_keys]
    
    # Close polygon
    categories_closed = categories + [categories[0]]
    values_closed = values + [values[0]]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill='toself',
        fillcolor='rgba(56, 189, 248, 0.16)',
        line=dict(color='#38bdf8', width=2.5),
        marker=dict(size=7, color='#38bdf8', symbol='circle'),
        name='SK-VDD-001 Risk',
        hovertemplate="<b>%{theta}</b><br>Score: %{r}/100<extra></extra>"
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[25, 50, 75, 100],
                tickfont=dict(size=9, color=FONT_MUTED),
                gridcolor="rgba(255,255,255,0.08)",
                linecolor="rgba(255,255,255,0.12)",
            ),
            angularaxis=dict(
                tickfont=dict(size=11, color=FONT_COLOR, family=FONT_FAMILY),
                gridcolor="rgba(255,255,255,0.08)",
                linecolor="rgba(255,255,255,0.12)",
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor=BG_TRANSPARENT,
        plot_bgcolor=BG_TRANSPARENT,
        height=320,
        margin=dict(t=35, b=35, l=45, r=45),
        showlegend=False,
    )
    return fig


# ── 3. Single Dimension Mini Gauge ───────────────────────────────────────────

def plot_gauge(score: float, title: str = "Risk Score", accent_color: str = None) -> go.Figure:
    score = max(0.0, min(float(score), 100.0))
    label, default_color = _get_tier_info(score)
    color = accent_color or default_color

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(
            font=dict(family="JetBrains Mono, monospace", size=34, color=color),
        ),
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(family=FONT_FAMILY, size=12, color=FONT_MUTED),
        ),
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=0,
                tickfont=dict(color=FONT_MUTED, size=9, family=FONT_FAMILY),
                tickvals=[0, 25, 50, 75, 100],
                showticklabels=True,
            ),
            bgcolor="rgba(255,255,255,0.02)",
            borderwidth=1,
            bordercolor="rgba(255,255,255,0.06)",
            steps=GAUGE_STEPS,
            bar=dict(color=color, thickness=0.08),
            threshold=dict(
                line=dict(color=color, width=3),
                thickness=0.82,
                value=score,
            ),
        ),
    ))

    fig.add_annotation(
        x=0.5, y=0.08,
        text=f'<span style="font-size:10px;color:{FONT_MUTED};letter-spacing:1.2px;">{label}</span>',
        showarrow=False, xref="paper", yref="paper",
    )

    fig.update_layout(**_base_layout(
        height=250,
        margin=dict(t=40, b=40, l=25, r=25),
    ))
    return fig


def plot_all_risk_gauges(risk_scores: dict) -> dict:
    label_map = {
        "financial": ("Financial Viability (30%)", "#10b981"),
        "reputation": ("Reputational Risk (20%)", "#38bdf8"),
        "key_person": ("Key-Person Risk (20%)", "#c084fc"),
        "cyber": ("Tech & Cyber (20%)", "#f59e0b"),
        "compliance": ("Compliance (10%)", "#f43f5e"),
    }
    charts = {}
    for key, (label, color) in label_map.items():
        val = risk_scores.get(key, 20)
        charts[key] = plot_gauge(float(val), label, accent_color=color)
    return charts


# ── 4. Donut Chart ────────────────────────────────────────────────────────────

def plot_overall_risk_pie(risk_scores: dict) -> go.Figure:
    labels = ["Financial (30%)", "Reputation (20%)", "Key Person (20%)", "Cyber (20%)", "Compliance (10%)"]
    values = [
        risk_scores.get("financial", 20),
        risk_scores.get("reputation", 20),
        risk_scores.get("key_person", 20),
        risk_scores.get("cyber", 20),
        risk_scores.get("compliance", 20),
    ]
    colors = ["#10b981", "#38bdf8", "#c084fc", "#f59e0b", "#f43f5e"]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.64,
        marker=dict(colors=colors, line=dict(color="#080c14", width=2.5)),
        textinfo="label+percent",
        textposition="outside",
        textfont=dict(family=FONT_FAMILY, size=11, color=FONT_COLOR),
        hovertemplate="<b>%{label}</b><br>Score: %{value}/100<br>Proportion: %{percent}<extra></extra>",
        pull=[0.02] * 5,
        rotation=90,
    ))

    avg_score = int(sum(values) / len(values)) if values else 20
    _, needle = _get_tier_info(avg_score)

    fig.add_annotation(
        x=0.5, y=0.5,
        text=(
            f'<span style="font-family:JetBrains Mono,monospace;font-size:26px;'
            f'font-weight:700;color:{needle};">{avg_score}</span>'
            f'<br><span style="font-size:9px;color:{FONT_MUTED};letter-spacing:1.2px;">AVERAGE SCORE</span>'
        ),
        showarrow=False, xref="paper", yref="paper", align="center",
    )

    fig.update_layout(**_base_layout(
        height=320,
        margin=dict(t=35, b=35, l=15, r=110),
        showlegend=True,
        legend=dict(
            orientation="v", x=1.02, y=0.5, xanchor="left",
            font=dict(family=FONT_FAMILY, size=11, color=FONT_COLOR),
            bgcolor="rgba(0,0,0,0)",
        ),
        title=dict(
            text="<b>Risk Dimension Proportions</b>",
            font=dict(family=FONT_FAMILY, size=13, color=FONT_MUTED),
            x=0.5, xanchor="center",
        ),
    ))
    return fig