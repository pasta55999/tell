from __future__ import annotations

import streamlit as st

from tell.analysis.rules.revenue import attribute_variance
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import charts, components as c, data, state, theme


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    c.page_header("Revenue reconciliation", "Seller-reported revenue against net sales rebuilt from order and refund records. Trace any gap to the transactions behind it.", eyebrow=brand["name"])
    rec = fin[fin["reported_revenue"].notna()] if not fin.empty else fin
    if rec.empty:
        c.empty_state("No seller statements", "Import the seller's monthly statements in Settings & imports to reconcile reported revenue.")
        return

    reported, net, gross = float(rec["reported_revenue"].sum()), float(rec["net_sales"].sum()), float(rec["gross_sales"].sum())
    breaches = rec[rec["revenue_variance_pct"].abs() >= 2]
    var_pct = (reported / net - 1) * 100 if net else 0
    c.kpi_row([("Seller-reported revenue", c.money(reported, cur), c.delta_text(f"{len(rec)} months of management accounts", "neutral"), theme.VIOLET),
               ("Order-ledger gross sales", c.money(gross, cur), c.delta_text("completed orders after discounts", "neutral"), theme.COBALT),
               ("Refund-adjusted net sales", c.money(net, cur), c.delta_text(f"less {c.money(float(rec['refunds_posted'].sum()), cur)} refunds posted", "neutral"), theme.EMERALD),
               ("Unexplained by net sales", c.signed_money(reported - net, cur), c.delta_text(f"{var_pct:+.1f}% · {len(breaches)} month(s) breach 2%", "risk" if len(breaches) else "good"), theme.CORAL if len(breaches) else theme.EMERALD)])

    c.section("Reconciliation flow", "Full reported period")
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.plotly_chart(charts.reconciliation_flow({"reported": reported, "gross": gross, "net": net}, cur), width="stretch", config={"displayModeBar": False})
    with b:
        c.caption("Reported revenue should land close to refund-adjusted net sales. A figure that tracks gross sales instead suggests refunds were not deducted; a figure above gross sales suggests cancelled orders, shipping or VAT are included.")
        if breaches.empty:
            c.insight("All reported months reconcile within the 2% tolerance.", "emerald")
        else:
            c.insight(f"Months breaching tolerance: {', '.join(breaches['period'])}. Combined overstatement {c.signed_money(float(breaches['revenue_variance'].sum()), cur)}.", "coral")

    c.section("By month", "Seller-reported vs refund-adjusted net sales, and the variance against the ±2% threshold")
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.plotly_chart(charts.reconciliation_bars(fin, cur), width="stretch", config={"displayModeBar": False})
    with b:
        st.plotly_chart(charts.variance_bars(fin, cur), width="stretch", config={"displayModeBar": False})

    cols = ["period", "reported_revenue", "gms", "discounts", "gross_sales", "refunds_posted", "net_sales", "cancelled_value", "revenue_variance", "revenue_variance_pct"]
    show = rec[cols].rename(columns={"period": "Month", "reported_revenue": "Reported", "gms": "GMS", "discounts": "Discounts", "gross_sales": "Gross sales",
                                     "refunds_posted": "Refunds posted", "net_sales": "Net sales", "cancelled_value": "Cancelled (memo)", "revenue_variance": "Variance", "revenue_variance_pct": "Var %"})
    show.insert(0, "", ["▲" if abs(v) >= 2 else "" for v in rec["revenue_variance_pct"]])
    c.table(c.format_table(show, money_cols=["Reported", "GMS", "Discounts", "Gross sales", "Refunds posted", "Net sales", "Cancelled (memo)", "Variance"], pct_cols=["Var %"], cur=cur), height=440,
            column_config={"": st.column_config.TextColumn("", width="small", help="▲ marks months breaching the 2% threshold")})
    st.download_button("Export reconciliation (CSV)", df_to_csv(rec[cols].round(2)), file_name=f"{brand['slug']}-reconciliation.csv", mime="text/csv")

    c.section("Drill into a month", "Bridge from the seller's figure to the supported figure, with the underlying records")
    default = list(rec["period"]).index(breaches["period"].iloc[0]) if not breaches.empty else len(rec) - 1
    sel, _ = st.columns([2, 5])
    with sel:
        period = st.selectbox("Month", list(rec["period"]), index=default, label_visibility="collapsed")
    row = rec[rec["period"] == period].iloc[0]
    label, residual = attribute_variance(row)
    x, y = st.columns([2, 3], gap="large")
    with x:
        c.kpi("Reported", c.money(row["reported_revenue"], cur), None, theme.VIOLET, plain=True)
        c.kpi("Net sales (supported)", c.money(row["net_sales"], cur), c.esc(f"gross {c.money(row['gross_sales'], cur)} − refunds {c.money(row['refunds_posted'], cur)}"), theme.EMERALD, plain=True)
        tone = "risk" if abs(row["revenue_variance_pct"]) >= 2 else "good"
        c.kpi("Variance", c.signed_money(row["revenue_variance"], cur), c.delta_text(c.pct(row["revenue_variance_pct"], signed=True) + " of net sales", tone), theme.CORAL if tone == "risk" else theme.EMERALD, plain=True)
        if abs(row["revenue_variance_pct"]) < 2:
            c.insight("Within the 2% tolerance; no finding raised for this month.", "emerald")
        elif label:
            c.insight(f"The variance is approximately {label} (residual {c.money(residual, cur)}). This points to a definitional difference the seller should confirm.", "coral")
        else:
            c.insight("The variance does not match refunds, cancellations, shipping or discounts in any combination; it needs an explanation from the seller.", "coral")
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
