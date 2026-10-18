from __future__ import annotations

import streamlit as st

from tell.db import repository as repo
from tell.ui import charts, components as c, data, state


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    c.page_header("Inventory", "Month-end counts reconciled to receipts, sales and restocked returns; supplier costs against recorded unit costs.", eyebrow=brand["name"])
    rf = data.inventory_rollforward(bid, h)
    if rf.empty:
        c.empty_state("No inventory snapshots", "Import at least two month-end snapshots per SKU and supplier receipts to run the roll-forward.")
        return
    base = (rf["opening"] + rf["received"]).clip(lower=1)
    flagged = rf[(rf["variance"].abs() >= 5) & (rf["variance"].abs() / base * 100 >= 3)]
    c.kpi_row([("SKUs tracked", str(rf["product_id"].nunique()), f"{rf['period'].nunique()} months"),
               ("Months reconciling", f"{len(rf) - len(flagged)} of {len(rf)}", "SKU-months within tolerance"),
               ("SKUs with variances", str(flagged["sku"].nunique()), ", ".join(sorted(flagged["sku"].unique())) if not flagged.empty else "none"),
               ("Net unit variance", f"{int(flagged['variance'].sum()):+d}", "recorded minus expected, flagged months")])
    st.write("")
    st.markdown("<h3>Roll-forward by SKU</h3>", unsafe_allow_html=True)
    skus = sorted(rf["sku"].unique())
    default = skus.index(flagged["sku"].iloc[0]) if not flagged.empty else 0
    sku = st.selectbox("SKU", skus, index=default, label_visibility="collapsed")
    d = rf[rf["sku"] == sku]
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.plotly_chart(charts.inventory_rollforward(d), width="stretch", config={"displayModeBar": False})
    with b:
        c.caption("Expected = previous count + receipts - units sold + restocked returns (calendar month). A persistent negative gap suggests shrinkage or unrecorded sales; a positive gap suggests phantom stock or missing sales records.")
    show = d[["period", "opening", "received", "sold", "restocked", "expected", "recorded", "variance"]].rename(
        columns={"period": "Month", "opening": "Opening", "received": "Received", "sold": "Sold", "restocked": "Restocked", "expected": "Expected", "recorded": "Recorded", "variance": "Variance"})
    c.table(show, height=330)

    c.divider()
    st.markdown("<h3>Supplier receipts</h3>", unsafe_allow_html=True)
    receipts = repo.supplier_receipts(state.conn(), bid)
    if receipts.empty:
        c.caption("No supplier receipts imported; cost reconciliation not available.")
        return
    rec_cost = repo.product_cost_by_month(state.conn(), bid)
    r = receipts.assign(period=receipts["received_date"].str[:7]).merge(rec_cost[["period", "product_id", "avg_unit_cost"]], on=["period", "product_id"], how="left")
    r["variance_pct"] = (r["unit_cost"] / r["avg_unit_cost"] - 1) * 100
    show = r[["receipt_ref", "sku", "received_date", "supplier", "quantity", "unit_cost", "avg_unit_cost", "variance_pct"]].rename(
        columns={"receipt_ref": "Receipt", "sku": "SKU", "received_date": "Received", "supplier": "Supplier", "quantity": "Qty", "unit_cost": "Invoice unit cost", "avg_unit_cost": "Recorded unit cost", "variance_pct": "Var %"})
    c.table(c.format_table(show, money_cols=["Invoice unit cost", "Recorded unit cost"], pct_cols=["Var %"], int_cols=["Qty"], cur=cur), height=360)
