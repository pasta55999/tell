"""Design tokens and global styles for Tell.

Palette: cool-white canvas, deep-ink text, midnight-navy sidebar, electric cobalt as the primary
accent, violet as a secondary analytical accent, emerald for favourable/verified signals and
coral for discrepancies and risk. Colour always carries meaning; it is never decoration.
"""

from __future__ import annotations

import streamlit as st

# --- colour tokens --------------------------------------------------------
CANVAS = "#F7F8FC"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#EEF0F9"
HIGHLIGHT = "#E8EAFF"
LINE = "#E1E5EF"
LINE_STRONG = "#C9D0E3"

INK = "#17213A"
INK_SOFT = "#4C5670"
MUTED = "#7A849F"

NAVY = "#111831"
NAVY_RAISED = "#1C2546"
NAVY_LINE = "#27315A"
NAVY_TEXT = "#E6E9F5"
NAVY_MUTED = "#8F9AC0"

COBALT = "#4F5DFF"
COBALT_DEEP = "#3A47E0"
COBALT_SOFT = "#E8EAFF"
VIOLET = "#8067F8"
VIOLET_SOFT = "#EEE9FF"
EMERALD = "#0B9F78"
EMERALD_SOFT = "#DDF4EC"
CORAL = "#E04E4E"          # darkened from #F06464 for AA text contrast on light tints
CORAL_SOFT = "#FDE3E3"
AMBER = "#B9731A"
AMBER_SOFT = "#FBEBD0"
SLATE = "#5E6B8C"
SLATE_SOFT = "#E6EAF3"

# Semantic maps -------------------------------------------------------------
SEVERITY_COLORS = {"critical": (CORAL, CORAL_SOFT), "high": (CORAL, CORAL_SOFT), "medium": (AMBER, AMBER_SOFT),
                   "low": (SLATE, SLATE_SOFT), "info": (INK_SOFT, SURFACE_ALT)}
SEVERITY_BAR = {"critical": CORAL, "high": CORAL, "medium": AMBER, "low": SLATE, "info": LINE_STRONG}
PRIORITY_COLORS = {"high": (CORAL, CORAL_SOFT), "medium": (AMBER, AMBER_SOFT), "low": (SLATE, SLATE_SOFT)}
STATUS_LABELS = {"detected": "Detected", "needs_investigation": "Needs investigation", "verified": "Verified", "dismissed": "Dismissed"}
STATUS_COLORS = {"detected": (INK_SOFT, SURFACE_ALT), "needs_investigation": (COBALT_DEEP, COBALT_SOFT), "verified": (EMERALD, EMERALD_SOFT), "dismissed": (MUTED, SURFACE_ALT)}
CLASS_LABELS = {"discrepancy": "Discrepancy", "suspected_risk": "Suspected risk", "observation": "Observation"}
CLASS_COLORS = {"discrepancy": (COBALT_DEEP, COBALT_SOFT), "suspected_risk": (VIOLET, VIOLET_SOFT), "observation": (SLATE, SLATE_SOFT)}

# Chart series: cobalt (primary), violet (secondary), emerald (favourable), coral (risk), slate, periwinkle
PLOTLY_COLORS = [COBALT, VIOLET, EMERALD, CORAL, SLATE, "#9FB1FF"]
SERIES = {"reported": VIOLET, "orders": COBALT, "net": EMERALD, "variance": CORAL, "neutral": "#B8C0D9"}

SIGNAL_ICON = (
    '<svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<rect x="1" y="1" width="26" height="26" rx="7" fill="#4F5DFF"/>'
    '<path d="M6 17.5 L11 12 L15 15.5 L22 8" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="22" cy="8" r="2.4" fill="#FFFFFF"/><circle cx="22" cy="8" r="1.1" fill="#F06464"/>'
    "</svg>"
)

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
  --tell-canvas: {CANVAS}; --tell-surface: {SURFACE}; --tell-surface-alt: {SURFACE_ALT}; --tell-highlight: {HIGHLIGHT};
  --tell-line: {LINE}; --tell-line-strong: {LINE_STRONG}; --tell-ink: {INK}; --tell-ink-soft: {INK_SOFT}; --tell-muted: {MUTED};
  --tell-cobalt: {COBALT}; --tell-cobalt-deep: {COBALT_DEEP}; --tell-cobalt-soft: {COBALT_SOFT};
  --tell-violet: {VIOLET}; --tell-emerald: {EMERALD}; --tell-coral: {CORAL}; --tell-amber: {AMBER};
  --tell-radius: 10px; --tell-radius-sm: 6px; --tell-shadow: 0 1px 2px rgba(23,33,58,0.05), 0 4px 16px rgba(23,33,58,0.05);
  --tell-space-1: 4px; --tell-space-2: 8px; --tell-space-3: 12px; --tell-space-4: 16px; --tell-space-6: 24px; --tell-space-8: 32px;
}}

