"""Reusable UI building blocks."""

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


def pct(value: Any, decimals: int = 1, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    return f"{float(value):+.{decimals}f}%" if signed else f"{float(value):.{decimals}f}%"


def page_header(title: str, subtitle: str | None = None, eyebrow: str | None = None) -> None:
    if eyebrow:
        st.markdown(f'<div class="tell-eyebrow">{html.escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.markdown(f"<h1>{html.escape(title)}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="tell-sub">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, delta: str | None = None) -> None:
    d = f'<div class="delta">{html.escape(delta)}</div>' if delta else ""
    st.markdown(f'<div class="tell-kpi"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div>{d}</div>', unsafe_allow_html=True)


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value, delta) in zip(cols, items):
        with col:
            kpi(label, value, delta)


def pill(text: str, fg: str, bg: str) -> str:
    return f'<span class="tell-pill" style="color:{fg};background:{bg}">{html.escape(text)}</span>'


def severity_pill(severity: str) -> str:
    fg, bg = theme.SEVERITY_COLORS.get(severity, (theme.INK_SOFT, theme.PANEL))
    return pill(severity, fg, bg)


def status_pill(status: str) -> str:
    return pill(theme.STATUS_LABELS.get(status, status), theme.INK_SOFT, "#fff; border:1px solid " + theme.LINE)


def class_pill(classification: str) -> str:
    return pill(theme.CLASS_LABELS.get(classification, classification), theme.SLATE, theme.SLATE_SOFT)


def divider() -> None:
    st.markdown('<div class="tell-divider"></div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="tell-note">{html.escape(text)}</div>', unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<div class="tell-caption">{html.escape(text)}</div>', unsafe_allow_html=True)


def empty_state(title: str, body: str, action_label: str | None = None, key: str | None = None) -> bool:
    st.markdown(f'<div class="tell-panel"><div style="font-weight:600;margin-bottom:4px">{html.escape(title)}</div>'
                f'<div class="tell-caption">{html.escape(body)}</div></div>', unsafe_allow_html=True)
    if action_label:
        st.write("")
        return st.button(action_label, type="primary", key=key)
    return False


def finding_row(f: pd.Series, cur: str) -> None:
    impact = money(f["estimated_impact"], cur) if pd.notna(f.get("estimated_impact")) else "Not quantified"
    st.markdown(
        f'<div class="tell-row"><div>{severity_pill(f["severity"])}{class_pill(f["classification"])}{status_pill(f["status"])}</div>'
        f'<div class="title" style="margin-top:6px">{html.escape(str(f["title"]))}</div>'
        f'<div class="meta">{html.escape(str(f["summary"]))}</div>'
        f'<div class="meta">Impact {html.escape(impact)} · {int(f["evidence_count"])} evidence rows · {html.escape(str(f["finding_key"]))}</div></div>',
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
