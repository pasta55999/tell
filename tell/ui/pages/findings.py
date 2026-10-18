from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st

from tell.analysis.engine import compare_runs, run_analysis, update_finding_status
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import components as c, data, state, theme


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    run = state.run()
    c.page_header("Findings", "Each finding is produced by a documented rule against the records and links to the rows that triggered it.", eyebrow=brand["name"])
    if run is None:
        if c.empty_state("No analysis run yet", "Run the analysis to reconcile the records and surface findings.", "Run analysis", key="fd_run"):
            with st.spinner("Analysing records..."):
                st.session_state.run_id = run_analysis(state.conn(), bid)
            st.rerun()
        return
    f = data.findings(int(run["id"]))
    if f.empty:
        c.empty_state("No findings", "The analysis completed without raising any findings on this data.")
        return

    sev = f["severity"].value_counts()
    c.kpi_row([("Findings", str(len(f)), f"run {run['id']}"),
               ("High or critical", str(int(sev.get("critical", 0) + sev.get("high", 0))), None),
               ("Quantified discrepancies", c.money(f[f["classification"] == "discrepancy"]["estimated_impact"].fillna(0).sum(), cur), "sum of discrepancy impacts"),
               ("Open", str(int((~f["status"].isin(["verified", "dismissed"])).sum())), "not yet verified or dismissed")])
    st.write("")

    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        sev_filter = st.multiselect("Severity", ["critical", "high", "medium", "low", "info"], default=[], placeholder="All severities", label_visibility="collapsed")
    with col2:
        cls_filter = st.multiselect("Type", list(theme.CLASS_LABELS), default=[], format_func=lambda k: theme.CLASS_LABELS[k], placeholder="All types", label_visibility="collapsed")
    with col3:
        hide_closed = st.toggle("Hide verified and dismissed", value=False)
    view = f.copy()
    if sev_filter:
        view = view[view["severity"].isin(sev_filter)]
    if cls_filter:
        view = view[view["classification"].isin(cls_filter)]
    if hide_closed:
        view = view[~view["status"].isin(["verified", "dismissed"])]

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown('<div class="tell-eyebrow">Ranked by severity, then impact</div>', unsafe_allow_html=True)
        options = view["id"].tolist()
        if not options:
            c.caption("No findings match the filters.")
            return
        labels = {int(r["id"]): f"{r['severity'].upper():8} · {r['title']}" for _, r in view.iterrows()}
        selected = st.radio("Finding", options, format_func=lambda i: labels[int(i)], label_visibility="collapsed", key="finding_radio")
        st.write("")
        st.download_button("Export findings (CSV)", df_to_csv(view[["finding_key", "severity", "classification", "status", "category", "title", "summary", "estimated_impact", "confidence", "evidence_count"]]),
                           file_name=f"{brand['slug']}-findings-run{run['id']}.csv", mime="text/csv")
    with right:
        _detail(int(selected), cur)

    c.divider()
    _compare(bid)


def _detail(finding_id: int, cur: str) -> None:
    conn = state.conn()
    f = repo.get_finding(conn, finding_id)
    m = json.loads(f["measured"]) if f["measured"] else {}
    st.markdown(f'<div>{c.severity_pill(f["severity"])}{c.class_pill(f["classification"])}{c.status_pill(f["status"])}</div>', unsafe_allow_html=True)
    st.markdown(f"<h2 style='margin-top:6px'>{html.escape(f['title'])}</h2>", unsafe_allow_html=True)
    c.note(f"{f['finding_key']} · rule v{f['rule_version']} · {f['category']} · period {f['period_start']} to {f['period_end']} · confidence {f['confidence']}")
    st.write("")
    k1, k2 = st.columns(2)
    with k1:
        c.kpi("Estimated impact", c.money(f["estimated_impact"], cur) if f["estimated_impact"] is not None else "Not quantified", None)
    with k2:
        c.kpi("Classification", theme.CLASS_LABELS[f["classification"]], {"discrepancy": "Two records disagree", "suspected_risk": "Pattern needs verification", "observation": "Informational; not a risk"}[f["classification"]])

    t1, t2, t3, t4 = st.tabs(["Why it was flagged", "Evidence", "Impact & next step", "Seller questions"])
    with t1:
        st.write(f["explanation"])
        st.markdown(f"**How the calculation works.** {f['method']}")
        if f["confidence_note"]:
            c.caption("Confidence: " + f["confidence_note"])
        with st.expander("Measured values"):
            st.json(m, expanded=False)
    with t2:
        ev = repo.evidence_for_finding(conn, finding_id)
        c.caption(f"{len(ev)} source rows. Each row names the table and record the rule used.")
        show = ev[["source_table", "source_id", "source_ref", "description", "value"]].rename(columns={"source_table": "Table", "source_id": "Record", "source_ref": "Reference", "description": "Description", "value": "Value"})
        c.table(show, height=min(420, 38 * len(show) + 40))
        st.download_button("Export evidence (CSV)", df_to_csv(ev.drop(columns=["extra"])), file_name=f"evidence-{f['finding_key'].replace(':', '-')}.csv", mime="text/csv", key=f"ev_{finding_id}")
        _source_rows(conn, ev)
    with t3:
        if f["impact_basis"]:
            st.markdown(f"**Impact assumptions.** {f['impact_basis']}")
        else:
            st.markdown("**Impact.** Not quantified from the available records; no estimate is invented.")
        if f["next_action"]:
            st.markdown(f"**Recommended next step.** {f['next_action']}")
        st.write("")
        st.markdown('<div class="tell-eyebrow">Update status</div>', unsafe_allow_html=True)
        new_status = st.selectbox("Status", list(theme.STATUS_LABELS), index=list(theme.STATUS_LABELS).index(f["status"]), format_func=lambda k: theme.STATUS_LABELS[k], label_visibility="collapsed", key=f"st_{finding_id}")
        note = st.text_area("Analyst note", value=f["analyst_note"] or "", placeholder="What was checked, with whom, and the outcome.", key=f"nt_{finding_id}", height=80)
        if st.button("Save", type="primary", key=f"sv_{finding_id}"):
            update_finding_status(conn, finding_id, new_status, note or None)
            st.success("Saved.")
            st.rerun()
    with t4:
        qs = repo.questions_for_finding(conn, finding_id)
        for _, q in qs.iterrows():
            st.markdown(f"**{q['question']}**")
            c.caption(f"Why: {q['rationale']}  \nRequest: {q['requested_items']}  \nPriority {q['priority']} · {q['status']}")
            st.write("")


