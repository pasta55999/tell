from __future__ import annotations

import html

import streamlit as st

from tell.analysis.engine import update_question_status
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import components as c, state, theme

PRIORITY_COLORS = {"high": (theme.RUST, theme.RUST_SOFT), "medium": (theme.AMBER, theme.AMBER_SOFT), "low": (theme.SLATE, theme.SLATE_SOFT)}


def render() -> None:
    brand = state.brand()
    run = state.run()
    c.page_header("Seller questions", "Prioritised diligence questions assembled from the findings in the selected run.", eyebrow=brand["name"])
    if run is None:
        c.empty_state("No analysis run yet", "Run the analysis from the Overview or Findings page; questions are generated from real findings.")
        return
    conn = state.conn()
    q = repo.questions_for_run(conn, int(run["id"]))
    if q.empty:
        c.empty_state("No questions", "The run produced no findings, so there is nothing to ask the seller yet.")
        return
    counts = q["status"].value_counts()
    c.kpi_row([("Questions", str(len(q)), f"{int((q['priority'] == 'high').sum())} high priority"),
               ("Pending", str(int(counts.get("pending", 0))), None), ("Answered", str(int(counts.get("answered", 0))), None), ("Resolved", str(int(counts.get("resolved", 0))), None)])
    st.write("")
    a, b = st.columns([3, 2])
    with a:
        status_filter = st.multiselect("Status", ["pending", "answered", "resolved"], default=["pending", "answered"], label_visibility="collapsed")
    with b:
        st.download_button("Export question list (CSV)", df_to_csv(q[["priority", "question", "rationale", "requested_items", "status", "finding_key"]]),
                           file_name=f"{brand['slug']}-seller-questions.csv", mime="text/csv")
    view = q[q["status"].isin(status_filter)] if status_filter else q
    for _, row in view.iterrows():
        fg, bg = PRIORITY_COLORS[row["priority"]]
        origin = html.escape(str(row["finding_key"])) if row["finding_key"] else "consolidated"
        with st.container():
            st.markdown(f'<div class="tell-row"><div>{c.pill(row["priority"], fg, bg)}{c.pill(row["status"], theme.INK_SOFT, "#fff; border:1px solid " + theme.LINE)}'
                        f'<span class="tell-note">{origin}</span></div>'
                        f'<div class="title" style="margin-top:6px">{html.escape(row["question"])}</div></div>', unsafe_allow_html=True)
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
                    if st.button("Save", key=f"qb_{row['id']}"):
                        update_question_status(conn, int(row["id"]), new_status, note or None)
                        st.rerun()
