from __future__ import annotations

import streamlit as st

from tell.analysis import metrics
from tell.analysis.conventions import DEFINITIONS
from tell.ui import charts, components as c, data, state


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    c.page_header("Financials", "Monthly performance derived from order, refund, cost and advertising records.", eyebrow=brand["name"])
    if fin.empty:
        c.empty_state("No data", "Import orders to see financial performance.")
        return
    t = metrics.period_totals(fin)
    c.kpi_row([("Gross sales", c.money(t["gross_sales"], cur), f"GMS {c.money(t['gms'], cur)} less discounts {c.money(t['discounts'], cur)}"),
               ("Net sales", c.money(t["net_sales"], cur), f"after {c.money(t['refunds_posted'], cur)} refunds"),
               ("Gross profit", c.money(t["gross_profit"], cur), c.pct(t["gross_margin_pct"]) + " margin"),
               ("Contribution proxy", c.money(t["contribution_proxy"], cur), "before fulfilment & overheads")])
    st.write("")

    tab1, tab2, tab3 = st.tabs(["Monthly P&L", "Products & categories", "Definitions"])
    with tab1:
        st.plotly_chart(charts.revenue_margin(fin, cur), width="stretch", config={"displayModeBar": False})
        cols = ["period", "orders_completed", "gms", "discounts", "gross_sales", "refunds_posted", "net_sales", "cogs", "gross_profit", "gross_margin_pct", "ad_spend", "ad_pct_of_gross_sales", "contribution_proxy", "aov"]
        show = fin[cols].rename(columns={"period": "Month", "orders_completed": "Orders", "gms": "GMS", "discounts": "Discounts", "gross_sales": "Gross sales",
                                         "refunds_posted": "Refunds", "net_sales": "Net sales", "cogs": "COGS", "gross_profit": "Gross profit", "gross_margin_pct": "GM %",
                                         "ad_spend": "Ad spend", "ad_pct_of_gross_sales": "Ads % sales", "contribution_proxy": "Contribution proxy", "aov": "AOV"})
        c.table(c.format_table(show, money_cols=["GMS", "Discounts", "Gross sales", "Refunds", "Net sales", "COGS", "Gross profit", "Ad spend", "Contribution proxy", "AOV"],
                               pct_cols=["GM %", "Ads % sales"], int_cols=["Orders"], cur=cur), height=460)
        c.note("Contribution proxy = gross profit - advertising. Excludes fulfilment, payroll, payment fees, software and rent. It is not EBITDA.")
    with tab2:
        prod = data.products(bid, h)
        cats = metrics.category_table(prod)
        a, b = st.columns([1, 1], gap="large")
        with a:
            st.markdown("<h3>Category share of gross sales</h3>", unsafe_allow_html=True)
            st.plotly_chart(charts.share_bars(cats, "category", "revenue_share_pct"), width="stretch", config={"displayModeBar": False})
        with b:
            st.markdown("<h3>Category margins</h3>", unsafe_allow_html=True)
            c.table(c.format_table(cats[["category", "skus", "units", "gross_sales", "gross_margin_pct", "refunded_amount"]].rename(
                columns={"category": "Category", "skus": "SKUs", "units": "Units", "gross_sales": "Gross sales", "gross_margin_pct": "GM %", "refunded_amount": "Refunded"}),
                money_cols=["Gross sales", "Refunded"], pct_cols=["GM %"], int_cols=["SKUs", "Units"], cur=cur))
        st.markdown("<h3>Gross sales by category and month</h3>", unsafe_allow_html=True)
        pm = data.product_monthly(bid, h)
        by_cat = pm.groupby(["period", "category"], as_index=False)["gross_sales"].sum()
        st.plotly_chart(charts.stacked_months(by_cat, "period", "gross_sales", "category", cur), width="stretch", config={"displayModeBar": False})
    with tab3:
        for k, v in DEFINITIONS.items():
            st.markdown(f"**{k}.** {v}")
