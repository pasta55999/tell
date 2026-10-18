"""Data room: what the seller provided, how the sources reconcile with each other, CSV import
with validation, import history, and analysis / demo-data controls."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from tell import config
from tell.analysis.engine import run_analysis
from tell.data.demo_generator import DEMO_SLUG, generate_demo
from tell.db import repository as repo
from tell.ingest import DATASETS, detect_mapping, file_sha256, import_validated, parse_csv, template_csv, validate
from tell.ui import components as c, data, state, theme

VIEWS = ["Sources & integrity", "Import data", "Import history", "Analysis & demo data"]
DATASET_LABELS = {"products": "Products & costs", "orders": "Orders", "order_items": "Order lines", "refunds": "Refunds", "refund_items": "Refund lines", "ad_spend": "Advertising",
                  "inventory_snapshots": "Inventory snapshots", "supplier_receipts": "Supplier receipts", "seller_statements": "Seller statements"}


def render() -> None:
    brand = state.brand()
    conn = state.conn()
    c.page_header("Data room", eyebrow=brand["name"])
    view = st.segmented_control("View", VIEWS, default=VIEWS[0], label_visibility="collapsed")
    if view == VIEWS[0]:
        _sources(conn, brand)
    elif view == VIEWS[1]:
        _import(conn, brand)
    elif view == VIEWS[2]:
        _history(conn, brand)
    else:
        _analysis(conn, brand)


# ---------------------------------------------------------------- sources & integrity

def _sources(conn, brand) -> None:
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    counts = repo.table_counts(conn, bid)
    h = data.data_hash(bid)
    cov, sc, label = data.coverage_info(bid, h)
    run = state.run()
    f = data.findings(int(run["id"])) if run is not None else pd.DataFrame()
    rules = set(f["rule_id"]) if not f.empty else set()
    fin = data.financials(bid, h)
    hist = repo.import_history(conn, bid)
    c.hero([("Source files", str(len(hist)), "imported into this deal"), ("Records", f"{sum(counts.values()):,}", " · ".join(f"{DATASET_LABELS[k]} {v:,}" for k, v in counts.items() if v)[:80] + "…"),
            ("Coverage", f"{sc}/100", label + (" — every dataset spans the order period" if sc >= 95 else " — gaps listed below"), theme.EMERALD if sc >= 95 else theme.AMBER),
            ("Data hash", h, "changes whenever source data changes")], small=True)

    c.section("Do the sources agree with each other?", "Each row compares two independent sources for the same fact")
    n_months = len(fin)
    stmt_months = n_months - len(cov["statements_missing"])
    rows = []
    if stmt_months:
        rev = f[f["rule_id"] == "REV-001"] if not f.empty else pd.DataFrame()
        rows.append(("Seller statements ↔ order & refund ledger (revenue)", "Conflict" if "REV-001" in rules else "Agree", theme.CORAL if "REV-001" in rules else theme.EMERALD,
                     f"{stmt_months} of {n_months} months", f"{len(rev)} month(s) differ by more than 2%: {', '.join(sorted(rev['subject']))}." if len(rev) else "Reported revenue within 2% of supported net sales in every month."))
        cogs_var = ((fin["reported_cogs"] - fin["cogs"]) / fin["cogs"] * 100).abs().max() if fin["reported_cogs"].notna().any() else None
        if cogs_var is not None:
            rows.append(("Seller statements ↔ order-line costs (COGS)", "Agree" if cogs_var < 2 else "Conflict", theme.EMERALD if cogs_var < 2 else theme.CORAL, f"{stmt_months} of {n_months} months", f"Largest monthly gap {cogs_var:.1f}%."))
        if fin["reported_ad_spend"].notna().any():
            adv = f[f["rule_id"] == "ADV-002"] if not f.empty else pd.DataFrame()
            rows.append(("Seller statements ↔ advertising platforms", "Conflict" if len(adv) else "Agree", theme.CORAL if len(adv) else theme.EMERALD, f"{stmt_months} of {n_months} months",
                         f"{len(adv)} month(s) differ by 10% or more: {', '.join(sorted(adv['subject']))}." if len(adv) else "Reported advertising within 10% of platform billing in every month."))
    else:
        rows.append(("Seller statements ↔ order ledger", "Unverified", theme.SLATE, "no statements", "Import the seller's management accounts to reconcile reported revenue, COGS and advertising."))
    if counts["inventory_snapshots"]:
        inv = f[f["rule_id"] == "INV-001"] if not f.empty else pd.DataFrame()
        rows.append(("Warehouse counts ↔ receipts, sales & returns", "Conflict" if len(inv) else "Agree", theme.CORAL if len(inv) else theme.EMERALD, f"{n_months - len(cov['inventory_missing'])} of {n_months} months",
                     f"{len(inv)} SKU(s) do not roll forward: {', '.join(inv['subject'])}." if len(inv) else "Every SKU's month-end count matches the movement-based expectation."))
    else:
        rows.append(("Warehouse counts ↔ movements", "Unverified", theme.SLATE, "no snapshots", "Import month-end stock counts to test for shrinkage or phantom stock."))
    if counts["supplier_receipts"]:
        s3 = f[f["rule_id"] == "INV-003"] if not f.empty else pd.DataFrame()
        rows.append(("Supplier invoices ↔ unit cost used in margins", "Conflict" if len(s3) else "Agree", theme.CORAL if len(s3) else theme.EMERALD, f"{counts['supplier_receipts']} receipts",
                     f"{len(s3)} SKU(s) invoiced 5%+ away from the recorded cost: {', '.join(s3['subject'])}." if len(s3) else "Invoice costs match the costs recorded on sales."))
    else:
        rows.append(("Supplier invoices ↔ recorded unit cost", "Unverified", theme.SLATE, "no receipts", "Import goods-received notes to test the cost base."))
    if counts["refunds"]:
        late = "REF-002" in rules
        rows.append(("Refund postings ↔ original orders (timing)", "Conflict" if late else "Agree", theme.CORAL if late else theme.EMERALD, f"{counts['refunds']} refunds linked to orders",
                     "A cluster of refunds was posted long after the sales they relate to." if late else "Refunds are posted within the normal window after their orders."))
    if counts["ad_spend"]:
        rows.append(("Advertising attribution", "Partial" if cov["channels_with_attribution"] < cov["channels_total"] else "Agree", theme.AMBER if cov["channels_with_attribution"] < cov["channels_total"] else theme.EMERALD,
                     f"{cov['channels_with_attribution']} of {cov['channels_total']} channels", "Return on spend can only be read where the platform reports attributed revenue; the rest is unverified."))
    c.source_map(rows)

    gaps = [g for g in [("Seller statements", cov["statements_missing"]), ("Advertising", cov["ad_spend_missing"]), ("Inventory snapshots", cov["inventory_missing"])] if g[1]]
    if gaps or cov["units_without_cost"]:
        c.section("Gaps that limit the analysis")
        for name, months in gaps:
            st.markdown(f"- **{name}** missing for {len(months)} month(s): {', '.join(months)}")
        if cov["units_without_cost"]:
            st.markdown(f"- **{cov['units_without_cost']:,} units** sold without any unit cost (excluded from COGS; margins understated by the missing cost)")
    if run is not None and run["skipped"]:
        sk = json.loads(run["skipped"]).get("skipped", [])
        if sk:
            c.insight("Skipped in the last run: " + " ".join(sk), "cobalt")

    c.section("What was provided", "Record counts by dataset")
    c.ledger([(DATASET_LABELS[k], f"{v:,}", None) for k, v in counts.items()])


# ---------------------------------------------------------------- import

def _import(conn, brand) -> None:
    bid = int(brand["id"])
    a, b = st.columns([2, 3], gap="large")
    with a:
        c.section("1 · Choose the dataset")
        key = st.selectbox("Dataset", list(DATASETS), format_func=lambda k: DATASETS[k].label, label_visibility="collapsed")
        spec = DATASETS[key]
        c.caption(spec.description)
        dayfirst = st.toggle("Dates are day-first (DD/MM/YYYY)", value=False, help="Only matters for ambiguous numeric dates; ISO dates are always accepted.")
        st.download_button("CSV template", template_csv(spec), file_name=f"tell-{key}-template.csv", mime="text/csv", icon=":material/download:")
        with st.expander("Expected columns"):
            for fld in spec.fields:
                st.markdown(f"- `{fld.name}`{' (required)' if fld.required else ''} — {fld.kind}" + (f"; {fld.description}" if fld.description else ""))
    with b:
        c.section("2 · Upload and map", f"Up to {config.max_upload_mb()} MB · nothing is written until you confirm")
        upload = st.file_uploader("CSV file", type=["csv"], accept_multiple_files=False, label_visibility="collapsed")
        if upload is None:
            c.panel("Waiting for a file", "Drop a CSV export here. Columns are detected from common export headers (Shopify, marketplace and accounting exports) and can be remapped before validation.", "tint")
            return
        raw = upload.getvalue()
        try:
            df = parse_csv(raw, upload.name, config.max_upload_mb())
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
            return
        sha = file_sha256(raw)
        st.markdown(f"**{upload.name}** · {len(df):,} rows · {len(df.columns)} columns")
        c.table(df.head(5), height=200)
        suggested = detect_mapping(list(df.columns), spec)
        mapping: dict[str, str | None] = {}
        cols = st.columns(3)
        options = ["— not mapped —"] + list(df.columns)
        for i, fld in enumerate(spec.fields):
            with cols[i % 3]:
                default = options.index(suggested[fld.name]) if suggested.get(fld.name) in options else 0
                choice = st.selectbox(f"{fld.name}{' *' if fld.required else ''}", options, index=default, key=f"map_{key}_{fld.name}_{sha[:8]}")
                mapping[fld.name] = None if choice == options[0] else choice
        result = validate(df, mapping, spec, conn, bid, sha, dayfirst)
        c.section("3 · Validation")
        c.hero([("Rows", f"{result.rows_total:,}", None), ("Valid, new", f"{len(result.valid):,}", "will be written", theme.EMERALD),
                ("Rejected", f"{result.error_rows:,}", "listed with row and reason", theme.CORAL if result.error_rows else None), ("Already present", f"{result.existing_in_db:,}", "skipped as duplicates")], small=True)
        for w in result.warnings:
            st.warning(w, icon=":material/warning:")
        if result.errors:
            with st.expander(f"Validation errors ({len(result.errors)})", expanded=result.error_rows == result.rows_total):
                c.table(result.errors_df(), height=240)
        if result.valid:
            with st.expander("Preview of rows to import"):
                c.table(result.preview_df(10).drop(columns=["_row"]))
        allow = st.checkbox("Allow re-import of a file that was imported before", value=False) if result.file_already_imported else False
        if st.button(f"Import {len(result.valid):,} valid rows", type="primary", disabled=not result.valid or (result.file_already_imported and not allow), icon=":material/upload:"):
            try:
                summary = import_validated(conn, bid, spec, upload.name, sha, mapping, result, allow_reimport=allow)
            except ValueError as exc:
                st.error(str(exc), icon=":material/error:")
                return
            state.invalidate()
            st.success(f"Imported {summary.imported:,} record(s); rejected {summary.rejected:,}; skipped {summary.skipped:,} duplicate(s). Re-run the analysis to refresh findings.", icon=":material/check_circle:")


def _history(conn, brand) -> None:
    hist = repo.import_history(conn, int(brand["id"]))
    c.section("Import history", "Every file, with what was written, rejected and skipped")
    if hist.empty:
        c.caption("No imports yet.")
        return
    c.table(hist.rename(columns={"id": "ID", "dataset": "Dataset", "filename": "File", "row_count": "Rows", "imported_rows": "Imported", "rejected_rows": "Rejected",
                                 "skipped_rows": "Skipped", "status": "Status", "imported_at": "Imported at (UTC)", "notes": "Notes"}), height=360)


def _analysis(conn, brand) -> None:
    c.section("Analysis", "Runs are stored with a data hash and rule versions so results can be reproduced and compared")
    c.caption(f"Database: {config.db_path()} (persists across restarts).")
    label = st.text_input("Run label (optional)", placeholder="e.g. after seller's second data drop")
    if st.button("Run analysis now", type="primary", icon=":material/play_arrow:"):
        with st.spinner("Analysing records..."):
            rid = run_analysis(conn, int(brand["id"]), label or None)
        st.session_state.run_id = rid
        st.success(f"Run {rid} completed.")
        st.rerun()
    c.section("Demo data", "Destructive: requires confirmation")
    c.caption("Saffron & Sage is a synthetic business generated deterministically (seed 20250101). Resetting deletes the demo brand, its imports, runs, findings, reviews and reports, then regenerates identical source data.")
    confirm = st.text_input("Type RESET to confirm", key="reset_confirm")
    if st.button("Reset demo data", disabled=confirm.strip() != "RESET", icon=":material/restart_alt:"):
        generate_demo(conn, force=True)
        state.invalidate()
        demo = repo.get_brand_by_slug(conn, DEMO_SLUG)
        st.session_state.brand_id = demo["id"]
        st.session_state.run_id = None
        st.success("Demo data regenerated.")
        st.rerun()
