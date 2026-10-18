"""Tell - acquisition diligence intelligence. Entry point: `streamlit run streamlit_app.py`."""

from __future__ import annotations

import streamlit as st

from tell import config
from tell.db import repository as repo
from tell.ui import state, theme
from tell.ui.pages import advertising, copilot, financials, findings, inventory, overview, products, questions, reconciliation, reports, settings

st.set_page_config(page_title="Tell", page_icon=":material/visibility:", layout="wide", initial_sidebar_state="expanded")
theme.inject_css()
state.ensure_state()

PAGES = [
    ("", "Overview", ":material/dashboard:", overview.render),
    ("financials", "Financials", ":material/table_chart:", financials.render),
    ("reconciliation", "Revenue Reconciliation", ":material/balance:", reconciliation.render),
    ("products", "Products & Margins", ":material/inventory_2:", products.render),
    ("advertising", "Advertising", ":material/campaign:", advertising.render),
    ("inventory", "Inventory", ":material/warehouse:", inventory.render),
    ("findings", "Findings", ":material/troubleshoot:", findings.render),
    ("questions", "Seller Questions", ":material/help_outline:", questions.render),
    ("reports", "Reports", ":material/description:", reports.render),
    ("copilot", "Analyst Copilot", ":material/forum:", copilot.render),
    ("settings", "Settings", ":material/settings:", settings.render),
]

pages = [st.Page(fn, title=title, icon=icon, url_path=slug or None, default=(slug == "")) for slug, title, icon, fn in PAGES]
nav = st.navigation(pages, position="hidden")
st.session_state.pages = {(slug or "overview"): page for (slug, _, _, _), page in zip(PAGES, pages)}

with st.sidebar:
    st.markdown(f'<div class="tell-brand">{config.APP_NAME}</div><div class="tell-tagline">{config.TAGLINE}</div>', unsafe_allow_html=True)
    conn = state.conn()
    brands = repo.list_brands(conn)
    if brands:
        ids = [b["id"] for b in brands]
        names = {b["id"]: b["name"] + (" (demo)" if b["is_demo"] else "") for b in brands}
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
    st.markdown('<div class="tell-divider"></div>', unsafe_allow_html=True)
    for page in pages:
        st.page_link(page, label=page.title, icon=page.icon)
    st.markdown('<div class="tell-divider"></div><div class="tell-note">Decision-support tool. Findings are detected discrepancies or suspected risks until verified. Works fully offline; no API keys.</div>', unsafe_allow_html=True)

nav.run()
