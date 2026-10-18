"""Tell - acquisition diligence intelligence. Entry point: `streamlit run streamlit_app.py`."""

from __future__ import annotations

import streamlit as st

from tell import config
from tell.db import repository as repo
from tell.ui import components as c, state, theme
from tell.ui.pages import copilot, data_room, deals, financial_story, findings, operations, overview, questions, reports

st.set_page_config(page_title="Tell", page_icon=":material/insights:", layout="wide", initial_sidebar_state="expanded")
theme.inject_css()
state.ensure_state()

# (key / url slug, title, icon, renderer, group)
PAGES = [
    ("deals", "Deals", ":material/work:", deals.render, "Pipeline"),
    ("overview", "Overview", ":material/dashboard:", overview.render, "Active deal"),
    ("financial_story", "Financial story", ":material/account_balance:", financial_story.render, "Active deal"),
    ("operations", "Operations", ":material/inventory_2:", operations.render, "Active deal"),
    ("findings", "Findings", ":material/troubleshoot:", findings.render, "Investigation"),
    ("questions", "Seller questions", ":material/help_outline:", questions.render, "Investigation"),
    ("reports", "Reports", ":material/description:", reports.render, "Investigation"),
    ("copilot", "Ask the records", ":material/forum:", copilot.render, "Investigation"),
    ("data_room", "Data room", ":material/folder_open:", data_room.render, "Sources"),
]

pages = [st.Page(fn, title=title, icon=icon, url_path=None if key == "overview" else key, default=(key == "overview")) for key, title, icon, fn, _ in PAGES]
nav = st.navigation(pages, position="hidden")
st.session_state.pages = {key: page for (key, _, _, _, _), page in zip(PAGES, pages)}

with st.sidebar:
    st.markdown(f'<div class="tell-wordmark">{theme.SIGNAL_ICON}<span class="name">{config.APP_NAME}</span></div>'
                f'<div class="tell-tagline">{config.TAGLINE}</div>', unsafe_allow_html=True)
    conn = state.conn()
    brands = repo.list_brands(conn)
    if brands:
        st.markdown('<div class="tell-side-label">Active deal</div>', unsafe_allow_html=True)
        ids = [b["id"] for b in brands]
        names = {b["id"]: b["name"] + (" · demo" if b["is_demo"] else "") for b in brands}
        chosen = st.selectbox("Brand", ids, index=ids.index(st.session_state.brand_id), format_func=lambda i: names[i], label_visibility="collapsed")
        if chosen != st.session_state.brand_id:
            st.session_state.brand_id = chosen
            st.session_state.run_id = None
            state.ensure_state()
            st.rerun()
        runs = [r for r in repo.list_runs(conn, st.session_state.brand_id) if r["status"] == "completed"]
        if runs:
            rid = [r["id"] for r in runs]
            labels = {r["id"]: f"Run {r['id']} · {str(r['finished_at'])[5:16].replace('T', ' ')}" + (f" · {r['label']}" if r["label"] else "") for r in runs}
            sel = st.selectbox("Analysis run", rid, index=rid.index(st.session_state.run_id) if st.session_state.run_id in rid else 0, format_func=lambda i: labels[i], label_visibility="collapsed")
            if sel != st.session_state.run_id:
                st.session_state.run_id = sel
                st.rerun()
        else:
            st.markdown('<div class="tell-note">No analysis run yet</div>', unsafe_allow_html=True)
    current_group = None
    for (key, title, icon, fn, group), page in zip(PAGES, pages):
        if group != current_group:
            st.markdown(f'<div class="tell-side-label">{group}</div>', unsafe_allow_html=True)
            current_group = group
        if page.title == nav.title:
            st.markdown(f'<div class="tell-nav-active" aria-current="page"><span class="material-symbols-rounded">{icon.strip(":").split("/")[1]}</span>{title}</div>', unsafe_allow_html=True)
        else:
            st.page_link(page, label=title, icon=icon)
    st.markdown('<div class="tell-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="tell-side-foot"><div class="avatar">DA</div><div><div class="who">Deal analyst</div><div class="role">Local workspace · offline</div></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="tell-note" style="margin-top:10px">Decision support, not approval. Findings are detected discrepancies or suspected risks until verified.</div>', unsafe_allow_html=True)

brand = state.brand()
run = state.run()
if brand is not None:
    status = (f"<b>{c.esc(brand['name'])}</b> · run {run['id']} · {run['finding_count']} findings · {str(run['finished_at'])[:10]}" if run is not None
              else f"<b>{c.esc(brand['name'])}</b> · no analysis yet")
else:
    status = "No active deal"
c.masthead(status)

nav.run()
