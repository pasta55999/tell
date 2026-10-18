from __future__ import annotations

import streamlit as st

from tell.ui import charts, components as c, data, state


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
    c.kpi_row([("Active SKUs", str(len(prod)), f"{int(prod['units'].sum()):,} units sold"),
               ("Top SKU share", c.pct(top["revenue_share_pct"]), f"{top['sku']} · top-3 {prod.head(3)['revenue_share_pct'].sum():.0f}%"),
               ("Portfolio gross margin", c.pct((prod['gross_sales'].sum() - prod['cogs'].sum()) / prod['gross_sales'].sum() * 100), None),
               ("Portfolio return rate", c.pct(portfolio_rr), "refunded units / units sold")])
    st.write("")
    a, b = st.columns([1, 1], gap="large")
    with a:
        st.markdown("<h3>Share of gross sales (top 10)</h3>", unsafe_allow_html=True)
        st.plotly_chart(charts.share_bars(prod, "sku", "revenue_share_pct"), width="stretch", config={"displayModeBar": False})
    with b:
        st.markdown("<h3>Return rate by SKU (30+ units)</h3>", unsafe_allow_html=True)
        rr = prod[prod["units"] >= 30].sort_values("return_rate_pct", ascending=False)
        st.plotly_chart(charts.share_bars(rr, "sku", "return_rate_pct"), width="stretch", config={"displayModeBar": False})

    st.markdown("<h3>SKU table</h3>", unsafe_allow_html=True)
    show = prod[["sku", "name", "category", "units", "gross_sales", "revenue_share_pct", "cogs", "gross_margin_pct", "refunded_units", "return_rate_pct", "refunded_amount"]].rename(
        columns={"sku": "SKU", "name": "Product", "category": "Category", "units": "Units", "gross_sales": "Gross sales", "revenue_share_pct": "Share %", "cogs": "COGS",
                 "gross_margin_pct": "GM %", "refunded_units": "Refunded units", "return_rate_pct": "Return %", "refunded_amount": "Refunded value"})
    c.table(c.format_table(show, money_cols=["Gross sales", "COGS", "Refunded value"], pct_cols=["Share %", "GM %", "Return %"], int_cols=["Units", "Refunded units"], cur=cur), height=520)

    c.divider()
    st.markdown("<h3>Unit cost and margin over time</h3>", unsafe_allow_html=True)
    pm = data.product_monthly(bid, h)
    sku = st.selectbox("SKU", list(prod["sku"]), label_visibility="collapsed")
    d = pm[pm["sku"] == sku].copy()
    if not d.empty:
        d["unit_cost"] = d["cogs"] / d["units"]
        d["gm_pct"] = (d["gross_sales"] - d["cogs"]) / d["gross_sales"] * 100
        x, y = st.columns(2, gap="large")
        with x:
            st.plotly_chart(charts.line(d, "period", "unit_cost", "Recorded unit cost"), width="stretch", config={"displayModeBar": False})
        with y:
            st.plotly_chart(charts.line(d, "period", "gm_pct", "Gross margin", "%"), width="stretch", config={"displayModeBar": False})