def _source_rows(conn, ev: pd.DataFrame) -> None:
    """Show the actual underlying rows for evidence that points to concrete record IDs."""
    with_ids = ev[ev["source_id"].notna()]
    if with_ids.empty:
        return
    table = with_ids["source_table"].iloc[0]
    ids = [int(i) for i in with_ids["source_id"].head(200)]
    marks = ",".join("?" for _ in ids)
    sql = {
        "refunds": f"SELECT r.refund_ref, r.refund_date, r.amount, r.reason, o.order_ref, o.order_date FROM refunds r JOIN orders o ON o.id = r.order_id WHERE r.id IN ({marks})",
        "inventory_snapshots": f"SELECT s.snapshot_date, p.sku, s.quantity_on_hand, s.source FROM inventory_snapshots s JOIN products p ON p.id = s.product_id WHERE s.id IN ({marks})",
        "supplier_receipts": f"SELECT r.receipt_ref, p.sku, r.received_date, r.quantity, r.unit_cost, r.supplier FROM supplier_receipts r JOIN products p ON p.id = r.product_id WHERE r.id IN ({marks})",
        "products": f"SELECT sku, name, category, list_price, standard_cost FROM products WHERE id IN ({marks})",
    }.get(table)
    if sql:
        with st.expander(f"Source rows from `{table}`"):
            c.table(repo.fetch_df(conn, sql, ids), height=min(360, 38 * len(ids) + 40))


def _compare(bid: int) -> None:
    conn = state.conn()
    runs = [r for r in repo.list_runs(conn, bid) if r["status"] == "completed"]
    st.markdown("<h3>Compare runs</h3>", unsafe_allow_html=True)
    if len(runs) < 2:
        c.caption("Run the analysis again after importing new data to compare which findings are new, resolved or changed.")
        return
    label = {r["id"]: f"Run {r['id']} · {str(r['finished_at'])[:16].replace('T', ' ')} · {r['finding_count']} findings · data {r['data_hash']}" for r in runs}
    a, b = st.columns(2)
    with a:
        base = st.selectbox("Baseline", [r["id"] for r in runs], index=min(1, len(runs) - 1), format_func=lambda i: label[i])
    with b:
        new = st.selectbox("Comparison", [r["id"] for r in runs], index=0, format_func=lambda i: label[i])
    if base == new:
        c.caption("Select two different runs.")
        return
    cmp = compare_runs(conn, int(base), int(new))
    c.kpi_row([("New findings", str(len(cmp["new"])), None), ("Resolved", str(len(cmp["resolved"])), "present in baseline only"),
               ("Changed", str(len(cmp["changed"])), "severity or impact differs"), ("Unchanged", str(cmp["unchanged_count"]), None)])
    c.caption(("Same underlying data" if cmp["same_data"] else "Underlying data differs between runs") + " · " + ("same rule versions" if cmp["same_rules"] else "rule versions differ")
              + ". 'Resolved' means the rule no longer fires on the new data; it does not by itself confirm the issue was fixed.")
    for title, items in (("New", cmp["new"]), ("Resolved", cmp["resolved"])):
        if items:
            st.markdown(f"**{title}**")
            for it in items:
                st.markdown(f"- {c.severity_pill(it['severity'])} {html.escape(it['title'])}", unsafe_allow_html=True)
    if cmp["changed"]:
        st.markdown("**Changed**")
        c.table(pd.DataFrame(cmp["changed"]))
