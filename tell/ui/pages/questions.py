from __future__ import annotations

import streamlit as st

from tell.analysis.engine import update_question_status
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import components as c, state, theme

PRIORITY_ORDER = ["high", "medium", "low"]


def render() -> None:
    brand = state.brand()
    run = state.run()
    c.page_header("Seller questions", "Prioritised diligence questions assembled from the findings in the selected run, with the evidence that prompted each one and the documents to request.", eyebrow=brand["name"])
    if run is None:
        c.empty_state("No analysis run yet", "Run the analysis from the overview; questions are generated from real findings.")
        return
    conn = state.conn()
    q = repo.questions_for_run(conn, int(run["id"]))
    if q.empty:
        c.panel("No questions", "The run produced no findings, so there is nothing to ask the seller yet.", "emerald")
        return
    counts = q["status"].value_counts()
    c.kpi_row([("Questions", str(len(q)), c.delta_text(f"{int((q['priority'] == 'high').sum())} high priority", "risk" if (q["priority"] == "high").any() else "neutral"), theme.COBALT),
               ("Pending", str(int(counts.get("pending", 0))), None, theme.AMBER),
               ("Answered", str(int(counts.get("answered", 0))), None, theme.VIOLET),
               ("Resolved", str(int(counts.get("resolved", 0))), None, theme.EMERALD)])
    st.write("")
    a, b, d = st.columns([3, 2, 2])
    with a:
        status_filter = st.multiselect("Status", ["pending", "answered", "resolved"], default=["pending", "answered"], label_visibility="collapsed")
    with b:
        group_by = st.selectbox("Group by", ["Priority", "Topic"], label_visibility="collapsed")
    with d:
        st.download_button("Export question list (CSV)", df_to_csv(q[["priority", "question", "rationale", "requested_items", "status", "finding_key"]]),
                           file_name=f"{brand['slug']}-seller-questions.csv", mime="text/csv", width="stretch")
    view = q[q["status"].isin(status_filter)] if status_filter else q
    view = view.assign(topic=view["finding_key"].fillna("GEN").str.split("-").str[0].map(
        {"REV": "Revenue", "REF": "Refunds & returns", "ADV": "Advertising", "MAR": "Profitability", "CON": "Concentration", "DSC": "Pricing", "INV": "Inventory", "SEA": "Seasonality", "DQ": "Data quality", "GEN": "Consolidated"}).fillna("Other"))
    if view.empty:
        c.panel("Nothing to show", "Adjust the status filter.", "tint")
        return
    groups = [(p, view[view["priority"] == p]) for p in PRIORITY_ORDER] if group_by == "Priority" else [(t, g) for t, g in view.groupby("topic")]
    for name, grp in groups:
        if grp.empty:
            continue
        c.section(f"{name.capitalize() if group_by == 'Priority' else name}", f"{len(grp)} question(s)")
        for _, row in grp.iterrows():
            accent = theme.PRIORITY_COLORS[row["priority"]][0]
            origin = c.esc(row["finding_key"]) if row["finding_key"] else "consolidated from several findings"
            st.markdown(f'<div class="tell-row" style="--row-accent:{accent}"><div>{c.priority_pill(row["priority"])}{c.pill(row["status"], *theme.STATUS_COLORS.get({"pending": "detected", "answered": "needs_investigation", "resolved": "verified"}[row["status"]]))}'
                        f'<span class="tell-note">{origin}</span></div><div class="title">{c.esc(row["question"])}</div></div>', unsafe_allow_html=True)
            with st.expander("Why it matters, evidence and requested documents"):
                st.markdown(f"**Why it matters.** {row['rationale']}")
                if row["evidence_note"]:
                    st.markdown(f"**Evidence that prompted it.** {row['evidence_note']}")
                st.markdown(f"**Request from the seller.** {row['requested_items']}")
                x, y, z = st.columns([2, 4, 1])
                with x:
                    new_status = st.selectbox("Status", ["pending", "answered", "resolved"], index=["pending", "answered", "resolved"].index(row["status"]), key=f"qs_{row['id']}", label_visibility="collapsed")
                with y:
                    note = st.text_input("Response note", value=row["answer_note"] or "", placeholder="Summary of the seller's answer", key=f"qn_{row['id']}", label_visibility="collapsed")
                with z:
                    if st.button("Save", key=f"qb_{row['id']}", width="stretch"):
                        update_question_status(conn, int(row["id"]), new_status, note or None)
                        st.rerun()
