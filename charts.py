# charts.py — fixed: proper gauge heights, no overlap, clean layout

import pandas as pd
import plotly.graph_objects as go

# ── Design tokens ────────────────────────────────────────────────────────────
BG_TRANSPARENT = "rgba(0,0,0,0)"
FONT_FAMILY    = "DM Sans, sans-serif"
FONT_COLOR     = "#e8f0fe"
FONT_MUTED     = "#6b7fa3"

CATEGORY_COLORS = {
    "Financial":  "#00e676",
    "Reputation": "#448aff",
    "Key Person": "#c77dff",
    "Cyber":      "#ffab40",
    "Compliance": "#ff5252",
}

GAUGE_STEPS = [
    {"range": [0,  40],  "color": "rgba(0,230,118,0.10)"},
    {"range": [40, 70],  "color": "rgba(255,171,64,0.10)"},
    {"range": [70, 100], "color": "rgba(255,82,82,0.10)"},
]

def _needle_color(score: float) -> str:
    if score <= 40:  return "#00e676"
    if score <= 70:  return "#ffab40"
    return "#ff5252"

def _risk_label(score: float) -> str:
    if score <= 40:  return "LOW"
    if score <= 70:  return "MEDIUM"
    return "HIGH"

def _base_layout(**kw) -> dict:
    base = dict(
        paper_bgcolor=BG_TRANSPARENT,
        plot_bgcolor =BG_TRANSPARENT,
        font=dict(family=FONT_FAMILY, color=FONT_COLOR, size=12),
        showlegend=False,
    )
    base.update(kw)
    return base

# ── DataFrame helper ─────────────────────────────────────────────────────────
def create_risk_dataframe(risk_scores: dict) -> pd.DataFrame:
    return pd.DataFrame([
        ("Financial",  risk_scores.get("financial",  50)),
        ("Reputation", risk_scores.get("reputation", 50)),
        ("Key Person", risk_scores.get("key_person", 50)),
        ("Cyber",      risk_scores.get("cyber",      50)),
        ("Compliance", risk_scores.get("compliance", 50)),
    ], columns=["Risk Type", "Score"])

# ── Overall gauge ────────────────────────────────────────────────────────────
def plot_overall_gauge(score: float) -> go.Figure:
    score  = max(0.0, min(float(score), 100.0))
    needle = _needle_color(score)
    label  = _risk_label(score)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(
            font=dict(family="JetBrains Mono, monospace", size=48, color=needle),
        ),
        title=dict(
            text=f"<b>Overall Risk Score</b>",
            font=dict(family=FONT_FAMILY, size=14, color=FONT_MUTED),
        ),
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=0,
                tickfont=dict(color=FONT_MUTED, size=10, family=FONT_FAMILY),
                tickvals=[0, 25, 50, 75, 100],
                showticklabels=True,
            ),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=GAUGE_STEPS,
            bar=dict(color=needle, thickness=0.07,
                     line=dict(color="rgba(0,0,0,0)", width=0)),
            threshold=dict(
                line=dict(color=needle, width=4),
                thickness=0.85,
                value=score,
            ),
        ),
    ))

    fig.add_annotation(
        x=0.5, y=0.10,
        text=f'<b style="color:{needle};font-size:13px;letter-spacing:2px;">{label} RISK</b>',
        showarrow=False, xref="paper", yref="paper",
    )

    fig.update_layout(**_base_layout(
        height=280,
        margin=dict(t=50, b=40, l=40, r=40),
    ))
    return fig

