from __future__ import annotations

import streamlit as st

from tell.analysis.rules.revenue import attribute_variance
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import charts, components as c, data, state


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    c.page_header("Revenue reconciliation", "Seller-reported revenue against net sales rebuilt from order and refund records.", eyebrow=brand["name"])
    rec = fin[fin["reported_revenue"].notna()] if not fin.empty else fin
    if rec.empty:
        c.empty_state("No seller statements", "Import the seller's monthly statements in Settings to reconcile reported revenue.")
        return

    reported, net = float(rec["reported_revenue"].sum()), float(rec["net_sales"].sum())
    breaches = rec[rec["revenue_variance_pct"].abs() >= 2]
    c.kpi_row([("Seller-reported revenue", c.money(reported, cur), f"{len(rec)} months"),
               ("Order-derived net sales", c.money(net, cur), "gross sales less refunds posted"),
               ("Variance", f"{reported - net:+,.0f}", c.pct((reported / net - 1) * 100 if net else None, signed=True)),
               ("Months breaching 2%", str(len(breaches)), ", ".join(breaches["period"]) if not breaches.empty else "none")])
    st.write("")
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.markdown("<h3>Reported vs supported, by month</h3>", unsafe_allow_html=True)
        st.plotly_chart(charts.reconciliation_bars(fin, cur), width="stretch", config={"displayModeBar": False})
    with b:
        st.markdown("<h3>Variance (% of net sales)</h3>", unsafe_allow_html=True)
        st.plotly_chart(charts.variance_bars(fin, cur), width="stretch", config={"displayModeBar": False})

    st.markdown("<h3>Monthly reconciliation</h3>", unsafe_allow_html=True)
    cols = ["period", "reported_revenue", "gms", "discounts", "gross_sales", "refunds_posted", "net_sales", "cancelled_value", "revenue_variance", "revenue_variance_pct"]
    show = rec[cols].rename(columns={"period": "Month", "reported_revenue": "Reported", "gms": "GMS", "discounts": "Discounts", "gross_sales": "Gross sales",
                                     "refunds_posted": "Refunds posted", "net_sales": "Net sales", "cancelled_value": "Cancelled (memo)", "revenue_variance": "Variance", "revenue_variance_pct": "Var %"})
    c.table(c.format_table(show, money_cols=["Reported", "GMS", "Discounts", "Gross sales", "Refunds posted", "Net sales", "Cancelled (memo)", "Variance"], pct_cols=["Var %"], cur=cur), height=440)
    st.download_button("Export reconciliation (CSV)", df_to_csv(rec[cols].round(2)), file_name=f"{brand['slug']}-reconciliation.csv", mime="text/csv")

    c.divider()
    st.markdown("<h3>Drill into a month</h3>", unsafe_allow_html=True)
    default = list(rec["period"]).index(breaches["period"].iloc[0]) if not breaches.empty else len(rec) - 1
    period = st.selectbox("Month", list(rec["period"]), index=default, label_visibility="collapsed")
    row = rec[rec["period"] == period].iloc[0]
    label, residual = attribute_variance(row)
    x, y = st.columns([2, 3], gap="large")
    with x:
        c.kpi("Reported", c.money(row["reported_revenue"], cur))
        c.kpi("Net sales (supported)", c.money(row["net_sales"], cur), f"gross {c.money(row['gross_sales'], cur)} - refunds {c.money(row['refunds_posted'], cur)}")
        c.kpi("Variance", f"{row['revenue_variance']:+,.0f}", c.pct(row["revenue_variance_pct"], signed=True))
        if abs(row["revenue_variance_pct"]) < 2:
            c.caption("Within the 2% tolerance; no finding raised for this month.")
        elif label:
            c.caption(f"The variance is approximately {label} (residual {c.money(residual, cur)}). This points to a definitional difference, which the seller should confirm.")
        else:
            c.caption("The variance does not match refunds, cancellations, shipping or discounts in any combination; it needs an explanation from the seller.")
    with y:
        st.plotly_chart(charts.waterfall(row, cur), width="stretch", config={"displayModeBar": False})

    conn = state.conn()
    t1, t2, t3 = st.tabs([f"Completed orders ({int(row['orders_completed'])})", f"Refunds posted ({int(row['refunds_posted_count'])})", f"Cancelled orders ({int(row['orders_cancelled'])})"])
    with t1:
        df = repo.orders_in_period(conn, bid, period, "completed")
        c.table(c.format_table(df.drop(columns=["id"]), money_cols=["gross_amount", "discount_amount", "shipping_amount", "net_amount"], cur=cur), height=320)
        st.download_button("Export orders (CSV)", df_to_csv(df), file_name=f"{brand['slug']}-orders-{period}.csv", mime="text/csv", key="dl_o")
    with t2:
        df = repo.refunds_in_period(conn, bid, period)
        c.table(c.format_table(df.drop(columns=["id"]), money_cols=["amount"], cur=cur), height=320)
        st.download_button("Export refunds (CSV)", df_to_csv(df), file_name=f"{brand['slug']}-refunds-{period}.csv", mime="text/csv", key="dl_r")
    with t3:
        df = repo.orders_in_period(conn, bid, period, "cancelled")
        c.table(c.format_table(df.drop(columns=["id"]), money_cols=["gross_amount", "discount_amount", "shipping_amount", "net_amount"], cur=cur), height=320)
