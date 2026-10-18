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
    c.page_header("Findings", "Every finding is produced by a versioned rule against the records and links to the rows that triggered it.", eyebrow=brand["name"])
    if run is None:
        if c.empty_state("No analysis run yet", "Run the analysis to reconcile the records and surface findings.", "Run analysis", key="fd_run"):
            with st.spinner("Analysing records..."):
                st.session_state.run_id = run_analysis(state.conn(), bid)
            st.rerun()
        return
    f = data.findings(int(run["id"]))
    if f.empty:
        c.panel("No findings", "The analysis completed without raising any findings on this data.", "emerald")
        return

    sev = f["severity"].value_counts()
    hi = int(sev.get("critical", 0) + sev.get("high", 0))
    open_n = int((~f["status"].isin(["verified", "dismissed"])).sum())
    disc_total = f[f["classification"] == "discrepancy"]["estimated_impact"].fillna(0).sum()
    c.kpi_row([("Findings", str(len(f)), c.delta_text(f"run {run['id']} · {int((f['classification'] == 'observation').sum())} observations", "neutral"), theme.COBALT),
               ("High or critical", str(hi), c.delta_text("need verification first", "risk" if hi else "neutral"), theme.CORAL if hi else theme.EMERALD),
               ("Quantified discrepancies", c.money(disc_total, cur), c.delta_text("sum of discrepancy impacts only", "neutral"), theme.VIOLET),
               ("Open", str(open_n), c.delta_text(f"{len(f) - open_n} verified or dismissed", "neutral"), theme.AMBER if open_n else theme.EMERALD)])
    st.write("")

    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        sev_filter = st.multiselect("Severity", ["critical", "high", "medium", "low", "info"], default=[], placeholder="All severities", label_visibility="collapsed")
    with col2:
        cls_filter = st.multiselect("Type", list(theme.CLASS_LABELS), default=[], format_func=lambda k: theme.CLASS_LABELS[k], placeholder="All types", label_visibility="collapsed")
    with col3:
        cat_filter = st.multiselect("Category", sorted(f["category"].unique()), default=[], placeholder="All categories", label_visibility="collapsed")
    with col4:
        hide_closed = st.toggle("Hide verified & dismissed", value=False)
    view = f.copy()
    if sev_filter:
        view = view[view["severity"].isin(sev_filter)]
    if cls_filter:
        view = view[view["classification"].isin(cls_filter)]
    if cat_filter:
        view = view[view["category"].isin(cat_filter)]
    if hide_closed:
        view = view[~view["status"].isin(["verified", "dismissed"])]
    active = [x for x in [", ".join(sev_filter), ", ".join(theme.CLASS_LABELS[k] for k in cls_filter), ", ".join(cat_filter), "open only" if hide_closed else ""] if x]
    c.note(f"Showing {len(view)} of {len(f)} findings" + (f" · filters: {' · '.join(active)}" if active else ""))

    left, right = st.columns([2, 3], gap="large")
    with left:
        options = view["id"].tolist()
        if not options:
            c.panel("No findings match", "Clear one or more filters to see findings.", "tint")
            return
        pre = st.session_state.pop("selected_finding", None)
        if pre in options:
            st.session_state.finding_radio = pre
        labels = {int(r["id"]): f"{r['severity'].upper()} · {r['title']}" for _, r in view.iterrows()}
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
    accent = theme.SEVERITY_BAR.get(f["severity"], theme.LINE_STRONG)
    st.markdown(f'<div style="border-left:4px solid {accent};padding-left:14px">'
                f'<div>{c.severity_pill(f["severity"])}{c.class_pill(f["classification"])}{c.status_pill(f["status"])}</div>'
                f'<h2 style="margin:8px 0 4px 0 !important">{html.escape(f["title"])}</h2>'
                f'<div class="tell-note">{f["finding_key"]} · rule v{f["rule_version"]} · {html.escape(f["category"])} · {f["period_start"]} to {f["period_end"]}</div></div>', unsafe_allow_html=True)
    st.write("")
    k1, k2, k3 = st.columns(3)
    with k1:
        c.kpi("Estimated impact", c.money(f["estimated_impact"], cur) if f["estimated_impact"] is not None else "Not quantified", None, accent, plain=True)
    with k2:
        c.kpi("Classification", theme.CLASS_LABELS[f["classification"]], c.esc({"discrepancy": "Two records disagree", "suspected_risk": "Pattern needs verification", "observation": "Informational, not a risk"}[f["classification"]]), None, plain=True)
    with k3:
        c.kpi("Confidence", f["confidence"].capitalize(), None, None, plain=True)

    t1, t2, t3, t4, t5 = st.tabs(["Observed", "Detection method", "Evidence", "Confidence & follow-up", "Seller questions"])
    with t1:
        c.insight(f["summary"], "coral" if f["severity"] in ("critical", "high") else "cobalt" if f["classification"] != "observation" else "emerald")
        st.write("")
        st.markdown("**Why it matters**")
        st.write(f["explanation"])
        if f["impact_basis"]:
            st.markdown(f"**Impact basis.** {f['impact_basis']}")
    with t2:
        st.write(f["method"])
        with st.expander("Measured values used by the rule"):
            st.json(m, expanded=False)
    with t3:
        ev = repo.evidence_for_finding(conn, finding_id)
        c.caption(f"{len(ev)} source rows. Each row names the table and record the rule used, so any number can be traced back.")
        show = ev[["source_table", "source_id", "source_ref", "description", "value"]].rename(columns={"source_table": "Table", "source_id": "Record", "source_ref": "Reference", "description": "Description", "value": "Value"})
        c.table(show, height=min(420, 38 * len(show) + 40))
        st.download_button("Export evidence (CSV)", df_to_csv(ev.drop(columns=["extra"])), file_name=f"evidence-{f['finding_key'].replace(':', '-')}.csv", mime="text/csv", key=f"ev_{finding_id}")
        _source_rows(conn, ev)
    with t4:
        st.markdown(f"**Confidence: {f['confidence']}.** {f['confidence_note'] or ''}")
        if f["next_action"]:
            st.markdown(f"**Recommended follow-up.** {f['next_action']}")
        st.write("")
        st.markdown('<div class="tell-eyebrow muted">Update status</div>', unsafe_allow_html=True)
        new_status = st.selectbox("Status", list(theme.STATUS_LABELS), index=list(theme.STATUS_LABELS).index(f["status"]), format_func=lambda k: theme.STATUS_LABELS[k], label_visibility="collapsed", key=f"st_{finding_id}")
        note = st.text_area("Analyst note", value=f["analyst_note"] or "", placeholder="What was checked, with whom, and the outcome.", key=f"nt_{finding_id}", height=80)
        if st.button("Save", type="primary", key=f"sv_{finding_id}"):
            update_finding_status(conn, finding_id, new_status, note or None)
            st.success("Status saved.")
            st.rerun()
    with t5:
        qs = repo.questions_for_finding(conn, finding_id)
        for _, q in qs.iterrows():
            st.markdown(f"{c.priority_pill(q['priority'])} **{html.escape(q['question'])}**", unsafe_allow_html=True)
            c.caption(f"Why: {q['rationale']}")
            c.caption(f"Request: {q['requested_items']} · status {q['status']}")
            st.write("")


def _source_rows(conn, ev: pd.DataFrame) -> None:
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
    c.section("Compare runs", "Which findings are new, resolved or changed between two stored runs")
    if len(runs) < 2:
        c.caption("Run the analysis again after importing new data to compare runs.")
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
    c.kpi_row([("New findings", str(len(cmp["new"])), None, theme.CORAL if cmp["new"] else None), ("Resolved", str(len(cmp["resolved"])), c.delta_text("present in baseline only", "neutral"), theme.EMERALD if cmp["resolved"] else None),
               ("Changed", str(len(cmp["changed"])), c.delta_text("severity or impact differs", "neutral"), theme.AMBER if cmp["changed"] else None), ("Unchanged", str(cmp["unchanged_count"]), None, None)], plain=True)
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