html, body, [class*="css"], .stApp, .stMarkdown {{ font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; color: var(--tell-ink); font-feature-settings: 'cv11', 'ss01'; }}
.stApp {{ background: var(--tell-canvas); }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1280px; }}
.tell-num, .tell-kpi .value, div[data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}

/* ---------- typography scale ---------- */
h1, h2, h3, h4 {{ font-family: 'Inter', sans-serif; color: var(--tell-ink); letter-spacing: -0.015em; }}
h1 {{ font-size: 1.75rem !important; font-weight: 700 !important; line-height: 1.2 !important; margin: 0 0 0.25rem 0 !important; padding: 0 !important; }}
h2 {{ font-size: 1.2rem !important; font-weight: 650 !important; margin: 1.6rem 0 0.4rem 0 !important; padding: 0 !important; }}
h3 {{ font-size: 1rem !important; font-weight: 600 !important; margin: 0.9rem 0 0.35rem 0 !important; padding: 0 !important; }}
.tell-eyebrow {{ font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--tell-cobalt-deep); font-weight: 700; margin-bottom: 6px; }}
.tell-eyebrow.muted {{ color: var(--tell-muted); }}
.tell-sub {{ color: var(--tell-ink-soft); font-size: 0.94rem; line-height: 1.5; margin: 0 0 1.1rem 0; max-width: 72ch; }}
.tell-note {{ color: var(--tell-muted); font-size: 0.78rem; line-height: 1.45; }}
.tell-caption {{ color: var(--tell-ink-soft); font-size: 0.85rem; line-height: 1.55; }}
.tell-meta {{ color: var(--tell-muted); font-size: 0.8rem; display: flex; gap: 14px; flex-wrap: wrap; align-items: center; }}
.tell-meta .dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 6px; }}

/* ---------- section header ---------- */
.tell-section {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 1.6rem 0 0.6rem 0; padding-bottom: 8px; border-bottom: 1px solid var(--tell-line); }}
.tell-section .title {{ font-size: 1.08rem; font-weight: 650; color: var(--tell-ink); letter-spacing: -0.01em; }}
.tell-section .hint {{ color: var(--tell-muted); font-size: 0.8rem; }}

/* ---------- KPI module ---------- */
.tell-kpi {{ position: relative; background: var(--tell-surface); border: 1px solid var(--tell-line); border-radius: var(--tell-radius); padding: 14px 16px 12px 18px; min-height: 104px; }}
.tell-kpi::before {{ content: ""; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px; border-radius: 3px; background: var(--kpi-accent, var(--tell-line-strong)); }}
.tell-kpi .label {{ font-size: 0.72rem; letter-spacing: 0.07em; text-transform: uppercase; color: var(--tell-muted); font-weight: 650; }}
.tell-kpi .value {{ font-size: 1.65rem; font-weight: 700; color: var(--tell-ink); line-height: 1.15; margin-top: 6px; letter-spacing: -0.02em; }}
.tell-kpi .delta {{ font-size: 0.8rem; color: var(--tell-ink-soft); margin-top: 6px; line-height: 1.4; }}
.tell-kpi .delta b {{ font-weight: 650; }}
.tell-kpi.plain {{ background: transparent; border: none; border-top: 1px solid var(--tell-line); border-radius: 0; padding-left: 0; min-height: 0; }}
.tell-kpi.plain::before {{ display: none; }}

/* ---------- pills & tags ---------- */
.tell-pill {{ display: inline-block; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; padding: 2px 8px; border-radius: 999px; margin-right: 6px; vertical-align: middle; line-height: 1.5; }}
.tell-pill.outline {{ background: var(--tell-surface); border: 1px solid var(--tell-line-strong); color: var(--tell-ink-soft); }}
.tell-chip {{ display: inline-block; font-size: 0.78rem; padding: 2px 10px; border-radius: 999px; background: var(--tell-surface-alt); color: var(--tell-ink-soft); margin-right: 6px; }}

