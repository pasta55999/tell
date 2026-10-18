from __future__ import annotations

import streamlit as st

from tell.ui import charts, components as c, data, state, theme


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    prod = data.products(bid, h)
    c.page_header("Products & margins", "SKU-level sales, margin, return rates and concentration over the full period.", eyebrow=brand["name"])
    if prod.empty:
        c.empty_state("No product sales", "Import orders with SKU-level lines to see product performance.")
        return
    top = prod.iloc[0]
    portfolio_rr = prod["refunded_units"].sum() / prod["units"].sum() * 100 if prod["units"].sum() else 0
    portfolio_gm = (prod["gross_sales"].sum() - prod["cogs"].sum()) / prod["gross_sales"].sum() * 100
    top3 = prod.head(3)["revenue_share_pct"].sum()
    rr_threshold = max(10.0, 2 * portfolio_rr)
    flagged_ret = prod[(prod["units"] >= 30) & (prod["return_rate_pct"] >= rr_threshold)]
    c.kpi_row([("Active SKUs", str(len(prod)), c.delta_text(f"{int(prod['units'].sum()):,} units sold", "neutral"), theme.COBALT),
               ("Top SKU share", c.pct(top["revenue_share_pct"]), c.delta_text(f"{top['sku']} · top-3 {top3:.0f}%", "risk" if top["revenue_share_pct"] >= 25 else "neutral"), theme.VIOLET),
               ("Portfolio gross margin", c.pct(portfolio_gm), c.delta_text("gross sales − COGS", "neutral"), theme.EMERALD),
               ("Portfolio return rate", c.pct(portfolio_rr), c.delta_text(f"{len(flagged_ret)} SKU(s) above {rr_threshold:.0f}%", "risk" if len(flagged_ret) else "good"), theme.CORAL if len(flagged_ret) else theme.EMERALD)])
    a, b = st.columns([1, 1], gap="large")
    with a:
        c.section("Share of gross sales", "top 10 SKUs · coral marks ≥ 25%")
        st.plotly_chart(charts.share_bars(prod, "sku", "revenue_share_pct", highlight_over=25), width="stretch", config={"displayModeBar": False})
    with b:
        c.section("Return rate by SKU", f"SKUs with 30+ units · coral marks ≥ {rr_threshold:.0f}%")
        rr = prod[prod["units"] >= 30].sort_values("return_rate_pct", ascending=False)
        st.plotly_chart(charts.share_bars(rr, "sku", "return_rate_pct", highlight_over=rr_threshold, color=theme.VIOLET), width="stretch", config={"displayModeBar": False})

    c.section("SKU table", "Ranked by gross sales · ▲ flags return rate above threshold or margin 10pp below portfolio")
    flag = [("▲" if (r["units"] >= 30 and r["return_rate_pct"] >= rr_threshold) or (r["gross_margin_pct"] <= portfolio_gm - 10) else "") for _, r in prod.iterrows()]
    show = prod[["sku", "name", "category", "units", "gross_sales", "revenue_share_pct", "cogs", "gross_margin_pct", "refunded_units", "return_rate_pct", "refunded_amount"]].rename(
        columns={"sku": "SKU", "name": "Product", "category": "Category", "units": "Units", "gross_sales": "Gross sales", "revenue_share_pct": "Share %", "cogs": "COGS",
                 "gross_margin_pct": "GM %", "refunded_units": "Refunded units", "return_rate_pct": "Return %", "refunded_amount": "Refunded value"})
    show.insert(0, "", flag)
    c.table(c.format_table(show, money_cols=["Gross sales", "COGS", "Refunded value"], pct_cols=["Share %", "GM %", "Return %"], int_cols=["Units", "Refunded units"], cur=cur), height=520,
            column_config={"": st.column_config.TextColumn("", width="small")})

    c.section("Unit cost and margin over time", "Recorded unit cost on order lines and resulting gross margin")
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
