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


# ---------------------------------------------------------------- v3: bespoke diligence visuals

def annual_bridge(fin: pd.DataFrame, cur: str, attribute) -> go.Figure:
    """Bridge from total seller-reported revenue to supported net sales, decomposed using the
    per-month variance attribution (cancelled orders included, refunds not deducted, residual)."""
    rec = fin[fin["reported_revenue"].notna()]
    reported, net = float(rec["reported_revenue"].sum()), float(rec["net_sales"].sum())
    cancelled = refunds = 0.0
    for _, r in rec.iterrows():
        if abs(r["revenue_variance_pct"]) < 2:
            continue
        label, _ = attribute(r)
        if label and "cancelled" in label:
            cancelled += float(r["cancelled_value"])
        if label and "refunds" in label:
            refunds += float(r["refunds_posted"])
    residual = (reported - cancelled - refunds) - net
    steps = [("Seller-<br>reported", reported, "absolute")]
    if cancelled:
        steps.append(("Cancelled orders<br>counted as sales", -cancelled, "relative"))
    if refunds:
        steps.append(("Refunds<br>not deducted", -refunds, "relative"))
    steps.append(("Rounding &<br>in-tolerance months", -residual, "relative"))
    steps.append(("Supported<br>net sales", net, "total"))
    fig = go.Figure(go.Waterfall(
        x=[s[0] for s in steps], y=[s[1] for s in steps], measure=[s[2] for s in steps],
        text=[f"{cur} {abs(s[1]):,.0f}" for s in steps], textposition="outside", textfont=dict(size=11, color=theme.INK),
        connector=dict(line=dict(color=theme.LINE_STRONG, width=1)), decreasing=dict(marker=dict(color=S["variance"])), increasing=dict(marker=dict(color=S["net"])),
        totals=dict(marker=dict(color=theme.SLATE)), hovertemplate=f"%{{x}}<br>{cur} %{{y:,.0f}}<extra></extra>"))
    fig.update_layout(waterfallgap=0.4)
    fig.update_yaxes(range=[min(net, reported) * 0.9, reported * 1.06])
    fig.update_xaxes(tickangle=0, tickfont=dict(size=11))
    return theme.plotly_layout(fig, 330, legend=False)


