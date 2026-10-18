from __future__ import annotations

import re

import streamlit as st

from tell import config
from tell.analysis.engine import run_analysis
from tell.data.demo_generator import DEMO_SLUG, generate_demo
from tell.db import repository as repo
from tell.ingest import DATASETS, detect_mapping, file_sha256, import_validated, parse_csv, template_csv, validate
from tell.ui import components as c, data, state


def render() -> None:
    brand = state.brand()
    conn = state.conn()
    c.page_header("Settings & imports", "Brand profile, CSV imports with column mapping and validation, import history and demo data.", eyebrow=brand["name"] if brand else "Tell")
    tabs = st.tabs(["Import data", "Import history", "Brand profile", "Analysis & demo data"])
    with tabs[0]:
        _import_tab(conn, brand)
    with tabs[1]:
        _history_tab(conn, brand)
    with tabs[2]:
        _brand_tab(conn, brand)
    with tabs[3]:
        _demo_tab(conn, brand)


def _import_tab(conn, brand) -> None:
    bid = int(brand["id"])
    a, b = st.columns([2, 3], gap="large")
    with a:
        key = st.selectbox("Dataset", list(DATASETS), format_func=lambda k: DATASETS[k].label)
        spec = DATASETS[key]
        c.caption(spec.description)
        dayfirst = st.toggle("Dates are day-first (DD/MM/YYYY)", value=False, help="Only matters for ambiguous numeric dates; ISO dates are always accepted.")
        st.download_button("Download CSV template", template_csv(spec), file_name=f"tell-{key}-template.csv", mime="text/csv")
        with st.expander("Expected columns"):
            for f in spec.fields:
                st.markdown(f"- `{f.name}`{' (required)' if f.required else ''} — {f.kind}" + (f"; {f.description}" if f.description else ""))
    with b:
        upload = st.file_uploader("CSV file", type=["csv"], accept_multiple_files=False, label_visibility="collapsed")
        if upload is None:
            c.caption(f"Upload a .csv up to {config.max_upload_mb()} MB. Nothing is written until you confirm the import after validation.")
            return
        raw = upload.getvalue()
        try:
            df = parse_csv(raw, upload.name, config.max_upload_mb())
        except ValueError as exc:
            st.error(str(exc))
            return
        sha = file_sha256(raw)
        st.markdown(f"**{upload.name}** · {len(df):,} rows · {len(df.columns)} columns")
        c.table(df.head(5), height=200)
        suggested = detect_mapping(list(df.columns), spec)
        st.markdown('<div class="tell-eyebrow">Column mapping</div>', unsafe_allow_html=True)
        mapping: dict[str, str | None] = {}
        cols = st.columns(3)
        options = ["— not mapped —"] + list(df.columns)
        for i, f in enumerate(spec.fields):
            with cols[i % 3]:
                default = options.index(suggested[f.name]) if suggested.get(f.name) in options else 0
                choice = st.selectbox(f"{f.name}{' *' if f.required else ''}", options, index=default, key=f"map_{key}_{f.name}_{sha[:8]}")
                mapping[f.name] = None if choice == options[0] else choice
        result = validate(df, mapping, spec, conn, bid, sha, dayfirst)
        st.write("")
        c.kpi_row([("Rows", f"{result.rows_total:,}", None), ("Valid, new", f"{len(result.valid):,}", None),
                   ("Rejected", f"{result.error_rows:,}", "rows with errors"), ("Already in database", f"{result.existing_in_db:,}", "skipped")])
        for w in result.warnings:
            st.warning(w)
        if result.errors:
            with st.expander(f"Validation errors ({len(result.errors)})", expanded=result.error_rows == result.rows_total):
                c.table(result.errors_df(), height=240)
        if result.valid:
            with st.expander("Preview of rows to import"):
                c.table(result.preview_df(10).drop(columns=["_row"]))
        allow = st.checkbox("Allow re-import of a file that was imported before", value=False) if result.file_already_imported else False
        if st.button(f"Import {len(result.valid):,} valid rows", type="primary", disabled=not result.valid or (result.file_already_imported and not allow)):
            try:
                summary = import_validated(conn, bid, spec, upload.name, sha, mapping, result, allow_reimport=allow)
            except ValueError as exc:
                st.error(str(exc))
                return
            state.invalidate()
            st.success(f"Imported {summary.imported:,} record(s); rejected {summary.rejected:,}; skipped {summary.skipped:,} duplicate(s). Re-run the analysis to refresh findings.")


