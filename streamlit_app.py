"""Tell - acquisition diligence intelligence. Entry point: `streamlit run streamlit_app.py`."""

from __future__ import annotations

import streamlit as st

from tell import config
from tell.db import repository as repo
from tell.ui import state, theme
from tell.ui.pages import advertising, copilot, financials, findings, inventory, overview, products, questions, reconciliation, reports, settings

st.set_page_config(page_title="Tell", page_icon=":material/insights:", layout="wide", initial_sidebar_state="expanded")
theme.inject_css()
state.ensure_state()

# (url slug, title, icon, renderer, group)
PAGES = [
    ("", "Acquisition overview", ":material/dashboard:", overview.render, "Workspace"),
    ("financials", "Financials", ":material/table_chart:", financials.render, "Analysis"),
    ("reconciliation", "Revenue reconciliation", ":material/balance:", reconciliation.render, "Analysis"),
    ("products", "Products & margins", ":material/inventory_2:", products.render, "Analysis"),
    ("advertising", "Advertising", ":material/campaign:", advertising.render, "Analysis"),
    ("inventory", "Inventory", ":material/warehouse:", inventory.render, "Analysis"),
    ("findings", "Findings", ":material/troubleshoot:", findings.render, "Diligence"),
    ("questions", "Seller questions", ":material/help_outline:", questions.render, "Diligence"),
    ("reports", "Reports", ":material/description:", reports.render, "Diligence"),
    ("copilot", "Analyst copilot", ":material/forum:", copilot.render, "Diligence"),
    ("settings", "Settings & imports", ":material/settings:", settings.render, "System"),
]

pages = [st.Page(fn, title=title, icon=icon, url_path=slug or None, default=(slug == "")) for slug, title, icon, fn, _ in PAGES]
nav = st.navigation(pages, position="hidden")
st.session_state.pages = {(slug or "overview"): page for (slug, _, _, _, _), page in zip(PAGES, pages)}

with st.sidebar:
    st.markdown(f'<div class="tell-wordmark">{theme.SIGNAL_ICON}<span class="name">{config.APP_NAME}</span></div>'
                f'<div class="tell-tagline">{config.TAGLINE}</div>', unsafe_allow_html=True)
    conn = state.conn()
    brands = repo.list_brands(conn)
    if brands:
        st.markdown('<div class="tell-side-label">Target business</div>', unsafe_allow_html=True)
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
    for (slug, title, icon, fn, group), page in zip(PAGES, pages):
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

nav.run()