/* ---------- finding / list rows ---------- */
.tell-row {{ position: relative; padding: 12px 14px 12px 18px; border: 1px solid var(--tell-line); border-radius: var(--tell-radius); background: var(--tell-surface); margin-bottom: 8px; transition: border-color .15s, box-shadow .15s; }}
.tell-row:hover {{ border-color: var(--tell-line-strong); box-shadow: var(--tell-shadow); }}
.tell-row::before {{ content: ""; position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; border-radius: 3px; background: var(--row-accent, var(--tell-line-strong)); }}
.tell-row .title {{ font-weight: 600; font-size: 0.95rem; color: var(--tell-ink); margin-top: 6px; }}
.tell-row .meta {{ color: var(--tell-ink-soft); font-size: 0.83rem; margin-top: 3px; line-height: 1.45; }}
.tell-row .impact {{ font-weight: 650; color: var(--tell-ink); font-variant-numeric: tabular-nums; }}
.tell-row.flat {{ border: none; border-bottom: 1px solid var(--tell-line); border-radius: 0; background: transparent; padding-left: 14px; margin-bottom: 0; }}
.tell-row.flat:hover {{ box-shadow: none; background: var(--tell-surface-alt); }}

.tell-divider {{ border-top: 1px solid var(--tell-line); margin: 1.4rem 0; }}
.tell-panel {{ background: var(--tell-surface); border: 1px solid var(--tell-line); border-radius: var(--tell-radius); padding: 16px 18px; }}
.tell-panel.tint {{ background: var(--tell-highlight); border-color: #D4D8FF; }}
.tell-panel.emerald {{ background: {EMERALD_SOFT}; border-color: #BFE7D8; }}
.tell-panel.coral {{ background: {CORAL_SOFT}; border-color: #F6C4C4; }}
.tell-panel .ttl {{ font-weight: 650; margin-bottom: 4px; }}
.tell-insight {{ border-left: 3px solid var(--tell-cobalt); background: var(--tell-highlight); padding: 10px 14px; border-radius: 0 var(--tell-radius-sm) var(--tell-radius-sm) 0; font-size: 0.88rem; color: var(--tell-ink); line-height: 1.5; }}
.tell-insight.coral {{ border-color: var(--tell-coral); background: {CORAL_SOFT}; }}
.tell-insight.emerald {{ border-color: var(--tell-emerald); background: {EMERALD_SOFT}; }}

/* ---------- stat strip (reconciliation bridge) ---------- */
.tell-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
.tell-strip .cell {{ background: var(--tell-surface); border: 1px solid var(--tell-line); border-radius: var(--tell-radius-sm); padding: 10px 12px; }}
.tell-strip .cell .k {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: .06em; color: var(--tell-muted); font-weight: 650; display: flex; align-items: center; gap: 6px; }}
.tell-strip .cell .v {{ font-size: 1.15rem; font-weight: 700; margin-top: 4px; font-variant-numeric: tabular-nums; }}
.tell-strip .cell .s {{ font-size: 0.76rem; color: var(--tell-ink-soft); margin-top: 2px; }}
.tell-swatch {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}

/* ---------- Streamlit widget overrides ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{ border-radius: 8px; border: 1px solid var(--tell-line-strong); background: var(--tell-surface); color: var(--tell-ink); font-weight: 550; min-height: 38px; transition: background .15s, border-color .15s, color .15s; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{ border-color: var(--tell-cobalt); color: var(--tell-cobalt-deep); background: var(--tell-highlight); }}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{ outline: 2px solid var(--tell-cobalt); outline-offset: 2px; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{ background: var(--tell-cobalt); border-color: var(--tell-cobalt); color: #fff; }}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{ background: var(--tell-cobalt-deep); border-color: var(--tell-cobalt-deep); color: #fff; }}
.stButton > button:disabled {{ opacity: .5; }}
div[data-testid="stDataFrame"] {{ border: 1px solid var(--tell-line); border-radius: var(--tell-radius-sm); overflow: hidden; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 22px; border-bottom: 1px solid var(--tell-line); }}
.stTabs [data-baseweb="tab"] {{ padding: 8px 0; color: var(--tell-ink-soft); font-weight: 500; }}
.stTabs [aria-selected="true"] {{ color: var(--tell-cobalt-deep); font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--tell-cobalt); height: 2px; }}
div[data-testid="stExpander"] {{ border: 1px solid var(--tell-line); border-radius: var(--tell-radius-sm); background: var(--tell-surface); }}
div[data-testid="stExpander"] summary {{ font-weight: 550; }}
div[data-testid="stRadio"] label {{ padding: 6px 8px; border-radius: 6px; width: 100%; transition: background .12s; }}
div[data-testid="stRadio"] label:hover {{ background: var(--tell-surface-alt); }}
div[data-testid="stRadio"] label:has(input:checked) {{ background: var(--tell-highlight); }}
div[data-testid="stChatMessage"] {{ background: var(--tell-surface); border: 1px solid var(--tell-line); border-radius: var(--tell-radius); padding: 12px 16px; }}
div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {{ visibility: hidden; height: 0; }}
header[data-testid="stHeader"] {{ background: transparent; height: 1.6rem; }}
footer {{ visibility: hidden; }}
#MainMenu {{ visibility: hidden; }}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {{ background: {NAVY}; border-right: 1px solid {NAVY_LINE}; }}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1.3rem; }}
section[data-testid="stSidebar"] * {{ color: {NAVY_TEXT}; }}
.tell-wordmark {{ display: flex; align-items: center; gap: 10px; margin-bottom: 2px; }}
.tell-wordmark .name {{ font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; color: #fff; }}
.tell-tagline {{ font-size: 0.76rem; color: {NAVY_MUTED}; margin: 0 0 16px 38px; }}
.tell-side-label {{ font-size: 0.66rem; letter-spacing: 0.1em; text-transform: uppercase; color: {NAVY_MUTED}; font-weight: 700; margin: 14px 0 6px 2px; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{ padding: 7px 10px; border-radius: 7px; margin: 1px 0; transition: background .12s; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span, section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {{ color: {NAVY_TEXT}; font-size: 0.9rem; font-weight: 500; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{ background: {NAVY_RAISED}; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] {{ background: {COBALT}; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] span, section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] p {{ color: #fff; font-weight: 600; }}
.tell-nav-active {{ display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 7px; background: {COBALT}; color: #fff !important; font-size: 0.9rem; font-weight: 600; margin: 1px 0; }}
.tell-nav-active .material-symbols-rounded {{ font-family: 'Material Symbols Rounded'; font-size: 1.15rem; line-height: 1; color: #fff; font-variation-settings: 'FILL' 0, 'wght' 400; }}
section[data-testid="stSidebar"] .tell-divider {{ border-color: {NAVY_LINE}; margin: 0.9rem 0; }}
section[data-testid="stSidebar"] .tell-note {{ color: {NAVY_MUTED}; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{ background: {NAVY_RAISED}; border-color: {NAVY_LINE}; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] svg {{ fill: {NAVY_MUTED}; }}
.tell-side-foot {{ display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 8px; background: {NAVY_RAISED}; }}
.tell-side-foot .avatar {{ width: 30px; height: 30px; border-radius: 50%; background: {VIOLET}; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.8rem; color: #fff; flex-shrink: 0; }}
.tell-side-foot .who {{ font-size: 0.82rem; font-weight: 600; color: #fff; line-height: 1.2; }}
.tell-side-foot .role {{ font-size: 0.72rem; color: {NAVY_MUTED}; }}


/* ---------- v3: editorial composition ---------- */
.tell-identity {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 22px; padding-bottom: 14px; border-bottom: 2px solid var(--tell-ink); margin-bottom: 4px; }}
.tell-identity .name {{ font-size: 1.9rem; font-weight: 750; letter-spacing: -0.03em; color: var(--tell-ink); line-height: 1.05; }}
.tell-identity .fact {{ font-size: 0.78rem; color: var(--tell-ink-soft); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }}
.tell-identity .fact b {{ color: var(--tell-ink); font-weight: 700; }}
.tell-stage {{ display: flex; flex-wrap: wrap; gap: 0; margin: 10px 0 4px 0; border: 1px solid var(--tell-line); border-radius: 8px; overflow: hidden; background: var(--tell-surface); }}
.tell-stage .step {{ flex: 1 1 150px; padding: 8px 12px; font-size: 0.74rem; color: var(--tell-muted); border-right: 1px solid var(--tell-line); display: flex; gap: 8px; align-items: center; }}
.tell-stage .step:last-child {{ border-right: none; }}
.tell-stage .step .n {{ width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--tell-line-strong); display: inline-flex; align-items: center; justify-content: center; font-size: 0.66rem; font-weight: 700; flex-shrink: 0; }}
.tell-stage .step.done {{ color: var(--tell-ink); }}
.tell-stage .step.done .n {{ background: var(--tell-emerald); border-color: var(--tell-emerald); color: #fff; }}
.tell-stage .step.active {{ color: var(--tell-cobalt-deep); background: var(--tell-highlight); font-weight: 600; }}
.tell-stage .step.active .n {{ background: var(--tell-cobalt); border-color: var(--tell-cobalt); color: #fff; }}
.tell-stage .step.partial .n {{ border-color: var(--tell-amber); color: var(--tell-amber); }}
.tell-stage .step .sub {{ font-weight: 400; color: var(--tell-muted); margin-left: auto; font-variant-numeric: tabular-nums; }}

.tell-brief {{ border-top: 3px solid var(--tell-ink); padding-top: 14px; }}
.tell-brief .kicker {{ font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--tell-cobalt-deep); font-weight: 700; }}
.tell-brief .lede {{ font-size: 1.35rem; font-weight: 650; line-height: 1.3; letter-spacing: -0.015em; color: var(--tell-ink); margin: 6px 0 14px 0; max-width: 60ch; }}
.tell-brief .lede em {{ font-style: normal; color: var(--tell-coral); }}
.tell-brief .item {{ display: grid; grid-template-columns: 26px 1fr; gap: 10px; padding: 9px 0; border-top: 1px solid var(--tell-line); font-size: 0.9rem; line-height: 1.5; color: var(--tell-ink); }}
.tell-brief .item .n {{ font-size: 0.72rem; font-weight: 700; color: var(--tell-muted); padding-top: 3px; font-variant-numeric: tabular-nums; }}
.tell-brief .item .tag {{ font-size: 0.66rem; letter-spacing: 0.07em; text-transform: uppercase; font-weight: 700; margin-right: 8px; }}
.tell-brief .item .ref {{ color: var(--tell-muted); font-size: 0.76rem; margin-left: 6px; white-space: nowrap; }}

.tell-hero {{ display: flex; flex-wrap: wrap; gap: 22px 36px; align-items: flex-end; padding: 6px 0 10px 0; }}
.tell-hero .fig {{ min-width: 0; }}
.tell-hero .fig .k {{ font-size: 0.7rem; letter-spacing: 0.09em; text-transform: uppercase; color: var(--tell-muted); font-weight: 650; }}
.tell-hero .fig .v {{ font-size: clamp(1.4rem, 2vw, 2.1rem); font-weight: 750; letter-spacing: -0.03em; line-height: 1.05; color: var(--tell-ink); font-variant-numeric: tabular-nums; margin-top: 2px; }}
.tell-hero .fig .v.sm {{ font-size: clamp(1.15rem, 1.5vw, 1.45rem); }}
.tell-hero .fig .s {{ font-size: 0.78rem; color: var(--tell-ink-soft); margin-top: 3px; }}
.tell-hero .fig.accent .v {{ color: var(--fig-color, var(--tell-ink)); }}

.tell-ledger {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
.tell-ledger td {{ padding: 7px 0 !important; border: none !important; border-bottom: 1px solid var(--tell-line) !important; vertical-align: top; background: transparent !important; color: var(--tell-ink); }}
.tell-ledger tr {{ background: transparent !important; }}
.tell-ledger td:last-child {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; padding-left: 16px; }}
.tell-ledger tr.total td {{ border-top: 2px solid var(--tell-ink) !important; border-bottom: none !important; font-weight: 700; }}
.tell-ledger tr.flag td:last-child {{ color: var(--tell-coral); }}
.tell-ledger .sub {{ color: var(--tell-muted); font-size: 0.76rem; display: block; font-weight: 400; }}

.tell-timeline {{ position: relative; padding-left: 18px; }}
.tell-timeline::before {{ content: ""; position: absolute; left: 5px; top: 6px; bottom: 6px; width: 2px; background: var(--tell-line); }}
.tell-timeline .ev {{ position: relative; padding: 4px 0 12px 12px; font-size: 0.85rem; color: var(--tell-ink); }}
.tell-timeline .ev::before {{ content: ""; position: absolute; left: -17px; top: 9px; width: 10px; height: 10px; border-radius: 50%; background: var(--ev-color, var(--tell-line-strong)); border: 2px solid var(--tell-canvas); }}
.tell-timeline .ev .when {{ font-size: 0.72rem; color: var(--tell-muted); letter-spacing: 0.04em; text-transform: uppercase; font-weight: 650; }}
.tell-timeline .ev .what {{ margin-top: 1px; line-height: 1.45; }}

.tell-signal {{ display: grid; grid-template-columns: 6px 1fr auto; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--tell-line); align-items: start; }}
.tell-signal .bar {{ width: 6px; border-radius: 3px; background: var(--sig-color, var(--tell-line-strong)); align-self: stretch; }}
.tell-signal .t {{ font-size: 0.9rem; font-weight: 600; color: var(--tell-ink); line-height: 1.35; }}
.tell-signal .m {{ font-size: 0.8rem; color: var(--tell-ink-soft); margin-top: 2px; line-height: 1.45; }}
.tell-signal .impact {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; font-size: 0.95rem; white-space: nowrap; }}
.tell-signal .impact small {{ display: block; font-size: 0.68rem; color: var(--tell-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }}

.tell-listitem {{ padding: 8px 10px 8px 12px; border-left: 3px solid var(--li-color, var(--tell-line-strong)); margin: 0 0 4px 0; font-size: 0.86rem; line-height: 1.35; color: var(--tell-ink); background: transparent; border-radius: 0 6px 6px 0; }}
.tell-listitem.active {{ background: var(--tell-highlight); font-weight: 600; }}
.tell-listitem .k {{ font-size: 0.68rem; color: var(--tell-muted); letter-spacing: 0.05em; text-transform: uppercase; font-weight: 700; margin-right: 6px; }}
.tell-listitem .sub {{ display: block; color: var(--tell-muted); font-size: 0.74rem; font-weight: 400; margin-top: 1px; }}

.tell-srcmap {{ display: grid; grid-template-columns: 1.4fr 1fr 1fr 2fr; font-size: 0.85rem; border-top: 2px solid var(--tell-ink); }}
.tell-srcmap > div {{ padding: 9px 10px 9px 0; border-bottom: 1px solid var(--tell-line); }}
.tell-srcmap .h {{ font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--tell-muted); font-weight: 700; }}
.tell-srcmap .st {{ font-weight: 700; display: inline-flex; align-items: center; gap: 6px; }}
.tell-srcmap .st::before {{ content: ""; width: 9px; height: 9px; border-radius: 2px; background: var(--st-color); }}

.tell-doc {{ max-width: 860px; }}
.tell-doc .masthead {{ border-bottom: 3px solid var(--tell-ink); padding-bottom: 12px; margin-bottom: 8px; }}
.tell-doc .masthead .t {{ font-size: 2rem; font-weight: 750; letter-spacing: -0.03em; line-height: 1.1; }}
.tell-doc .masthead .s {{ color: var(--tell-ink-soft); font-size: 0.9rem; margin-top: 6px; }}
.tell-doc h2 {{ font-size: 1.05rem !important; text-transform: uppercase; letter-spacing: 0.06em; color: var(--tell-cobalt-deep); margin-top: 1.8rem !important; }}
.tell-doc .num {{ color: var(--tell-muted); margin-right: 8px; }}

div[data-testid="stRadio"] label {{ padding: 5px 8px; }}
div[data-baseweb="segmented-control"] {{ background: var(--tell-surface-alt); border-radius: 8px; }}
.stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{ border-radius: 8px; }}

/* ---------- responsive ---------- */
.tell-kpi .value {{ font-size: clamp(1.15rem, 1.6vw, 1.65rem); overflow-wrap: anywhere; }}
@media (max-width: 1200px) {{
  .tell-kpi {{ padding: 12px 12px 10px 14px; min-height: 0; }}
  .tell-kpi .label {{ font-size: 0.66rem; letter-spacing: 0.05em; }}
  .tell-kpi .delta {{ font-size: 0.74rem; }}
  .tell-section {{ flex-direction: column; align-items: flex-start; gap: 4px; }}
}}
@media (max-width: 900px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  h1 {{ font-size: 1.45rem !important; }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def plotly_layout(fig, height: int = 320, legend: bool = True, hovermode: str = "closest"):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=28, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color=INK_SOFT), colorway=PLOTLY_COLORS,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11), bgcolor="rgba(0,0,0,0)") if legend else dict(),
        showlegend=legend, hoverlabel=dict(bgcolor=NAVY, bordercolor=NAVY, font=dict(color="#fff", size=12, family="Inter, sans-serif")),
        hovermode=hovermode,
    )
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(size=11), title=None, showline=True)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE_STRONG, tickfont=dict(size=11), title=None, showline=False)
    return fig
