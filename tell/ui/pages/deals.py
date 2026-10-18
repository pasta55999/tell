"""Deals: acquisition targets and their diligence status; create a target; edit its profile."""

from __future__ import annotations

import re

import streamlit as st

from tell.db import repository as repo
from tell.ui import components as c, state, theme

CURRENCIES = ["AED", "USD", "EUR", "GBP", "SAR"]


def render() -> None:
    conn = state.conn()
    c.page_header("Deals", eyebrow="Pipeline")
    deals = repo.deal_summaries(conn)
    active = st.session_state.get("brand_id")
    c.hero([("Targets", str(len(deals)), "in this workspace"),
            ("Open findings", str(int(deals["open_findings"].fillna(0).sum())), "across all targets", theme.CORAL if deals["high_findings"].fillna(0).sum() else theme.INK),
            ("Open seller questions", str(int(deals["open_questions"].fillna(0).sum())), "awaiting responses", theme.AMBER)], small=True)
    c.section("Acquisition targets", "Select a deal to make it the active workspace")
    for _, d in deals.iterrows():
        is_active = int(d["id"]) == active
        stage = ("Not started" if not d["orders"] else "Data loaded" if not d["last_run_id"] else "Under investigation" if d["open_findings"] else "Reviewed")
        stage_color = theme.MUTED if stage == "Not started" else theme.COBALT if stage == "Data loaded" else theme.CORAL if stage == "Under investigation" else theme.EMERALD
        a, b = st.columns([5, 1], gap="medium")
        with a:
            st.markdown(f'<div class="tell-row" style="--row-accent:{stage_color}{";border-color:" + theme.COBALT if is_active else ""}">'
                        f'<div>{c.pill(stage, stage_color, theme.SURFACE_ALT)}{c.pill("demo", theme.MUTED, theme.SURFACE_ALT, outline=True) if d["is_demo"] else ""}{c.pill("active", theme.COBALT_DEEP, theme.COBALT_SOFT) if is_active else ""}</div>'
                        f'<div class="title">{c.esc(d["name"])}</div>'
                        f'<div class="meta">{c.esc(d["category"] or "")} · {c.esc(d["location"] or "")} · {d["reporting_currency"]}'
                        + (f' · {d["period_start"]} – {d["period_end"]} · {int(d["orders"]):,} orders · {int(d["sources"])} source file(s)' if d["orders"] else " · no records yet") + "</div>"
                        f'<div class="meta">' + (f'Last run {int(d["last_run_id"])} · {str(d["last_run_at"])[:16].replace("T", " ")} UTC · <span class="impact">{int(d["open_findings"])}</span> open findings ({int(d["high_findings"])} high) · {int(d["open_questions"])} questions pending' if d["last_run_id"] else "No analysis run") + "</div></div>", unsafe_allow_html=True)
        with b:
            st.write("")
            if not is_active and st.button("Open deal", key=f"deal_{d['id']}", width="stretch"):
                st.session_state.brand_id = int(d["id"])
                st.session_state.run_id = None
                state.ensure_state()
                state.go("overview")
            elif is_active and st.button("Go to overview", key=f"deal_{d['id']}", type="primary", width="stretch"):
                state.go("overview")

    c.divider()
    left, right = st.columns(2, gap="large")
    with left:
        c.section("New acquisition target")
        with st.form("new_brand"):
            new_name = st.text_input("Business name")
            new_cat = st.text_input("Sector", placeholder="e.g. Beauty & personal care")
            new_loc = st.text_input("Market / location", placeholder="City, Country")
            new_cur = st.selectbox("Reporting currency", CURRENCIES)
            if st.form_submit_button("Create target", type="primary"):
                slug = re.sub(r"[^a-z0-9]+", "-", new_name.lower()).strip("-")
                if not slug:
                    st.error("Enter a name.")
                elif repo.get_brand_by_slug(conn, slug):
                    st.error("A target with this name already exists.")
                else:
                    ws = conn.execute("SELECT id FROM workspaces ORDER BY id LIMIT 1").fetchone()
                    conn.execute("INSERT INTO brands(workspace_id, slug, name, category, location, reporting_currency) VALUES (?,?,?,?,?,?)",
                                 (ws[0], slug, new_name.strip(), new_cat.strip() or None, new_loc.strip() or None, new_cur))
                    st.session_state.brand_id = repo.get_brand_by_slug(conn, slug)["id"]
                    st.session_state.run_id = None
                    st.toast("Target created. Import its records in the Data room.")
                    st.rerun()
    with right:
        brand = state.brand()
        if brand is not None:
            c.section("Active target profile", brand["name"])
            with st.form("brand_form"):
                name = st.text_input("Business name", value=brand["name"])
                category = st.text_input("Sector", value=brand["category"] or "")
                location = st.text_input("Market / location", value=brand["location"] or "")
                currency = st.selectbox("Reporting currency", CURRENCIES, index=CURRENCIES.index(brand["reporting_currency"]) if brand["reporting_currency"] in CURRENCIES else 0)
                fy = st.number_input("Fiscal year starts in month", 1, 12, int(brand["fiscal_year_start_month"]))
                st.caption("Refunds are assigned to the month they were posted for reconciliation; cohort views by original order month are shown alongside.")
                if st.form_submit_button("Save profile"):
                    conn.execute("UPDATE brands SET name = ?, category = ?, location = ?, reporting_currency = ?, fiscal_year_start_month = ? WHERE id = ?",
                                 (name.strip() or brand["name"], category.strip() or None, location.strip() or None, currency, int(fy), int(brand["id"])))
                    state.invalidate()
                    st.toast("Profile saved.")
                    st.rerun()
