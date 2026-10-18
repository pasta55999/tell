"""Seller questions as a diligence workflow: grouped by theme, each tied to the finding and
figures that triggered it, with open / answered / resolved tracking."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from tell.analysis.engine import update_question_status
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import components as c, state, theme

THEMES = {"REV": "Revenue", "MAR": "Profitability", "DSC": "Pricing & promotions", "REF": "Refunds & returns", "ADV": "Advertising", "CON": "Concentration",
          "INV": "Inventory & suppliers", "SEA": "Seasonality", "DQ": "Data quality", "GEN": "Cross-cutting requests"}
STATUS_LABEL = {"pending": "Open", "answered": "Answered", "resolved": "Resolved"}
STATUS_TONE = {"pending": "detected", "answered": "needs_investigation", "resolved": "verified"}


def render() -> None:
    brand = state.brand()
    run = state.run()
    cur = brand["reporting_currency"]
    conn = state.conn()
    c.page_header("Seller questions", eyebrow=brand["name"])
    if run is None:
        c.empty_state("No analysis run yet", "Run the analysis from the overview; questions are generated from real findings, never from a generic list.")
        return
    q = repo.questions_for_run(conn, int(run["id"]))
    if q.empty:
        c.panel("No questions", "The run produced no findings, so there is nothing to ask the seller yet.", "emerald")
        return
    counts = q["status"].value_counts()
    c.hero([("Open", str(int(counts.get("pending", 0))), f"of {len(q)} · {int((q['priority'] == 'high').sum())} high priority", theme.AMBER if counts.get("pending") else theme.EMERALD),
            ("Answered", str(int(counts.get("answered", 0))), "awaiting review", theme.VIOLET),
            ("Resolved", str(int(counts.get("resolved", 0))), "closed with evidence", theme.EMERALD)], small=True)

    f1, f2, f3 = st.columns([3, 2, 2])
    with f1:
        status_filter = st.segmented_control("Status", ["Open", "Answered", "Resolved", "All"], default="Open", label_visibility="collapsed")
    with f2:
        group_by = st.selectbox("Group by", ["Theme", "Priority"], label_visibility="collapsed")
    with f3:
        st.download_button("Export (CSV)", df_to_csv(q[["priority", "question", "rationale", "requested_items", "status", "finding_key"]]), file_name=f"{brand['slug']}-seller-questions.csv", mime="text/csv", width="stretch")
    status_map = {"Open": ["pending"], "Answered": ["answered"], "Resolved": ["resolved"], "All": ["pending", "answered", "resolved"]}
    view = q[q["status"].isin(status_map[status_filter])].copy()
    view["theme"] = view["finding_key"].fillna("GEN").str.split("-").str[0].map(THEMES).fillna("Other")
    focus = st.session_state.pop("question_focus", None)
    if view.empty:
        c.panel("Nothing in this state", "Switch the status filter to see other questions.", "tint")
        return
    findings = repo.findings_for_run(conn, int(run["id"])).set_index("finding_key") if not q["finding_key"].dropna().empty else pd.DataFrame()

    theme_order = list(THEMES.values()) + ["Other"]
    groups = [(t, view[view["theme"] == t]) for t in theme_order if (view["theme"] == t).any()] if group_by == "Theme" else [(p.capitalize(), view[view["priority"] == p]) for p in ["high", "medium", "low"]]
    for name, grp in groups:
        if grp.empty:
            continue
        c.section(name, f"{len(grp)} question(s) · {int((grp['priority'] == 'high').sum())} high")
        for _, row in grp.iterrows():
            accent = theme.PRIORITY_COLORS[row["priority"]][0]
            fk = row["finding_key"]
            origin = f"from {fk}" if fk else "consolidated from several findings"
            is_focus = focus is not None and fk == focus
            st.markdown(f'<div class="tell-row{" flat" if False else ""}" style="--row-accent:{accent}{";border-color:" + theme.COBALT if is_focus else ""}">'
                        f'<div>{c.priority_pill(row["priority"])}{c.pill(STATUS_LABEL[row["status"]], *theme.STATUS_COLORS[STATUS_TONE[row["status"]]])}<span class="tell-note">{c.esc(origin)}</span></div>'
                        f'<div class="title">{c.esc(row["question"])}</div></div>', unsafe_allow_html=True)
            with st.expander("Why we ask, the figures behind it, and what to request", expanded=is_focus):
                a, b = st.columns([3, 2], gap="large")
                with a:
                    st.markdown(f"**Why it matters.** {row['rationale']}")
                    st.markdown(f"**Request from the seller.** {row['requested_items']}")
                    if row["answer_note"]:
                        c.insight("Seller's response: " + row["answer_note"], "cobalt")
                with b:
                    if fk and not findings.empty and fk in findings.index:
                        fr = findings.loc[fk]
                        m = json.loads(fr["measured"]) if fr["measured"] else {}
                        st.markdown('<div class="tell-eyebrow muted">Figures that prompted it</div>', unsafe_allow_html=True)
                        c.ledger(_figures(fr["rule_id"], m, cur), ("Estimated impact", c.money(fr["estimated_impact"], cur) if fr["estimated_impact"] is not None else "not quantified"))
                        if st.button("Open the finding", key=f"qf_{row['id']}", icon=":material/troubleshoot:"):
                            st.session_state.selected_finding = int(fr["id"])
                            state.go("findings")
                    elif row["evidence_note"]:
                        c.caption("Evidence: " + row["evidence_note"])
                st.markdown('<div class="tell-eyebrow muted" style="margin-top:8px">Record the outcome</div>', unsafe_allow_html=True)
                x, y, z = st.columns([2, 4, 1])
                with x:
                    new_status = st.selectbox("Status", ["pending", "answered", "resolved"], index=["pending", "answered", "resolved"].index(row["status"]), format_func=lambda k: STATUS_LABEL[k], key=f"qs_{row['id']}", label_visibility="collapsed")
                with y:
                    note = st.text_input("Response note", value="", placeholder="Summary of the seller's answer or the document received", key=f"qn_{row['id']}", label_visibility="collapsed")
                with z:
                    if st.button("Save", key=f"qb_{row['id']}", width="stretch"):
                        update_question_status(conn, int(row["id"]), new_status, note or None)
                        st.toast("Question updated.")
                        st.rerun()


def _figures(rule_id: str, m: dict, cur: str) -> list[tuple]:
    money = lambda v: f"{cur} {float(v):,.0f}"  # noqa: E731
    if rule_id == "REV-001":
        return [("Seller-reported", money(m["reported_revenue"]), None), ("Supported net sales", money(m["net_sales"]), None), ("Variance", f"{m['variance_pct']:+.1f}%", None, True)]
    if rule_id == "ADV-002":
        return [("Statement", money(m["reported_ad_spend"]), None), ("Platform records", money(m["recorded_ad_spend"]), None), ("Variance", f"{m['variance_pct']:+.0f}%", None, True)]
    if rule_id == "REF-001":
        return [("Return rate", f"{m['return_rate_pct']:.1f}%", None, True), ("Portfolio", f"{m['portfolio_return_rate_pct']:.1f}%", None), ("Units refunded", f"{m['refunded_units']} / {m['units_sold']}", None)]
    if rule_id == "REF-002":
        return [("Late refunds", str(m["late_refund_count"]), f"{m['lag_days_min']}–{m['lag_days_max']} days"), ("Value", money(m["late_refund_value"]), None, True)]
    if rule_id == "REF-003":
        return [("Cohort refund rate", f"{m['cohort_refund_rate_pct']:.1f}%", None, True), ("Normal", f"{m['median_other_months_pct']:.1f}%", None)]
    if rule_id == "MAR-001":
        return [("Margin before", f"{m['first_window']['gross_margin_pct']:.1f}%", None), ("Margin after", f"{m['last_window']['gross_margin_pct']:.1f}%", None, True), ("Unit cost", f"{m['avg_unit_cost_change_pct']:+.1f}%", None)]
    if rule_id == "DSC-001":
        return [("Discount rate", f"{m['discount_rate_pct']:.1f}%", None, True), ("Normal", f"{m['median_other_months_pct']:.1f}%", None)]
    if rule_id == "CON-001":
        return [(m["top_sku"], f"{m['top_share_pct']:.1f}%", "of gross sales", True), ("Top 3", f"{m['top3_share_pct']:.1f}%", None)]
    if rule_id == "INV-001":
        return [("Cumulative variance", f"{m['cumulative_variance_units']:+d} units", f"{m['months_flagged']} month(s)", True)]
    if rule_id == "INV-003":
        mm = m["mismatches"][0]
        return [("Invoice cost", f"{cur} {mm['supplier_unit_cost']:,.2f}", mm["period"]), ("Recorded cost", f"{cur} {mm['recorded_unit_cost']:,.2f}", None, True)]
    if rule_id == "SEA-001":
        return [("Sales vs baseline", f"{m['sales_growth_pct']:+.0f}%", None), ("Orders vs baseline", f"{m['orders_growth_pct']:+.0f}%", None)]
    return [(k.replace("_", " "), str(v), None) for k, v in list(m.items())[:4] if not isinstance(v, (dict, list))]
