"""Plotly chart builders. Series colours are semantic (see theme.SERIES)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from tell.ui import theme

S = theme.SERIES


def _money_fmt(cur: str) -> str:
    return f"{cur} %{{y:,.0f}}"


def revenue_margin(fin: pd.DataFrame, cur: str) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=fin["period"], y=fin["net_sales"], name=f"Net sales ({cur})", marker_color=theme.COBALT, marker_line_width=0,
                hovertemplate=f"Net sales {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_scatter(x=fin["period"], y=fin["gross_margin_pct"], name="Gross margin (%)", yaxis="y2", mode="lines+markers",
                    line=dict(color=theme.VIOLET, width=2.2), marker=dict(size=6, color="#fff", line=dict(color=theme.VIOLET, width=2)),
                    hovertemplate="Gross margin %{y:.1f}%<extra></extra>")
    ymax = float(fin["gross_margin_pct"].max() or 0)
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, max(100, ymax + 10)], ticksuffix="%", tickfont=dict(size=11)),
                      bargap=0.35)
    return theme.plotly_layout(fig, 320, hovermode="x unified")


def reconciliation_flow(totals: dict, cur: str) -> go.Figure:
    """Horizontal comparison of seller-reported revenue, order-ledger gross sales and refund-adjusted net sales."""
    rows = [("Seller-reported revenue", totals["reported"], S["reported"], "Figure in the seller's management accounts"),
            ("Order-ledger gross sales", totals["gross"], S["orders"], "Completed orders after discounts, before refunds"),
            ("Refund-adjusted net sales", totals["net"], S["net"], "Gross sales less refunds posted in the period")]
    fig = go.Figure()
    for label, value, color, desc in rows:
        fig.add_bar(y=[label], x=[value], orientation="h", marker_color=color, marker_line_width=0, name=label, width=0.58,
                    text=[f"{cur} {value:,.0f}"], textposition="auto", insidetextanchor="end", outsidetextfont=dict(size=12, color=theme.INK, family="Inter"),
                    insidetextfont=dict(size=12, color="#fff", family="Inter"), cliponaxis=False, hovertemplate=f"<b>{label}</b><br>{cur} %{{x:,.0f}}<br><span style='font-size:11px'>{desc}</span><extra></extra>")
    xmax = max(v for _, v, _, _ in rows)
    fig.update_layout(barmode="overlay", xaxis=dict(range=[0, xmax * 1.22], showticklabels=False, showgrid=False), yaxis=dict(autorange="reversed", tickfont=dict(size=12, color=theme.INK)), bargap=0.2)
    return theme.plotly_layout(fig, 230, legend=False)


def reconciliation_bars(fin: pd.DataFrame, cur: str) -> go.Figure:
    df = fin[fin["reported_revenue"].notna()]
    fig = go.Figure()
    fig.add_bar(x=df["period"], y=df["reported_revenue"], name="Seller-reported", marker_color=S["reported"], marker_line_width=0,
                hovertemplate=f"Seller-reported {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_bar(x=df["period"], y=df["net_sales"], name="Refund-adjusted net sales", marker_color=S["net"], marker_line_width=0,
                hovertemplate=f"Net sales {cur} %{{y:,.0f}}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    return theme.plotly_layout(fig, 300, hovermode="x unified")


def variance_bars(fin: pd.DataFrame, cur: str, threshold_pct: float = 2.0) -> go.Figure:
    df = fin[fin["reported_revenue"].notna()]
    colors = [S["variance"] if abs(v) >= threshold_pct else S["neutral"] for v in df["revenue_variance_pct"].fillna(0)]
    fig = go.Figure(go.Bar(x=df["period"], y=df["revenue_variance_pct"], marker_color=colors, marker_line_width=0,
                           customdata=df["revenue_variance"], hovertemplate=f"Variance %{{y:+.1f}}%<br>{cur} %{{customdata:+,.0f}}<extra></extra>"))
    fig.add_hline(y=threshold_pct, line_dash="dot", line_color=theme.MUTED, line_width=1, annotation_text=f"±{threshold_pct:g}% threshold", annotation_position="top left", annotation_font=dict(size=10, color=theme.MUTED))
    fig.add_hline(y=-threshold_pct, line_dash="dot", line_color=theme.MUTED, line_width=1)
    fig.update_yaxes(ticksuffix="%")
    return theme.plotly_layout(fig, 240, legend=False)


def waterfall(row: pd.Series, cur: str) -> go.Figure:
    """Bridge from seller-reported revenue to order-derived net sales for one month."""
    reported, net, gross = float(row["reported_revenue"]), float(row["net_sales"]), float(row["gross_sales"])
    refunds, cancelled = float(row["refunds_posted"]), float(row["cancelled_value"])
    steps = [("Seller-reported", reported, "absolute")]
    rem = reported
    if abs(reported - (gross + cancelled)) < abs(reported - gross):
        steps.append(("Less cancelled orders", -cancelled, "relative")); rem -= cancelled
    steps.append(("Less refunds posted", -refunds, "relative")); rem -= refunds
    residual = net - rem
    if abs(residual) > 0.5:
        steps.append(("Unexplained residual", residual, "relative"))
    steps.append(("Net sales (supported)", net, "total"))
    fig = go.Figure(go.Waterfall(
        x=[s[0] for s in steps], y=[s[1] for s in steps], measure=[s[2] for s in steps],
        text=[f"{cur} {abs(s[1]):,.0f}" for s in steps], textposition="outside", textfont=dict(size=11),
        connector=dict(line=dict(color=theme.LINE_STRONG, width=1)), decreasing=dict(marker=dict(color=S["variance"])), increasing=dict(marker=dict(color=S["net"])),
        totals=dict(marker=dict(color=S["orders"])), hovertemplate=f"%{{x}}<br>{cur} %{{y:,.0f}}<extra></extra>"))
    fig.update_layout(waterfallgap=0.35)
    return theme.plotly_layout(fig, 310, legend=False)


def stacked_months(df: pd.DataFrame, x: str, y: str, group: str, cur: str) -> go.Figure:
    fig = go.Figure()
    for i, (name, g) in enumerate(df.groupby(group)):
        fig.add_bar(x=g[x], y=g[y], name=str(name), marker_color=theme.PLOTLY_COLORS[i % len(theme.PLOTLY_COLORS)], marker_line_width=0,
                    hovertemplate=f"{name} {cur} %{{y:,.0f}}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.35)
    return theme.plotly_layout(fig, 300, hovermode="x unified")


def share_bars(df: pd.DataFrame, label: str, value: str, top: int = 10, highlight_over: float | None = None, color: str = theme.COBALT) -> go.Figure:
    d = df.head(top).iloc[::-1]
    colors = [S["variance"] if highlight_over is not None and v >= highlight_over else color for v in d[value]]
    fig = go.Figure(go.Bar(x=d[value], y=d[label], orientation="h", marker_color=colors, marker_line_width=0,
                           text=[f"{v:.1f}%" for v in d[value]], textposition="outside", textfont=dict(size=11), cliponaxis=False,
                           hovertemplate="%{y}<br>%{x:.1f}%<extra></extra>"))
    fig.update_xaxes(ticksuffix="%", range=[0, float(d[value].max()) * 1.18 if len(d) else 1], showgrid=False)
    return theme.plotly_layout(fig, 30 * len(d) + 60, legend=False)


def line(df: pd.DataFrame, x: str, y: str, name: str, suffix: str = "", color: str = theme.COBALT, height: int = 240, baseline: float | None = None) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines+markers", name=name, line=dict(color=color, width=2.2),
                               marker=dict(size=6, color="#fff", line=dict(color=color, width=2)),
                               fill="tozeroy", fillcolor=_alpha(color, 0.08),
                               hovertemplate=f"%{{x}}<br>{name} %{{y:,.1f}}{suffix}<extra></extra>"))
    if baseline is not None:
        fig.add_hline(y=baseline, line_dash="dot", line_color=theme.MUTED, line_width=1, annotation_text="median", annotation_position="top left", annotation_font=dict(size=10, color=theme.MUTED))
    fig.update_yaxes(ticksuffix=suffix)
    return theme.plotly_layout(fig, height, legend=False)


def inventory_rollforward(rf: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=rf["period"], y=rf["expected"], name="Expected (roll-forward)", mode="lines+markers", line=dict(color=theme.VIOLET, dash="dot", width=2), marker=dict(size=5))
    fig.add_scatter(x=rf["period"], y=rf["recorded"], name="Recorded count", mode="lines+markers", line=dict(color=theme.COBALT, width=2.2), marker=dict(size=6, color="#fff", line=dict(color=theme.COBALT, width=2)))
    bad = rf[rf["variance"] != 0]
    if not bad.empty:
        fig.add_scatter(x=bad["period"], y=bad["recorded"], name="Variance", mode="markers", marker=dict(size=10, color=S["variance"], symbol="diamond"),
                        hovertemplate="%{x}<br>recorded %{y} (variance %{customdata:+d})<extra></extra>", customdata=bad["variance"])
    return theme.plotly_layout(fig, 270, hovermode="x unified")


def _alpha(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"
