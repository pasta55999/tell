"""Reusable UI building blocks. All HTML is escaped; colours come from theme tokens."""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

from tell.ui import theme


def money(value: Any, cur: str = "AED", decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    return f"{cur} {float(value):,.{decimals}f}"


def signed_money(value: Any, cur: str = "AED") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    v = float(value)
    return f"{'+' if v >= 0 else '-'}{cur} {abs(v):,.0f}"


def pct(value: Any, decimals: int = 1, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    return f"{float(value):+.{decimals}f}%" if signed else f"{float(value):.{decimals}f}%"


def esc(v: Any) -> str:
    return html.escape(str(v))


# ---------------------------------------------------------------- headers

def page_header(title: str, subtitle: str | None = None, eyebrow: str | None = None, meta: list[tuple[str, str | None]] | None = None) -> None:
    """Title block. `meta` is a list of (text, dot_colour|None) rendered as a compact status line."""
    if eyebrow:
        st.markdown(f'<div class="tell-eyebrow">{esc(eyebrow)}</div>', unsafe_allow_html=True)
    st.markdown(f"<h1>{esc(title)}</h1>", unsafe_allow_html=True)
    if meta:
        items = "".join(f'<span>{(f"<span class=dot style=background:{d}></span>" if d else "")}{esc(t)}</span>' for t, d in meta)
        st.markdown(f'<div class="tell-meta" style="margin-bottom:10px">{items}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="tell-sub">{esc(subtitle)}</div>', unsafe_allow_html=True)


def section(title: str, hint: str | None = None) -> None:
    st.markdown(f'<div class="tell-section"><span class="title">{esc(title)}</span>'
                f'{f"<span class=hint>{esc(hint)}</span>" if hint else ""}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- KPIs

def kpi(label: str, value: str, delta: str | None = None, accent: str | None = None, plain: bool = False) -> None:
    style = f' style="--kpi-accent:{accent}"' if accent else ""
    d = f'<div class="delta">{delta}</div>' if delta else ""   # delta may contain <b>; callers pass escaped text
    st.markdown(f'<div class="tell-kpi{" plain" if plain else ""}"{style}><div class="label">{esc(label)}</div>'
                f'<div class="value">{esc(value)}</div>{d}</div>', unsafe_allow_html=True)


def kpi_row(items: list[tuple], plain: bool = False) -> None:
    """items: (label, value, delta[, accent])."""
    cols = st.columns(len(items), gap="small")
    for col, item in zip(cols, items):
        label, value, delta = item[0], item[1], item[2]
        accent = item[3] if len(item) > 3 else None
        with col:
            kpi(label, value, delta, accent, plain)


def delta_text(text: str, tone: str = "neutral") -> str:
    """Escaped delta string with a coloured leading marker. tone: neutral | up | down | risk | good."""
    color = {"risk": theme.CORAL, "down": theme.CORAL, "good": theme.EMERALD, "up": theme.EMERALD, "neutral": theme.MUTED}[tone]
    glyph = {"risk": "▲", "down": "▼", "good": "●", "up": "▲", "neutral": "●"}[tone]
    return f'<b style="color:{color}">{glyph}</b> {esc(text)}'


# ---------------------------------------------------------------- pills

def pill(text: str, fg: str, bg: str, outline: bool = False) -> str:
    cls = "tell-pill outline" if outline else "tell-pill"
    return f'<span class="{cls}" style="color:{fg};background:{bg}">{esc(text)}</span>'


def severity_pill(severity: str) -> str:
    fg, bg = theme.SEVERITY_COLORS.get(severity, (theme.INK_SOFT, theme.SURFACE_ALT))
    return pill(severity, fg, bg)


def status_pill(status: str) -> str:
    fg, bg = theme.STATUS_COLORS.get(status, (theme.INK_SOFT, theme.SURFACE_ALT))
    return pill(theme.STATUS_LABELS.get(status, status), fg, bg)


def class_pill(classification: str) -> str:
    fg, bg = theme.CLASS_COLORS.get(classification, (theme.SLATE, theme.SLATE_SOFT))
    return pill(theme.CLASS_LABELS.get(classification, classification), fg, bg)


def priority_pill(priority: str) -> str:
    fg, bg = theme.PRIORITY_COLORS.get(priority, (theme.SLATE, theme.SLATE_SOFT))
    return pill(priority, fg, bg)


# ---------------------------------------------------------------- misc blocks

def divider() -> None:
    st.markdown('<div class="tell-divider"></div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="tell-note">{esc(text)}</div>', unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<div class="tell-caption">{esc(text)}</div>', unsafe_allow_html=True)


def insight(text: str, tone: str = "cobalt") -> None:
    st.markdown(f'<div class="tell-insight {tone}">{esc(text)}</div>', unsafe_allow_html=True)


def panel(title: str, body: str, tone: str = "") -> None:
    st.markdown(f'<div class="tell-panel {tone}"><div class="ttl">{esc(title)}</div><div class="tell-caption">{esc(body)}</div></div>', unsafe_allow_html=True)


def empty_state(title: str, body: str, action_label: str | None = None, key: str | None = None) -> bool:
    panel(title, body, "tint")
    if action_label:
        st.write("")
        return st.button(action_label, type="primary", key=key)
    return False


def stat_strip(cells: list[tuple[str, str, str | None, str | None]]) -> None:
    """cells: (label, value, sub, swatch_colour|None) rendered as a compact grid."""
    html_cells = "".join(
        f'<div class="cell"><div class="k">{(f"<span class=tell-swatch style=background:{sw}></span>" if sw else "")}{esc(k)}</div>'
        f'<div class="v">{esc(v)}</div>{f"<div class=s>{esc(s)}</div>" if s else ""}</div>' for k, v, s, sw in cells)
    st.markdown(f'<div class="tell-strip">{html_cells}</div>', unsafe_allow_html=True)


def finding_row(f: pd.Series, cur: str, flat: bool = False) -> None:
    impact = money(f["estimated_impact"], cur) if pd.notna(f.get("estimated_impact")) else "Not quantified"
    accent = theme.SEVERITY_BAR.get(f["severity"], theme.LINE_STRONG)
    st.markdown(
        f'<div class="tell-row{" flat" if flat else ""}" style="--row-accent:{accent}">'
        f'<div>{severity_pill(f["severity"])}{class_pill(f["classification"])}{status_pill(f["status"])}</div>'
        f'<div class="title">{esc(f["title"])}</div>'
        f'<div class="meta">{esc(f["summary"])}</div>'
        f'<div class="meta">Impact <span class="impact">{esc(impact)}</span> · {int(f["evidence_count"])} evidence rows · <span class="tell-note">{esc(f["finding_key"])}</span></div></div>',
        unsafe_allow_html=True,
    )


def format_table(df: pd.DataFrame, money_cols: list[str] = (), pct_cols: list[str] = (), int_cols: list[str] = (), cur: str = "AED") -> pd.DataFrame:
    out = df.copy()
    for c in money_cols:
        if c in out:
            out[c] = out[c].map(lambda v: money(v, cur))
    for c in pct_cols:
        if c in out:
            out[c] = out[c].map(lambda v: pct(v))
    for c in int_cols:
        if c in out:
            out[c] = out[c].map(lambda v: "" if pd.isna(v) else f"{int(v):,}")
    return out


def table(df: pd.DataFrame, height: int | None = None, **kwargs) -> None:
    if height is not None:
        kwargs["height"] = height
    st.dataframe(df, width="stretch", hide_index=True, **kwargs)
