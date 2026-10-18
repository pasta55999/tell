from __future__ import annotations

import streamlit as st

from tell.db import repository as repo
from tell.ui import charts, components as c, data, state, theme


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    c.page_header("Inventory", "Month-end counts reconciled to receipts, sales and restocked returns; supplier invoice costs against the unit cost used in margins.", eyebrow=brand["name"])
    rf = data.inventory_rollforward(bid, h)
    if rf.empty:
        c.empty_state("No inventory snapshots", "Import at least two month-end snapshots per SKU and supplier receipts to run the roll-forward.")
        return
    base = (rf["opening"] + rf["received"]).clip(lower=1)
    flagged = rf[(rf["variance"].abs() >= 5) & (rf["variance"].abs() / base * 100 >= 3)]
    costs = data.products(bid, h).set_index("product_id")["standard_cost"] if not data.products(bid, h).empty else None
    value_at_risk = float(sum(abs(r.variance) * float(costs.get(r.product_id, 0) or 0) for r in flagged.itertuples())) if costs is not None else None
    c.kpi_row([("SKUs tracked", str(rf["product_id"].nunique()), c.delta_text(f"{rf['period'].nunique()} months of snapshots", "neutral"), theme.COBALT),
               ("SKU-months reconciling", f"{len(rf) - len(flagged)} of {len(rf)}", c.delta_text("within 5 units and 3%", "good" if flagged.empty else "neutral"), theme.EMERALD),
               ("SKUs with variances", str(flagged["sku"].nunique()), c.delta_text(", ".join(sorted(flagged["sku"].unique())) if not flagged.empty else "none", "risk" if not flagged.empty else "good"), theme.CORAL if not flagged.empty else theme.EMERALD),
               ("Inventory value at risk", c.money(value_at_risk, cur) if value_at_risk is not None else "n/a", c.delta_text(f"net {int(flagged['variance'].sum()):+d} units × standard cost", "neutral"), theme.VIOLET)])

    c.section("Roll-forward by SKU", "Expected = previous count + receipts − units sold + restocked returns")
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
            c.insight(f"{sku}: cumulative variance {cum:+d} units across {int((d['variance'] != 0).sum())} month(s). " +
                      ("A persistent shortfall suggests shrinkage or unrecorded sales." if cum < 0 else "Stock above what movements support suggests phantom stock or missing sales records."), "coral")
        c.caption("Diamonds mark months where the recorded count departs from the roll-forward. A missing goods-received note would also produce a variance, so confirm receipts before concluding.")
    show = d[["period", "opening", "received", "sold", "restocked", "expected", "recorded", "variance"]].rename(
        columns={"period": "Month", "opening": "Opening", "received": "Received", "sold": "Sold", "restocked": "Restocked", "expected": "Expected", "recorded": "Recorded", "variance": "Variance"})
    show.insert(0, "", ["▲" if v != 0 else "" for v in d["variance"]])
    c.table(show, height=330, column_config={"": st.column_config.TextColumn("", width="small")})

    c.section("All variances", "Every SKU-month outside tolerance")
    if flagged.empty:
        c.caption("None.")
    else:
        c.table(flagged[["sku", "name", "period", "expected", "recorded", "variance"]].rename(columns={"sku": "SKU", "name": "Product", "period": "Month", "expected": "Expected", "recorded": "Recorded", "variance": "Variance"}), height=min(300, 38 * len(flagged) + 40))

    c.section("Supplier receipts vs recorded unit cost", "▲ marks receipts priced 5% or more away from the cost used on order lines in the same month")
    receipts = repo.supplier_receipts(state.conn(), bid)
    if receipts.empty:
        c.caption("No supplier receipts imported; cost reconciliation not available.")
        return
    rec_cost = repo.product_cost_by_month(state.conn(), bid)
    r = receipts.assign(period=receipts["received_date"].str[:7]).merge(rec_cost[["period", "product_id", "avg_unit_cost"]], on=["period", "product_id"], how="left")
    r["variance_pct"] = (r["unit_cost"] / r["avg_unit_cost"] - 1) * 100
    show = r[["receipt_ref", "sku", "received_date", "supplier", "quantity", "unit_cost", "avg_unit_cost", "variance_pct"]].rename(
        columns={"receipt_ref": "Receipt", "sku": "SKU", "received_date": "Received", "supplier": "Supplier", "quantity": "Qty", "unit_cost": "Invoice unit cost", "avg_unit_cost": "Recorded unit cost", "variance_pct": "Var %"})
    show.insert(0, "", ["▲" if abs(v) >= 5 else "" for v in r["variance_pct"].fillna(0)])
    c.table(c.format_table(show, money_cols=["Invoice unit cost", "Recorded unit cost"], pct_cols=["Var %"], int_cols=["Qty"], cur=cur), height=360, column_config={"": st.column_config.TextColumn("", width="small")})