def _history_tab(conn, brand) -> None:
    hist = repo.import_history(conn, int(brand["id"]))
    if hist.empty:
        c.caption("No imports yet.")
        return
    c.table(hist.rename(columns={"id": "ID", "dataset": "Dataset", "filename": "File", "row_count": "Rows", "imported_rows": "Imported", "rejected_rows": "Rejected",
                                 "skipped_rows": "Skipped", "status": "Status", "imported_at": "Imported at (UTC)", "notes": "Notes"}), height=360)
    counts = repo.table_counts(conn, int(brand["id"]))
    c.caption("Records in database: " + " · ".join(f"{k} {v:,}" for k, v in counts.items()))


def _brand_tab(conn, brand) -> None:
    with st.form("brand_form"):
        name = st.text_input("Brand name", value=brand["name"])
        category = st.text_input("Category", value=brand["category"] or "")
        currency = st.selectbox("Reporting currency", ["AED", "USD", "EUR", "GBP", "SAR"], index=["AED", "USD", "EUR", "GBP", "SAR"].index(brand["reporting_currency"]) if brand["reporting_currency"] in ["AED", "USD", "EUR", "GBP", "SAR"] else 0)
        fy = st.number_input("Fiscal year starts in month", 1, 12, int(brand["fiscal_year_start_month"]))
        st.caption("Refund date convention: refunds are assigned to the month they were posted for reconciliation; cohort views by original order month are shown alongside.")
        if st.form_submit_button("Save profile", type="primary"):
            conn.execute("UPDATE brands SET name = ?, category = ?, reporting_currency = ?, fiscal_year_start_month = ? WHERE id = ?",
                         (name.strip() or brand["name"], category.strip() or None, currency, int(fy), int(brand["id"])))
            state.invalidate()
            st.success("Saved.")
            st.rerun()
    c.divider()
    st.markdown("<h3>Add a brand</h3>", unsafe_allow_html=True)
    with st.form("new_brand"):
        new_name = st.text_input("Name")
        new_cur = st.selectbox("Currency", ["AED", "USD", "EUR", "GBP", "SAR"])
        if st.form_submit_button("Create empty brand"):
            slug = re.sub(r"[^a-z0-9]+", "-", new_name.lower()).strip("-")
            if not slug:
                st.error("Enter a name.")
            elif repo.get_brand_by_slug(conn, slug):
                st.error("A brand with this name already exists.")
            else:
                ws = conn.execute("SELECT id FROM workspaces ORDER BY id LIMIT 1").fetchone()
                conn.execute("INSERT INTO brands(workspace_id, slug, name, reporting_currency) VALUES (?,?,?,?)", (ws[0], slug, new_name.strip(), new_cur))
                st.session_state.brand_id = repo.get_brand_by_slug(conn, slug)["id"]
                st.session_state.run_id = None
                st.rerun()


def _demo_tab(conn, brand) -> None:
    st.markdown("<h3>Analysis</h3>", unsafe_allow_html=True)
    c.caption(f"Database: {config.db_path()} (persists across restarts). Runs store the data hash and rule versions so results can be reproduced and compared.")
    label = st.text_input("Run label (optional)", placeholder="e.g. after seller's second data drop")
    if st.button("Run analysis now", type="primary"):
        with st.spinner("Analysing records..."):
            rid = run_analysis(conn, int(brand["id"]), label or None)
        st.session_state.run_id = rid
        st.success(f"Run {rid} completed.")
        st.rerun()
    c.divider()
    st.markdown("<h3>Demo data</h3>", unsafe_allow_html=True)
    c.caption("Saffron & Sage is a synthetic business generated deterministically (seed 20250101). Resetting deletes the demo brand, its imports, runs, findings and reports, then regenerates identical source data.")
    confirm = st.text_input("Type RESET to confirm", key="reset_confirm")
    if st.button("Reset demo data", disabled=confirm.strip() != "RESET"):
        generate_demo(conn, force=True)
        state.invalidate()
        demo = repo.get_brand_by_slug(conn, DEMO_SLUG)
        st.session_state.brand_id = demo["id"]
        st.session_state.run_id = None
        st.success("Demo data regenerated.")
        st.rerun()
