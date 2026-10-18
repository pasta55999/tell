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


def masthead(status_html: str) -> None:
    """Brand strip at the top of every page: signal mark, wordmark, tagline and a live status chip."""
    st.markdown(f'<div class="tell-masthead"><div class="brand"><span class="tag">Every business has a tell.</span></div>'
                f'<div class="status"><span class="dot"></span>{status_html}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- v3 editorial blocks

def identity(name: str, facts: list[tuple[str, str]]) -> None:
    """Acquisition identity strip: big name plus uppercase key facts."""
    fs = "".join(f'<span class="fact">{(esc(k) + " ") if k else ""}<b>{esc(v)}</b></span>' for k, v in facts if v)
    st.markdown(f'<div class="tell-identity"><span class="name">{esc(name)}</span>{fs}</div>', unsafe_allow_html=True)


def stepper(steps: list[tuple[str, str, str | None]]) -> None:
    """Workflow stepper. steps: (label, state in done|active|partial|todo, sub-text)."""
    items = "".join(f'<div class="step {s}"><span class="n">{i}</span>{esc(l)}{f"<span class=sub>{esc(sub)}</span>" if sub else ""}</div>'
                    for i, (l, s, sub) in enumerate(steps, 1))
    st.markdown(f'<div class="tell-stage">{items}</div>', unsafe_allow_html=True)


def brief(kicker: str, lede_html: str, items: list[dict]) -> None:
    """Investment intelligence brief. items: {tag, tag_color, text, ref}. lede_html may contain <em>."""
    rows = ""
    for i, it in enumerate(items, 1):
        ref = f'<span class="ref">{esc(it["ref"])}</span>' if it.get("ref") else ""
        rows += (f'<div class="item"><span class="n">{i:02d}</span><span><span class="tag" style="color:{it.get("tag_color", theme.MUTED)}">{esc(it["tag"])}</span>'
                 f'{esc(it["text"])}{ref}</span></div>')
    st.markdown(f'<div class="tell-brief"><div class="kicker">{esc(kicker)}</div><div class="lede">{lede_html}</div>{rows}</div>', unsafe_allow_html=True)


def hero(figs: list[tuple], small: bool = False) -> None:
    """Typographic figures. figs: (label, value, sub[, colour])."""
    parts = []
    for f in figs:
        k, v, s = f[0], f[1], f[2]
        color = f[3] if len(f) > 3 and f[3] else None
        parts.append(f'<div class="fig{" accent" if color else ""}"{f" style=--fig-color:{color}" if color else ""}><div class="k">{esc(k)}</div>'
                     f'<div class="v{" sm" if small else ""}">{esc(v)}</div>{f"<div class=s>{esc(s)}</div>" if s else ""}</div>')
    st.markdown(f'<div class="tell-hero">{"".join(parts)}</div>', unsafe_allow_html=True)


def ledger(rows: list[tuple], total: tuple | None = None) -> None:
    """Aligned key/value rows. rows: (label, value, sub|None, flag:bool)."""
    body = ""
    for r in rows:
        label, value = r[0], r[1]
        sub = r[2] if len(r) > 2 and r[2] else None
        flag = r[3] if len(r) > 3 else False
        body += f'<tr class="{"flag" if flag else ""}"><td>{esc(label)}{f"<span class=sub>{esc(sub)}</span>" if sub else ""}</td><td>{esc(value)}</td></tr>'
    if total:
        body += f'<tr class="total"><td>{esc(total[0])}</td><td>{esc(total[1])}</td></tr>'
    st.markdown(f'<table class="tell-ledger">{body}</table>', unsafe_allow_html=True)


def timeline(events: list[tuple[str, str, str | None]]) -> None:
    """events: (when, what_html_escaped_text, colour)."""
    items = "".join(f'<div class="ev"{f" style=--ev-color:{c}" if c else ""}><div class="when">{esc(w)}</div><div class="what">{t}</div></div>' for w, t, c in events)
    st.markdown(f'<div class="tell-timeline">{items}</div>', unsafe_allow_html=True)


def signal(f: pd.Series, cur: str, compact: bool = False) -> None:
    color = theme.SEVERITY_BAR.get(f["severity"], theme.LINE_STRONG)
    impact = money(f["estimated_impact"], cur) if pd.notna(f.get("estimated_impact")) else "—"
    meta = (f'<div class="m">{esc(f["severity"])} · {esc(theme.CLASS_LABELS.get(f["classification"], f["classification"]).lower())}</div>' if compact
            else f'<div class="m">{severity_pill(f["severity"])}{class_pill(f["classification"])}{esc(f["summary"])}</div>')
    st.markdown(f'<div class="tell-signal" style="--sig-color:{color}"><div class="bar"></div><div><div class="t">{esc(f["title"])}</div>{meta}</div>'
                f'<div class="impact">{esc(impact)}<small>{"est. impact" if impact != "—" else "not quantified"}</small></div></div>', unsafe_allow_html=True)


def list_item(key: str, title: str, sub: str | None, color: str, active: bool = False) -> str:
    return (f'<div class="tell-listitem{" active" if active else ""}" style="--li-color:{color}"><span class="k">{esc(key)}</span>{esc(title)}'
            f'{f"<span class=sub>{esc(sub)}</span>" if sub else ""}</div>')


def source_map(rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (comparison, status_label, status_colour, detail)."""
    head = '<div class="h">Comparison</div><div class="h">Status</div><div class="h">Coverage</div><div class="h">What the records say</div>'
    body = "".join(f'<div>{esc(a)}</div><div><span class="st" style="--st-color:{col}">{esc(s)}</span></div><div>{esc(cov)}</div><div class="tell-caption">{esc(d)}</div>'
                   for a, s, col, cov, d in rows)
    st.markdown(f'<div class="tell-srcmap">{head}{body}</div>', unsafe_allow_html=True)


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
