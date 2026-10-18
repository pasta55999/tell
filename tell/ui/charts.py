"""Plotly chart builders used across pages."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from tell.ui import theme


def revenue_margin(fin: pd.DataFrame, cur: str) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=fin["period"], y=fin["net_sales"], name="Net sales", marker_color=theme.GREEN, opacity=0.9,
                hovertemplate=f"%{{x}}<br>Net sales {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_scatter(x=fin["period"], y=fin["gross_margin_pct"], name="Gross margin %", yaxis="y2", mode="lines+markers",
                    line=dict(color=theme.AMBER, width=2), marker=dict(size=5), hovertemplate="%{x}<br>Gross margin %{y:.1f}%<extra></extra>")
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, max(100, float(fin["gross_margin_pct"].max() or 0) + 10)], ticksuffix="%"))
    return theme.plotly_layout(fig, 320)


def reconciliation_bars(fin: pd.DataFrame, cur: str) -> go.Figure:
    df = fin[fin["reported_revenue"].notna()]
    fig = go.Figure()
    fig.add_bar(x=df["period"], y=df["net_sales"], name="Order-derived net sales", marker_color=theme.GREEN, hovertemplate=f"%{{x}}<br>Net sales {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_bar(x=df["period"], y=df["reported_revenue"], name="Seller-reported revenue", marker_color="#B9B4A6", hovertemplate=f"%{{x}}<br>Reported {cur} %{{y:,.0f}}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.25)
    return theme.plotly_layout(fig, 300)


def variance_bars(fin: pd.DataFrame, cur: str, threshold_pct: float = 2.0) -> go.Figure:
    df = fin[fin["reported_revenue"].notna()]
    colors = [theme.RUST if abs(v) >= threshold_pct else "#B9B4A6" for v in df["revenue_variance_pct"].fillna(0)]
    fig = go.Figure(go.Bar(x=df["period"], y=df["revenue_variance_pct"], marker_color=colors,
                           hovertemplate="%{x}<br>Variance %{y:+.1f}%<extra></extra>"))
    fig.add_hline(y=threshold_pct, line_dash="dot", line_color=theme.MUTED, line_width=1)
    fig.add_hline(y=-threshold_pct, line_dash="dot", line_color=theme.MUTED, line_width=1)
    fig.update_yaxes(ticksuffix="%")
    return theme.plotly_layout(fig, 240, legend=False)


def waterfall(row: pd.Series, cur: str) -> go.Figure:
    """Bridge from seller-reported revenue to order-derived net sales for one month."""
    reported = float(row["reported_revenue"])
    net = float(row["net_sales"])
    gross = float(row["gross_sales"])
    refunds = float(row["refunds_posted"])
    cancelled = float(row["cancelled_value"])
    # Decompose: reported -> remove cancelled -> remove refunds -> residual -> net sales
    steps = [("Seller-reported", reported, "absolute")]
    rem = reported
    if abs(reported - (gross + cancelled)) < abs(reported - gross):
        steps.append(("Less cancelled orders", -cancelled, "relative")); rem -= cancelled
    steps.append(("Less refunds posted", -refunds, "relative")); rem -= refunds
    residual = net - rem
    if abs(residual) > 0.5:
        steps.append(("Unexplained residual", residual, "relative"))
    steps.append(("Order-derived net sales", net, "total"))
    fig = go.Figure(go.Waterfall(
        x=[s[0] for s in steps], y=[s[1] for s in steps], measure=[s[2] for s in steps],
        connector=dict(line=dict(color=theme.LINE)), decreasing=dict(marker=dict(color=theme.RUST)), increasing=dict(marker=dict(color=theme.GREEN)),
        totals=dict(marker=dict(color=theme.INK_SOFT)), hovertemplate=f"%{{x}}<br>{cur} %{{y:,.0f}}<extra></extra>"))
    return theme.plotly_layout(fig, 300, legend=False)


def stacked_months(df: pd.DataFrame, x: str, y: str, group: str, cur: str) -> go.Figure:
    fig = go.Figure()
    for i, (name, g) in enumerate(df.groupby(group)):
        fig.add_bar(x=g[x], y=g[y], name=str(name), marker_color=theme.PLOTLY_COLORS[i % len(theme.PLOTLY_COLORS)],
                    hovertemplate=f"%{{x}}<br>{name} {cur} %{{y:,.0f}}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.3)
    return theme.plotly_layout(fig, 300)


def share_bars(df: pd.DataFrame, label: str, value: str, top: int = 10) -> go.Figure:
    d = df.head(top).iloc[::-1]
    fig = go.Figure(go.Bar(x=d[value], y=d[label], orientation="h", marker_color=theme.GREEN, hovertemplate="%{y}<br>%{x:.1f}%<extra></extra>"))
    fig.update_xaxes(ticksuffix="%")
    return theme.plotly_layout(fig, 28 * len(d) + 60, legend=False)


def line(df: pd.DataFrame, x: str, y: str, name: str, suffix: str = "", color: str = theme.GREEN, height: int = 240) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines+markers", name=name, line=dict(color=color, width=2), marker=dict(size=5),
                               hovertemplate=f"%{{x}}<br>{name} %{{y:,.1f}}{suffix}<extra></extra>"))
    fig.update_yaxes(ticksuffix=suffix)
    return theme.plotly_layout(fig, height, legend=False)


def inventory_rollforward(rf: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=rf["period"], y=rf["expected"], name="Expected (roll-forward)", mode="lines+markers", line=dict(color=theme.INK_SOFT, dash="dot"))
    fig.add_scatter(x=rf["period"], y=rf["recorded"], name="Recorded count", mode="lines+markers", line=dict(color=theme.GREEN, width=2))
    return theme.plotly_layout(fig, 260)
