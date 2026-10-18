"""Operations: products & concentration, refund patterns, advertising, inventory & suppliers.
Each view answers a specific diligence question with a visual chosen for it."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tell.db import repository as repo
from tell.ui import charts, components as c, data, state, theme

VIEWS = ["Products & concentration", "Refund patterns", "Advertising", "Inventory & suppliers"]


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    c.page_header("Operations", eyebrow=brand["name"])
    h = data.data_hash(bid)
    default = st.session_state.pop("ops_view", None) or VIEWS[0]
    view = st.segmented_control("View", VIEWS, default=default, label_visibility="collapsed", key="ops_seg")
    if view == VIEWS[0]:
        _products(bid, cur, h)
    elif view == VIEWS[1]:
        _refunds(bid, cur, h)
    elif view == VIEWS[2]:
        _advertising(bid, cur, h)
    else:
        _inventory(bid, cur, h)


# ---------------------------------------------------------------- products

def _products(bid: int, cur: str, h: str) -> None:
    prod = data.products(bid, h)
    if prod.empty:
        c.empty_state("No product sales", "Import orders with SKU-level lines.")
        return
    top = prod.iloc[0]
    portfolio_rr = prod["refunded_units"].sum() / prod["units"].sum() * 100 if prod["units"].sum() else 0
    portfolio_gm = (prod["gross_sales"].sum() - prod["cogs"].sum()) / prod["gross_sales"].sum() * 100
    gp_total = prod["gross_profit"].sum()
    rr_threshold = max(10.0, 2 * portfolio_rr)
    flagged_ret = prod[(prod["units"] >= 30) & (prod["return_rate_pct"] >= rr_threshold)]
    c.hero([("One SKU carries", f"{top['revenue_share_pct']:.0f}%", f"of gross sales and {top['gross_profit'] / gp_total * 100:.0f}% of gross profit · {top['sku']}", theme.VIOLET if top["revenue_share_pct"] >= 25 else theme.INK),
            ("Range", f"{len(prod)} SKUs", f"{int(prod['units'].sum()):,} units · portfolio margin {portfolio_gm:.1f}%"),
            ("Returns", f"{portfolio_rr:.1f}%", f"{len(flagged_ret)} SKU(s) above {rr_threshold:.0f}%", theme.CORAL if len(flagged_ret) else theme.EMERALD)], small=True)
    a, b = st.columns([3, 2], gap="large")
    with a:
        c.section("Which SKUs account for revenue and gross profit", "Top 10 by gross sales · share of total")
        st.plotly_chart(charts.contribution_view(prod), width="stretch", config={"displayModeBar": False})
    with b:
        c.section("Return rate by SKU", f"30+ units · coral ≥ {rr_threshold:.0f}%")
        rr = prod[prod["units"] >= 30].sort_values("return_rate_pct", ascending=False)
        st.plotly_chart(charts.share_bars(rr, "sku", "return_rate_pct", highlight_over=rr_threshold, color=theme.VIOLET), width="stretch", config={"displayModeBar": False})
    c.section("SKU table", "▲ flags a return rate above threshold or a margin 10pp below the portfolio")
    flag = [("▲" if (r["units"] >= 30 and r["return_rate_pct"] >= rr_threshold) or (r["gross_margin_pct"] <= portfolio_gm - 10) else "") for _, r in prod.iterrows()]
    show = prod[["sku", "name", "category", "units", "gross_sales", "revenue_share_pct", "gross_profit", "gross_margin_pct", "refunded_units", "return_rate_pct"]].rename(
        columns={"sku": "SKU", "name": "Product", "category": "Category", "units": "Units", "gross_sales": "Gross sales", "revenue_share_pct": "Share %", "gross_profit": "Gross profit",
                 "gross_margin_pct": "GM %", "refunded_units": "Refunded units", "return_rate_pct": "Return %"})
    show.insert(0, "", flag)
    c.table(c.format_table(show, money_cols=["Gross sales", "Gross profit"], pct_cols=["Share %", "GM %", "Return %"], int_cols=["Units", "Refunded units"], cur=cur), height=480, column_config={"": st.column_config.TextColumn("", width="small")})
    c.section("Unit cost and margin over time for one SKU")
    pm = data.product_monthly(bid, h)
    sel, _ = st.columns([2, 5])
    with sel:
        sku = st.selectbox("SKU", list(prod["sku"]), label_visibility="collapsed")
    d = pm[pm["sku"] == sku].copy()
    if not d.empty:
        d["unit_cost"] = d["cogs"] / d["units"]
        d["gm_pct"] = (d["gross_sales"] - d["cogs"]) / d["gross_sales"] * 100
        x, y = st.columns(2, gap="large")
        with x:
            st.plotly_chart(charts.line(d, "period", "unit_cost", f"Recorded unit cost ({cur})", color=theme.COBALT), width="stretch", config={"displayModeBar": False})
        with y:
            st.plotly_chart(charts.line(d, "period", "gm_pct", "Gross margin", "%", color=theme.EMERALD, baseline=portfolio_gm), width="stretch", config={"displayModeBar": False})


# ---------------------------------------------------------------- refunds

def _refunds(bid: int, cur: str, h: str) -> None:
    conn = state.conn()
    lags = repo.refund_lags(conn, bid)
    fin = data.financials(bid, h)
    if lags.empty:
        c.empty_state("No refunds", "Import refunds linked to orders to see cohort and delay patterns.")
        return
    late = lags[lags["lag_days"] > 45]
    c.hero([("Refunds", f"{len(lags):,}", f"{c.money(lags['amount'].sum(), cur)} · {lags['amount'].sum() / fin['gross_sales'].sum() * 100:.1f}% of gross sales · median delay {lags['lag_days'].median():.0f} days"),
            ("Posted > 45 days after sale", f"{len(late)}", f"{c.money(late['amount'].sum(), cur)} · {late['amount'].sum() / lags['amount'].sum() * 100:.0f}% of refund value", theme.CORAL if len(late) >= 8 else theme.INK),
            ("Reason most cited", lags["reason"].value_counts().index[0], f"{lags['reason'].value_counts().iloc[0]} refunds")], small=True)
    a, b = st.columns([3, 2], gap="large")
    with a:
        c.section("When were the refunds for each month's sales actually paid?", "Refund value by original order month, split by delay")
        st.plotly_chart(charts.refund_cohorts(lags, cur), width="stretch", config={"displayModeBar": False})
    with b:
        c.section("Cohort refund rate", "Refunds matched to the order month ÷ that month's gross sales")
        st.plotly_chart(charts.line(fin, "period", "refund_rate_pct", "Cohort refund rate", "%", theme.CORAL, 300, baseline=float(fin["refund_rate_pct"].median())), width="stretch", config={"displayModeBar": False})
    c.section("Every refund by order date and delay", "Diamonds: refunds posted in the month with the largest late cluster")
    worst = late.groupby("refund_period")["amount"].sum().idxmax() if not late.empty else None
    st.plotly_chart(charts.lag_scatter(lags, worst, cur), width="stretch", config={"displayModeBar": False})
    c.section("Refund ledger")
    show = lags[["refund_ref", "refund_date", "order_ref", "order_date", "lag_days", "amount", "reason"]].rename(columns={"refund_ref": "Refund", "refund_date": "Posted", "order_ref": "Order", "order_date": "Ordered", "lag_days": "Delay (days)", "amount": "Amount", "reason": "Reason"})
    show.insert(0, "", ["▲" if v > 45 else "" for v in lags["lag_days"]])
    c.table(c.format_table(show, money_cols=["Amount"], cur=cur), height=380, column_config={"": st.column_config.TextColumn("", width="small", help="▲ posted more than 45 days after the order")})


# ---------------------------------------------------------------- advertising

def _advertising(bid: int, cur: str, h: str) -> None:
    ads = data.ad_spend(bid, h)
    fin = data.financials(bid, h)
    if ads.empty:
        c.empty_state("No advertising records", "Import monthly ad spend per channel.")
        return
    ch = data.channels(bid, h)
    total = float(ads["spend"].sum())
    with_attr = ch[ch["attribution_available"]]
    max_var = fin["ad_variance_pct"].abs().max() if fin["ad_variance_pct"].notna().any() else None
    c.hero([("Spend", c.money(total, cur), f"{total / fin['gross_sales'].sum() * 100:.1f}% of gross sales · {len(ch)} channels"),
            ("Return verified for", f"{len(with_attr)} of {len(ch)} channels", (", ".join(f"{r['channel']} {r['roas']:.1f}x" for _, r in with_attr.iterrows()) or "no channel reports attribution") + f" · {c.money(ch[~ch['attribution_available']]['spend'].sum(), cur)} unverified", theme.EMERALD if len(with_attr) else theme.AMBER),
            ("Statement vs platform", c.pct(max_var) if max_var is not None else "n/a", "largest monthly gap to the seller's accounts", theme.CORAL if (max_var or 0) >= 10 else theme.EMERALD)], small=True)
    a, b = st.columns([3, 2], gap="large")
    with a:
        c.section("Spend by channel", cur)
        st.plotly_chart(charts.stacked_months(ads, "period", "spend", "channel", cur), width="stretch", config={"displayModeBar": False})
    with b:
        c.section("Spend intensity", "% of gross sales · dotted line = median")
        st.plotly_chart(charts.line(fin, "period", "ad_pct_of_gross_sales", "Ads % of gross sales", "%", height=300, baseline=float(fin["ad_pct_of_gross_sales"].median())), width="stretch", config={"displayModeBar": False})
    c.section("Spend versus attributable revenue", "ROAS shown only where the platform reports attributed revenue for every month")
    show = ch.copy()
    show["roas"] = show.apply(lambda r: f"{r['roas']:.2f}x (platform-attributed, unverified)" if pd.notna(r["roas"]) else "not available — no attribution data", axis=1)
    show["share"] = show["spend"] / total * 100
    c.table(c.format_table(show[["channel", "spend", "share", "impressions", "clicks", "attributed_revenue", "roas"]].rename(
        columns={"channel": "Channel", "spend": "Spend", "share": "Share %", "impressions": "Impressions", "clicks": "Clicks", "attributed_revenue": "Attributed revenue", "roas": "ROAS"}),
        money_cols=["Spend", "Attributed revenue"], pct_cols=["Share %"], int_cols=["Impressions", "Clicks"], cur=cur))
    c.insight("Tell does not infer attribution from aggregate sales, so no blended ROAS or causal uplift is shown. Platform-attributed revenue is the platform's own claim and is not independently verified.", "cobalt")
    if fin["reported_ad_spend"].notna().any():
        c.section("Seller statements against platform billing", "▲ months where the gap is at least 10%")
        worst = fin.loc[fin["ad_variance_pct"].abs().idxmax(), "period"] if max_var and max_var >= 10 else None
        st.plotly_chart(charts.statement_vs_platform(fin, cur, worst), width="stretch", config={"displayModeBar": False})


# ---------------------------------------------------------------- inventory

def _inventory(bid: int, cur: str, h: str) -> None:
    conn = state.conn()
    rf = data.inventory_rollforward(bid, h)
    if rf.empty:
        c.empty_state("No inventory snapshots", "Import at least two month-end snapshots per SKU and supplier receipts to run the roll-forward.")
        return
    base = (rf["opening"] + rf["received"]).clip(lower=1)
    flagged = rf[(rf["variance"].abs() >= 5) & (rf["variance"].abs() / base * 100 >= 3)]
    prod = data.products(bid, h)
    costs = prod.set_index("product_id")["standard_cost"] if not prod.empty else pd.Series(dtype=float)
    value_at_risk = float(sum(abs(r.variance) * float(costs.get(r.product_id, 0) or 0) for r in flagged.itertuples()))
    c.hero([("Does the stock reconcile?", f"{len(rf) - len(flagged)} of {len(rf)}", "SKU-months within 5 units and 3% of expected", theme.EMERALD if flagged.empty else theme.AMBER),
            ("SKUs with variances", str(flagged["sku"].nunique()), ", ".join(sorted(flagged["sku"].unique())) or "none", theme.CORAL if not flagged.empty else theme.EMERALD),
            ("Stock value at risk", c.money(value_at_risk, cur), f"net {int(flagged['variance'].sum()):+d} units × standard cost", theme.VIOLET)], small=True)
    c.section("Recorded count against the movement-based expectation", "Expected = previous count + receipts − units sold + restocked returns")
    skus = sorted(rf["sku"].unique())
    default = skus.index(flagged["sku"].iloc[0]) if not flagged.empty else 0
    sel, _ = st.columns([2, 5])
    with sel:
        sku = st.selectbox("SKU", skus, index=default, label_visibility="collapsed")
    d = rf[rf["sku"] == sku]
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.plotly_chart(charts.inventory_rollforward(d), width="stretch", config={"displayModeBar": False})
    with b:
        cum = int(d["variance"].sum())
        if cum == 0:
            c.insight(f"{sku} reconciles in every month.", "emerald")
        else:
            c.insight(f"{sku}: cumulative variance {cum:+d} units across {int((d['variance'] != 0).sum())} month(s). " + ("A persistent shortfall suggests shrinkage or unrecorded sales." if cum < 0 else "Stock above what movements support suggests phantom stock or missing sales records."), "coral")
        c.ledger([(r.period, f"{r.variance:+d}", f"opening {r.opening} + in {r.received} − sold {r.sold} + back {r.restocked} = {r.expected}; counted {r.recorded}", r.variance != 0) for r in d.itertuples()])
    c.section("Supplier invoice cost against the cost used in margins", "▲ receipts priced 5% or more away from the order-line cost in the same month")
    receipts = repo.supplier_receipts(conn, bid)
    if receipts.empty:
        c.caption("No supplier receipts imported.")
        return
    rec_cost = repo.product_cost_by_month(conn, bid)
    r = receipts.assign(period=receipts["received_date"].str[:7]).merge(rec_cost[["period", "product_id", "avg_unit_cost"]], on=["period", "product_id"], how="left")
    r["variance_pct"] = (r["unit_cost"] / r["avg_unit_cost"] - 1) * 100
    bad = r[r["variance_pct"].abs() >= 5]
    if not bad.empty:
        pid = int(bad["product_id"].iloc[0])
        x, y = st.columns([3, 2], gap="large")
        with x:
            st.plotly_chart(charts.cost_vs_invoice(rec_cost[rec_cost["product_id"] == pid].sort_values("period"), receipts[receipts["product_id"] == pid], cur), width="stretch", config={"displayModeBar": False})
        with y:
            c.insight(f"{bad['sku'].iloc[0]}: {len(bad)} receipt(s) invoiced {bad['variance_pct'].iloc[0]:+.0f}% away from the unit cost on order lines. If the invoice is right, margin on this SKU is overstated.", "coral")
    show = r[["receipt_ref", "sku", "received_date", "supplier", "quantity", "unit_cost", "avg_unit_cost", "variance_pct"]].rename(
        columns={"receipt_ref": "Receipt", "sku": "SKU", "received_date": "Received", "supplier": "Supplier", "quantity": "Qty", "unit_cost": "Invoice unit cost", "avg_unit_cost": "Recorded unit cost", "variance_pct": "Var %"})
    show.insert(0, "", ["▲" if abs(v) >= 5 else "" for v in r["variance_pct"].fillna(0)])
    c.table(c.format_table(show, money_cols=["Invoice unit cost", "Recorded unit cost"], pct_cols=["Var %"], int_cols=["Qty"], cur=cur), height=340, column_config={"": st.column_config.TextColumn("", width="small")})
