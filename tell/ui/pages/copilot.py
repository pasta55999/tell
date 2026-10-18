from __future__ import annotations

import streamlit as st

from tell.copilot import ask, supported_questions
from tell.ui import components as c, state


def render() -> None:
    brand = state.brand()
    run = state.run()
    c.page_header("Analyst copilot", "Questions are matched to a fixed set of analytical intents and answered with calculations from the database and the selected run. No language model is involved; unsupported questions are declined rather than guessed.", eyebrow=brand["name"])
    c.insight("Rule-based Analyst Copilot · every answer cites the finding keys and tables it was computed from.", "cobalt")
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []
    with st.expander("Supported questions", expanded=not st.session_state.copilot_history):
        cols = st.columns(2)
        for i, q in enumerate(supported_questions()):
            with cols[i % 2]:
                if st.button(q, key=f"sq_{i}", width="stretch"):
                    st.session_state.copilot_pending = q
    question = st.chat_input("Ask about revenue, refunds, margins, findings, evidence or seller questions")
    if st.session_state.get("copilot_pending"):
        question = st.session_state.pop("copilot_pending")
    if question:
        answer = ask(state.conn(), int(brand["id"]), question, int(run["id"]) if run else None)
        st.session_state.copilot_history.append((question, answer))
    for q, a in st.session_state.copilot_history[-8:]:
        with st.chat_message("user", avatar=":material/person:"):
            st.write(q)
        with st.chat_message("assistant", avatar=":material/insights:"):
            st.text(a.text)
            if a.table is not None and not a.table.empty:
                with st.expander("Data behind this answer"):
                    c.table(a.table)
            meta = f"{a.engine} · intent: {a.intent}"
            if a.related_findings:
                meta += " · related findings: " + ", ".join(a.related_findings[:6])
            c.note(meta)