def margin_story(fin: pd.DataFrame, cur: str) -> go.Figure:
    """Linked panels: gross sales vs COGS, then gross margin / discount / refund rates."""
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.55, 0.45], vertical_spacing=0.08)
    fig.add_bar(x=fin["period"], y=fin["gross_sales"], name=f"Gross sales ({cur})", marker_color=theme.COBALT, marker_line_width=0, row=1, col=1,
                hovertemplate=f"Gross sales {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_bar(x=fin["period"], y=fin["cogs"], name=f"COGS ({cur})", marker_color=theme.VIOLET, marker_line_width=0, row=1, col=1,
                hovertemplate=f"COGS {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_scatter(x=fin["period"], y=fin["gross_margin_pct"], name="Gross margin %", mode="lines+markers", line=dict(color=theme.EMERALD, width=2.4), marker=dict(size=6), row=2, col=1,
                    hovertemplate="Gross margin %{y:.1f}%<extra></extra>")
    fig.add_scatter(x=fin["period"], y=fin["discount_rate_pct"], name="Discount rate %", mode="lines+markers", line=dict(color=theme.AMBER, width=1.8, dash="dot"), marker=dict(size=5), row=2, col=1,
                    hovertemplate="Discounts %{y:.1f}% of GMS<extra></extra>")
    fig.add_scatter(x=fin["period"], y=fin["refund_rate_pct"], name="Refund rate % (cohort)", mode="lines+markers", line=dict(color=theme.CORAL, width=1.8, dash="dot"), marker=dict(size=5), row=2, col=1,
                    hovertemplate="Refunds %{y:.1f}% of cohort sales<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.3)
    fig.update_yaxes(ticksuffix="%", row=2, col=1)
    fig = theme.plotly_layout(fig, 430, hovermode="x unified")
    fig.update_xaxes(showgrid=False, linecolor=theme.LINE, showline=True)
    fig.update_yaxes(gridcolor=theme.LINE)
    return fig


def refund_cohorts(lags: pd.DataFrame, cur: str) -> go.Figure:
    """Refund value by original order month, split by lag bucket."""
    if lags.empty:
        return go.Figure()
    buckets = pd.cut(lags["lag_days"], bins=[-1, 30, 45, 90, 10_000], labels=["0-30 days", "31-45 days", "46-90 days", "90+ days"])
    g = lags.assign(bucket=buckets).groupby(["order_period", "bucket"], observed=False)["amount"].sum().unstack(fill_value=0)
    colors = {"0-30 days": theme.COBALT, "31-45 days": "#9FB1FF", "46-90 days": theme.AMBER, "90+ days": theme.CORAL}
    fig = go.Figure()
    for col in g.columns:
        fig.add_bar(x=g.index, y=g[col], name=str(col), marker_color=colors[str(col)], marker_line_width=0,
                    hovertemplate=f"{col}: {cur} %{{y:,.0f}}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.35)
    return theme.plotly_layout(fig, 300, hovermode="x unified")


def lag_scatter(lags: pd.DataFrame, highlight_period: str | None, cur: str) -> go.Figure:
    """Each refund as a point: order date vs lag; the highlighted posting month in coral."""
    d = lags.copy()
    hl = d["refund_period"] == highlight_period if highlight_period else pd.Series(False, index=d.index)
    fig = go.Figure()
    fig.add_scatter(x=d.loc[~hl, "order_date"], y=d.loc[~hl, "lag_days"], mode="markers", name="Refunds", marker=dict(size=6, color=theme.COBALT, opacity=0.55),
                    customdata=d.loc[~hl, ["refund_ref", "amount"]], hovertemplate="%{customdata[0]}<br>order %{x}<br>lag %{y} days<br>" + cur + " %{customdata[1]:,.0f}<extra></extra>")
    if hl.any():
        fig.add_scatter(x=d.loc[hl, "order_date"], y=d.loc[hl, "lag_days"], mode="markers", name=f"Posted {highlight_period}", marker=dict(size=8, color=theme.CORAL, symbol="diamond"),
                        customdata=d.loc[hl, ["refund_ref", "amount"]], hovertemplate="%{customdata[0]}<br>order %{x}<br>lag %{y} days<br>" + cur + " %{customdata[1]:,.0f}<extra></extra>")
    fig.add_hline(y=45, line_dash="dot", line_color=theme.MUTED, line_width=1, annotation_text="45-day late threshold", annotation_position="top left", annotation_font=dict(size=10, color=theme.MUTED))
    fig.update_yaxes(title=None, ticksuffix=" d")
    return theme.plotly_layout(fig, 300)


def contribution_view(prod: pd.DataFrame, top: int = 10) -> go.Figure:
    """Revenue share vs gross-profit share per SKU (ranked by revenue)."""
    d = prod.head(top).copy()
    gp_total = float(prod["gross_profit"].sum()) or 1.0
    d["gp_share"] = d["gross_profit"] / gp_total * 100
    d = d.iloc[::-1]
    fig = go.Figure()
    fig.add_bar(y=d["sku"], x=d["revenue_share_pct"], orientation="h", name="Share of gross sales", marker_color=theme.COBALT, marker_line_width=0,
                hovertemplate="%{y}<br>%{x:.1f}% of gross sales<extra></extra>")
    fig.add_bar(y=d["sku"], x=d["gp_share"], orientation="h", name="Share of gross profit", marker_color=theme.EMERALD, marker_line_width=0,
                hovertemplate="%{y}<br>%{x:.1f}% of gross profit<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
    fig.update_xaxes(ticksuffix="%")
    return theme.plotly_layout(fig, 34 * len(d) + 70)


def highlight_line(df: pd.DataFrame, x: str, y: str, name: str, highlight: list[str], suffix: str = "", color: str = theme.COBALT, baseline: float | None = None, height: int = 240) -> go.Figure:
    fig = line(df, x, y, name, suffix, color, height, baseline)
    hl = df[df[x].isin(highlight)]
    if not hl.empty:
        fig.add_scatter(x=hl[x], y=hl[y], mode="markers", name="Flagged", marker=dict(size=12, color=theme.CORAL, symbol="diamond"), hovertemplate=f"%{{x}}<br>{name} %{{y:,.1f}}{suffix}<extra></extra>")
    return fig


def cost_vs_invoice(recorded: pd.DataFrame, receipts: pd.DataFrame, cur: str) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=recorded["period"], y=recorded["avg_unit_cost"], mode="lines+markers", name="Unit cost used in COGS", line=dict(color=theme.COBALT, width=2.2), marker=dict(size=6),
                    hovertemplate=f"%{{x}}<br>recorded {cur} %{{y:,.2f}}<extra></extra>")
    fig.add_scatter(x=receipts["received_date"].str[:7], y=receipts["unit_cost"], mode="markers", name="Supplier invoice cost", marker=dict(size=10, color=theme.VIOLET, symbol="square"),
                    customdata=receipts["receipt_ref"], hovertemplate=f"%{{customdata}}<br>invoice {cur} %{{y:,.2f}}<extra></extra>")
    return theme.plotly_layout(fig, 260)


def statement_vs_platform(fin: pd.DataFrame, cur: str, highlight: str | None = None) -> go.Figure:
    df = fin[fin["reported_ad_spend"].notna()]
    fig = go.Figure()
    fig.add_bar(x=df["period"], y=df["ad_spend"], name="Platform records", marker_color=theme.COBALT, marker_line_width=0, hovertemplate=f"Platform {cur} %{{y:,.0f}}<extra></extra>")
    fig.add_bar(x=df["period"], y=df["reported_ad_spend"], name="Seller statement", marker_color=[S["variance"] if p == highlight else theme.VIOLET for p in df["period"]], marker_line_width=0,
                hovertemplate=f"Statement {cur} %{{y:,.0f}}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.3)
    return theme.plotly_layout(fig, 260, hovermode="x unified")


