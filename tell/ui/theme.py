"""Visual identity for Tell: editorial, warm-neutral, forest-green accent."""

from __future__ import annotations

import streamlit as st

INK = "#24262B"
INK_SOFT = "#5C6066"
MUTED = "#8A8E95"
IVORY = "#FBFAF7"
PANEL = "#F3F1EB"
LINE = "#E4E1D8"
GREEN = "#2F5D50"
GREEN_SOFT = "#DCE7E1"
AMBER = "#9A6B1F"
AMBER_SOFT = "#F3E7CF"
RUST = "#9C4A3A"
RUST_SOFT = "#F1DDD7"
SLATE = "#4E5D73"
SLATE_SOFT = "#E1E6EE"

SEVERITY_COLORS = {"critical": (RUST, RUST_SOFT), "high": (RUST, RUST_SOFT), "medium": (AMBER, AMBER_SOFT),
                   "low": (SLATE, SLATE_SOFT), "info": (INK_SOFT, PANEL)}
STATUS_LABELS = {"detected": "Detected", "needs_investigation": "Needs investigation", "verified": "Verified", "dismissed": "Dismissed"}
CLASS_LABELS = {"discrepancy": "Discrepancy", "suspected_risk": "Suspected risk", "observation": "Observation"}

PLOTLY_COLORS = [GREEN, "#8AA79B", AMBER, SLATE, RUST, "#B9B4A6"]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] {{ font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; color: {INK}; }}
.stApp {{ background: {IVORY}; }}
section[data-testid="stSidebar"] {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1.2rem; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }}

h1, h2, h3 {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600; letter-spacing: -0.01em; color: {INK}; }}
h1 {{ font-size: 1.85rem !important; margin-bottom: 0.2rem !important; }}
h2 {{ font-size: 1.3rem !important; margin-top: 1.6rem !important; }}
h3 {{ font-size: 1.05rem !important; }}

.tell-brand {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 1.55rem; font-weight: 600; color: {INK}; letter-spacing: -0.01em; }}
.tell-tagline {{ font-size: 0.78rem; color: {MUTED}; margin-top: -2px; margin-bottom: 14px; font-style: italic; }}
.tell-eyebrow {{ font-size: 0.72rem; letter-spacing: 0.09em; text-transform: uppercase; color: {MUTED}; font-weight: 600; margin-bottom: 4px; }}
.tell-sub {{ color: {INK_SOFT}; font-size: 0.95rem; margin-bottom: 1.2rem; }}
.tell-note {{ color: {MUTED}; font-size: 0.8rem; }}
.tell-caption {{ color: {INK_SOFT}; font-size: 0.85rem; line-height: 1.5; }}

.tell-kpi {{ padding: 14px 0 10px 0; border-top: 1px solid {LINE}; }}
.tell-kpi .label {{ font-size: 0.74rem; letter-spacing: 0.06em; text-transform: uppercase; color: {MUTED}; font-weight: 600; }}
.tell-kpi .value {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 1.7rem; font-weight: 600; color: {INK}; line-height: 1.15; margin-top: 4px; }}
.tell-kpi .delta {{ font-size: 0.8rem; color: {INK_SOFT}; margin-top: 2px; }}

.tell-pill {{ display: inline-block; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
             padding: 2px 8px; border-radius: 999px; margin-right: 6px; vertical-align: middle; }}

.tell-row {{ padding: 12px 0; border-bottom: 1px solid {LINE}; }}
.tell-row .title {{ font-weight: 600; font-size: 0.97rem; color: {INK}; }}
.tell-row .meta {{ color: {INK_SOFT}; font-size: 0.84rem; margin-top: 2px; }}

.tell-divider {{ border-top: 1px solid {LINE}; margin: 1.2rem 0; }}
.tell-panel {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; padding: 16px 18px; }}

div[data-testid="stMetric"] {{ background: transparent; }}
.stButton > button {{ border-radius: 8px; border: 1px solid {LINE}; background: #fff; color: {INK}; font-weight: 500; }}
.stButton > button:hover {{ border-color: {GREEN}; color: {GREEN}; }}
.stButton > button[kind="primary"] {{ background: {GREEN}; border-color: {GREEN}; color: #fff; }}
.stButton > button[kind="primary"]:hover {{ background: #264c41; }}
div[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 8px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 18px; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ padding: 8px 0; color: {INK_SOFT}; }}
.stTabs [aria-selected="true"] {{ color: {GREEN}; border-bottom: 2px solid {GREEN}; }}
div[data-testid="stExpander"] {{ border: 1px solid {LINE}; border-radius: 8px; background: #fff; }}
footer {{ visibility: hidden; }}
#MainMenu {{ visibility: hidden; }}
div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {{ visibility: hidden; height: 0; }}
header[data-testid="stHeader"] {{ background: transparent; height: 2.2rem; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{ padding: 4px 8px; border-radius: 6px; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span {{ color: {INK}; font-size: 0.92rem; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{ background: #E9E6DD; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def plotly_layout(fig, height: int = 320, legend: bool = True):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=24, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color=INK_SOFT), colorway=PLOTLY_COLORS,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)) if legend else dict(),
        showlegend=legend, hoverlabel=dict(bgcolor="#fff", font=dict(color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(size=11), title=None)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE, tickfont=dict(size=11), title=None)
    return fig