# ── Single category gauge ────────────────────────────────────────────────────
def plot_gauge(score: float, title: str = "Risk Score",
               accent_color: str = None) -> go.Figure:
    score  = max(0.0, min(float(score), 100.0))
    needle = accent_color or _needle_color(score)
    label  = _risk_label(score)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(
            font=dict(family="JetBrains Mono, monospace", size=36, color=needle),
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
                tickvals=[0, 50, 100],
                showticklabels=True,
            ),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=GAUGE_STEPS,
            bar=dict(color=needle, thickness=0.08,
                     line=dict(color="rgba(0,0,0,0)", width=0)),
            threshold=dict(
                line=dict(color=needle, width=3),
                thickness=0.82,
                value=score,
            ),
        ),
    ))

    fig.add_annotation(
        x=0.5, y=0.08,
        text=f'<span style="font-size:10px;color:{FONT_MUTED};letter-spacing:1.5px;">{label} RISK</span>',
        showarrow=False, xref="paper", yref="paper",
    )

    fig.update_layout(**_base_layout(
        # KEY FIX: tall enough so number + label + arc never overlap
        height=260,
        margin=dict(t=45, b=45, l=30, r=30),
    ))
    return fig

# ── All 5 individual gauges ───────────────────────────────────────────────────
def plot_all_risk_gauges(risk_scores: dict) -> dict:
    label_map = {
        "financial":  "Financial",
        "reputation": "Reputation",
        "key_person": "Key Person",
        "cyber":      "Cyber",
        "compliance": "Compliance",
    }
    charts = {}
    for key, value in risk_scores.items():
        label = label_map.get(key, key.capitalize())
        color = CATEGORY_COLORS.get(label, "#ffffff")
        fig   = plot_gauge(float(value), f"{label} Risk", accent_color=color)
        charts[key] = fig
    return charts

# ── Donut pie ────────────────────────────────────────────────────────────────
def plot_overall_risk_pie(risk_scores: dict) -> go.Figure:
    labels = ["Financial", "Reputation", "Key Person", "Cyber", "Compliance"]
    values = [
        risk_scores.get("financial",  50),
        risk_scores.get("reputation", 50),
        risk_scores.get("key_person", 50),
        risk_scores.get("cyber",      50),
        risk_scores.get("compliance", 50),
    ]
    colors = [CATEGORY_COLORS[l] for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.62,
        marker=dict(colors=colors, line=dict(color="#0b0f1a", width=3)),
        textinfo="label+percent",
        textposition="outside",
        textfont=dict(family=FONT_FAMILY, size=11, color=FONT_COLOR),
        hovertemplate="<b>%{label}</b><br>Score: %{value}<br>Share: %{percent}<extra></extra>",
        pull=[0.03] * 5,
        rotation=90,
    ))

    total = sum(values)
    fig.add_annotation(
        x=0.5, y=0.5,
        text=(
            f'<span style="font-family:JetBrains Mono,monospace;font-size:26px;'
            f'font-weight:700;color:#e8f0fe;">{total}</span>'
            f'<br><span style="font-size:10px;color:{FONT_MUTED};letter-spacing:1.5px;">TOTAL SCORE</span>'
        ),
        showarrow=False, xref="paper", yref="paper", align="center",
    )

    fig.update_layout(**_base_layout(
        height=320,
        margin=dict(t=40, b=40, l=20, r=120),
        showlegend=True,
        legend=dict(
            orientation="v", x=1.02, y=0.5, xanchor="left",
            font=dict(family=FONT_FAMILY, size=11, color=FONT_COLOR),
            bgcolor="rgba(0,0,0,0)",
        ),
        title=dict(
            text="<b>Risk Distribution</b>",
            font=dict(family=FONT_FAMILY, size=14, color=FONT_MUTED),
            x=0.5, xanchor="center",
        ),
    ))
    return fig

# ── Legacy compat ─────────────────────────────────────────────────────────────
def plot_pie_chart(df: pd.DataFrame) -> go.Figure:
    return plot_overall_risk_pie({
        "financial":  df[df["Risk Type"] == "Financial"]["Score"].values[0]  if len(df) > 0 else 50,
        "reputation": df[df["Risk Type"] == "Reputation"]["Score"].values[0] if len(df) > 1 else 50,
        "key_person": df[df["Risk Type"] == "Key Person"]["Score"].values[0] if len(df) > 2 else 50,
        "cyber":      df[df["Risk Type"] == "Cyber"]["Score"].values[0]      if len(df) > 3 else 50,
        "compliance": df[df["Risk Type"] == "Compliance"]["Score"].values[0] if len(df) > 4 else 50,
    })