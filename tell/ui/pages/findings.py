"""Findings investigation workspace: a navigable list, a story-led detail pane with the figures,
the rule, the evidence rows, alternatives, follow-up status with history, related findings and
the seller questions each finding generates."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from tell.analysis.engine import compare_runs, run_analysis, update_finding_status
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import charts, components as c, data, state, theme

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# Plausible alternative explanations the analyst should rule out. These are generic to the rule,
# stated as possibilities, and never presented as the cause.
ALTERNATIVES = {
    "REV-001": ["Revenue recognised on dispatch or payment date rather than order date (timing).", "Shipping income, VAT or marketplace fees included in the reported figure.", "Manual journal adjustments or wholesale invoices not present in the order export."],
    "ADV-002": ["Agency fees or platform credits netted off in the accounts.", "Spend accrued in a different month to the platform billing date.", "A channel excluded from the export the seller provided."],
    "REF-001": ["A single defective batch rather than a structural quality problem.", "A courier or packaging issue specific to this SKU's size or fragility.", "Listing or photography that sets the wrong expectation."],
    "REF-002": ["A deliberate goodwill campaign after a known complaint wave.", "A back-office backlog that delayed processing legitimate returns.", "Refunds re-issued after failed payment reversals."],
    "REF-003": ["A supplier batch or courier incident affecting this month's deliveries.", "The late-refund cluster (REF-002) inflating this cohort after the fact."],
    "MAR-001": ["Deliberate price investment to win share, with increases planned.", "Freight or FX cost shocks that have since reversed.", "Mix shift towards lower-margin SKUs rather than cost inflation per SKU."],
    "DSC-001": ["A planned seasonal or launch campaign with a documented brief.", "Clearance of discontinued stock recorded as discount rather than write-down."],
    "CON-001": ["A deliberate hero-product strategy with protected supply and IP.", "New products launched late in the period that are not yet visible in annual shares."],
    "INV-001": ["A goods-received note missing from the export rather than missing stock.", "Transfers to a second location or marketplace warehouse not in the snapshot.", "Count timing not aligned to month end."],
    "INV-002": ["Receipts recorded after sales in the same month (sequence, not substance)."],
    "INV-003": ["A temporary price surcharge the supplier later credited.", "Standard cost deliberately held until stock bought at the old price sells through."],
    "SEA-001": ["A one-off bulk or B2B order rather than consumer seasonality.", "Pulled-forward demand ahead of a price rise."],
    "DQ-001": ["Files exist but were not included in the data room export."],
}


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    run = state.run()
    conn = state.conn()
    c.page_header("Findings", eyebrow=brand["name"])
    if run is None:
        if c.empty_state("No analysis run yet", "Run the analysis to reconcile the records and surface findings.", "Run analysis", key="fd_run"):
            with st.spinner("Analysing records..."):
                st.session_state.run_id = run_analysis(conn, bid)
            st.rerun()
        return
    f = data.findings(int(run["id"]))
    if f.empty:
        c.panel("No findings", "The analysis completed without raising any findings on this data.", "emerald")
        return

    material = f[f["classification"] != "observation"]
    open_n = int((~material["status"].isin(["verified", "dismissed"])).sum())
    disc_total = f[f["classification"] == "discrepancy"]["estimated_impact"].fillna(0).sum()
    c.hero([("Material findings", str(len(material)), f"{int(f['severity'].isin(['critical', 'high']).sum())} high severity · {len(f) - len(material)} observations", theme.CORAL),
            ("Quantified discrepancies", c.money(disc_total, cur), "reported vs supported values", theme.VIOLET),
            ("Open", str(open_n), f"{int((f['status'] == 'detected').sum())} not yet reviewed", theme.AMBER if open_n else theme.EMERALD)], small=True)

    # ---------------------------------------------------------------- controls
    f1, f2, f3, f4 = st.columns([4, 2, 2, 1])
    with f1:
        q = st.text_input("Search", placeholder="Search title, SKU, month or rule…", label_visibility="collapsed", key="fd_q")
    with f2:
        sev_filter = st.multiselect("Severity", list(SEV_ORDER), default=[], placeholder="All severities", label_visibility="collapsed")
    with f3:
        sort = st.selectbox("Sort", ["Severity", "Impact", "Period", "Category"], label_visibility="collapsed")
    with f4:
        with st.popover("More", width="stretch"):
            cls_filter = st.multiselect("Type", list(theme.CLASS_LABELS), default=[], format_func=lambda k: theme.CLASS_LABELS[k], placeholder="All types")
            status_filter = st.multiselect("Status", list(theme.STATUS_LABELS), default=[], format_func=lambda k: theme.STATUS_LABELS[k], placeholder="Any status")
    view = f.copy()
    if q:
        ql = q.lower()
        view = view[view.apply(lambda r: ql in f"{r['title']} {r['subject']} {r['rule_id']} {r['category']} {r['summary']}".lower(), axis=1)]
    if sev_filter:
        view = view[view["severity"].isin(sev_filter)]
    if cls_filter:
        view = view[view["classification"].isin(cls_filter)]
    if status_filter:
        view = view[view["status"].isin(status_filter)]
    if sort == "Impact":
        view = view.sort_values("estimated_impact", ascending=False, na_position="last")
    elif sort == "Period":
        view = view.sort_values(["period_start", "severity"])
    elif sort == "Category":
        view = view.assign(_s=view["severity"].map(SEV_ORDER)).sort_values(["category", "_s"]).drop(columns="_s")
    active = [x for x in [f'"{q}"' if q else "", ", ".join(sev_filter), ", ".join(theme.CLASS_LABELS[k] for k in cls_filter), ", ".join(theme.STATUS_LABELS[k] for k in status_filter)] if x]
    c.note(f"{len(view)} of {len(f)} findings" + (" · " + " · ".join(active) if active else ""))

    # ---------------------------------------------------------------- split view
    left, right = st.columns([5, 9], gap="large")
    with left:
        options = view["id"].tolist()
        if not options:
            c.panel("No findings match", "Clear the search or one of the filters.", "tint")
            return
        pre = st.session_state.pop("selected_finding", None)
        if pre in options:
            st.session_state.finding_radio = pre
        elif st.session_state.get("finding_radio") not in options:
            st.session_state.finding_radio = options[0]
        labels = {int(r["id"]): f"{r['severity'].upper()} · {r['title']}" for _, r in view.iterrows()}
        selected = st.radio("Finding", options, format_func=lambda i: labels[int(i)], label_visibility="collapsed", key="finding_radio")
        st.write("")
        st.download_button("Export list (CSV)", df_to_csv(view[["finding_key", "severity", "classification", "status", "category", "title", "summary", "estimated_impact", "confidence", "evidence_count"]]),
                           file_name=f"{brand['slug']}-findings-run{run['id']}.csv", mime="text/csv")
    with right:
        _detail(conn, bid, int(run["id"]), int(selected), cur, f)

    if st.session_state.pop("show_compare", False) or len([r for r in repo.list_runs(conn, bid) if r["status"] == "completed"]) >= 2:
        c.divider()
        _compare(bid)


# ---------------------------------------------------------------- detail pane

def _detail(conn, bid: int, run_id: int, finding_id: int, cur: str, all_f: pd.DataFrame) -> None:
    f = repo.get_finding(conn, finding_id)
    m = json.loads(f["measured"]) if f["measured"] else {}
    accent = theme.SEVERITY_BAR.get(f["severity"], theme.LINE_STRONG)
    st.markdown(f'<div style="border-left:4px solid {accent};padding-left:16px;margin-top:4px">'
                f'<div>{c.severity_pill(f["severity"])}{c.class_pill(f["classification"])}{c.status_pill(f["status"])}<span class="tell-note">{f["finding_key"]} · rule v{f["rule_version"]} · {c.esc(f["category"])}</span></div>'
                f'<h2 style="margin:6px 0 2px 0 !important;font-size:1.35rem !important">{c.esc(f["title"])}</h2>'
                f'<div class="tell-caption">{c.esc(f["summary"])}</div></div>', unsafe_allow_html=True)
    st.write("")

    # The story: visual + ledger side by side
    vis, led = st.columns([3, 2], gap="large")
    with vis:
        _story_visual(conn, bid, f, m, cur)
    with led:
        st.markdown('<div class="tell-eyebrow muted">The numbers</div>', unsafe_allow_html=True)
        c.ledger(*_ledger_rows(f, m, cur))
        c.hero([("Estimated impact", c.money(f["estimated_impact"], cur) if f["estimated_impact"] is not None else "not quantified", f["impact_basis"][:90] + ("…" if f["impact_basis"] and len(f["impact_basis"]) > 90 else "") if f["impact_basis"] else "", accent)], small=True)

    n_ev = int(all_f.loc[all_f["id"] == finding_id, "evidence_count"].iloc[0]) if (all_f["id"] == finding_id).any() else 0
    tabs = st.tabs(["Why it matters", "How it was detected", f"Evidence ({n_ev})", "Confidence & alternatives", "Follow-up & history", "Seller questions"])
    with tabs[0]:
        st.write(f["explanation"])
        rel = repo.related_findings(conn, run_id, finding_id)
        if not rel.empty:
            st.markdown('<div class="tell-eyebrow muted" style="margin-top:10px">Related findings</div>', unsafe_allow_html=True)
            c.caption("Share the same subject, period or category. Links are structural, not causal.")
            for _, r in rel.head(6).iterrows():
                a, b = st.columns([5, 1])
                with a:
                    st.markdown(c.list_item(r["link"], r["title"], f"{r['finding_key']} · {r['severity']}", theme.SEVERITY_BAR.get(r["severity"], theme.LINE_STRONG)), unsafe_allow_html=True)
                with b:
                    if st.button("Open", key=f"rel_{finding_id}_{r['id']}"):
                        st.session_state.selected_finding = int(r["id"])
                        st.rerun()
    with tabs[1]:
        st.write(f["method"])
        with st.expander("Measured values used by the rule"):
            st.json(m, expanded=False)
    with tabs[2]:
        ev = repo.evidence_for_finding(conn, finding_id)
        c.caption(f"{len(ev)} source rows. Each names the table and record the rule used, so every figure above can be traced to a row in the data room.")
        show = ev[["source_table", "source_id", "source_ref", "description", "value"]].rename(columns={"source_table": "Table", "source_id": "Record", "source_ref": "Reference", "description": "Description", "value": "Value"})
        c.table(show, height=min(380, 38 * len(show) + 40))
        st.download_button("Export evidence (CSV)", df_to_csv(ev.drop(columns=["extra"])), file_name=f"evidence-{f['finding_key'].replace(':', '-')}.csv", mime="text/csv", key=f"ev_{finding_id}")
        _source_rows(conn, ev)
    with tabs[3]:
        st.markdown(f"**Confidence: {f['confidence']}.** {f['confidence_note'] or ''}")
        alts = ALTERNATIVES.get(f["rule_id"], [])
        if alts:
            st.markdown("**Alternative explanations to rule out**")
            for a in alts:
                st.markdown(f"- {a}")
        st.markdown("**Limitations.** " + {"discrepancy": "The two figures come from the records provided; a missing export or a different accounting convention would change the variance.",
                                             "suspected_risk": "This is a pattern, not a confirmed issue. Thresholds are documented and versioned but not calibrated on real deal data.",
                                             "observation": "Informational; recorded so that it is not mistaken for a risk later."}[f["classification"]])
    with tabs[4]:
        if f["next_action"]:
            c.insight("Recommended follow-up: " + f["next_action"], "cobalt")
        st.write("")
        s1, s2 = st.columns([2, 3])
        with s1:
            new_status = st.selectbox("Status", list(theme.STATUS_LABELS), index=list(theme.STATUS_LABELS).index(f["status"]), format_func=lambda k: theme.STATUS_LABELS[k], key=f"st_{finding_id}")
        with s2:
            note = st.text_input("Note", value="", placeholder="What was checked, with whom, and the outcome", key=f"nt_{finding_id}")
        if st.button("Save", type="primary", key=f"sv_{finding_id}"):
            update_finding_status(conn, finding_id, new_status, note or None)
            st.toast("Review recorded.")
            st.rerun()
        hist = repo.finding_history(conn, f["finding_key"])
        st.markdown('<div class="tell-eyebrow muted" style="margin-top:12px">Investigation history</div>', unsafe_allow_html=True)
        if hist.empty:
            c.caption("Not yet reviewed. Status changes and notes are recorded here with a timestamp.")
        else:
            c.timeline([(str(h["created_at"])[:16], f"{c.esc((h['from_status'] or '').replace('_', ' '))} → <b>{c.esc(h['to_status'].replace('_', ' '))}</b>" + (f" — {c.esc(h['note'])}" if h["note"] else "") + f" <span class=tell-note>run {h['run_id']}</span>",
                         theme.EMERALD if h["to_status"] in ("verified",) else theme.MUTED if h["to_status"] == "dismissed" else theme.COBALT) for _, h in hist.iterrows()])
    with tabs[5]:
        qs = repo.questions_for_finding(conn, finding_id)
        for _, qrow in qs.iterrows():
            st.markdown(f"{c.priority_pill(qrow['priority'])}{c.pill(qrow['status'], *theme.STATUS_COLORS[{'pending': 'detected', 'answered': 'needs_investigation', 'resolved': 'verified'}[qrow['status']]])} **{c.esc(qrow['question'])}**", unsafe_allow_html=True)
            c.caption(f"Why: {qrow['rationale']}")
            c.caption(f"Request: {qrow['requested_items']}")
        if st.button("Manage in Seller questions", key=f"q_{finding_id}"):
            st.session_state.question_focus = f["finding_key"]
            state.go("questions")


def _ledger_rows(f, m: dict, cur: str) -> tuple[list, tuple | None]:
    r, total = [], None
    money = lambda v: f"{cur} {float(v):,.0f}"  # noqa: E731
    rid = f["rule_id"]
    if rid == "REV-001":
        r = [("Seller-reported revenue", money(m["reported_revenue"]), f["subject"]), ("Order-ledger gross sales", money(m["gross_sales"]), "completed orders after discounts"),
             ("Refunds posted", "− " + money(m["refunds_posted"]), "deducted to reach net sales"), ("Supported net sales", money(m["net_sales"]), None),
             ("Cancelled orders (memo)", money(m["cancelled_value"]), "excluded from the ledger")]
        total = ("Variance (reported − supported)", f"{'+' if m['variance'] >= 0 else '−'}{money(abs(m['variance']))} · {m['variance_pct']:+.1f}%")
    elif rid == "ADV-002":
        r = [(ch["channel"], money(ch["spend"]), None) for ch in m["channels"]] + [("Platform total", money(m["recorded_ad_spend"]), None), ("Seller statement", money(m["reported_ad_spend"]), None)]
        total = ("Variance", f"{'+' if m['variance'] >= 0 else '−'}{money(abs(m['variance']))} · {m['variance_pct']:+.0f}%")
    elif rid == "REF-001":
        r = [("Units sold", f"{m['units_sold']:,}", None), ("Units refunded", f"{m['refunded_units']:,}", None), ("Return rate", f"{m['return_rate_pct']:.1f}%", None, True),
             ("Portfolio return rate", f"{m['portfolio_return_rate_pct']:.1f}%", None), ("Threshold", f"{m['threshold_pct']:.1f}%", "max(10%, 2× portfolio)")]
        total = ("Refunded value", money(m["refunded_amount"]))
    elif rid == "REF-002":
        r = [("Late refunds", f"{m['late_refund_count']}", f"lag {m['lag_days_min']}–{m['lag_days_max']} days"), ("Share of month's refunds", f"{m['share_of_month_refunds_pct']:.0f}%", None, True)] + \
            [(f"From {k} orders", f"{v}", None) for k, v in sorted(m["source_periods"].items())]
        total = ("Late refund value", money(m["late_refund_value"]))
    elif rid == "REF-003":
        r = [("Cohort refund rate", f"{m['cohort_refund_rate_pct']:.1f}%", None, True), ("Median other months", f"{m['median_other_months_pct']:.1f}%", None), ("Refunds in cohort", f"{m['refund_count']}", None), ("Refunded > 45 days after sale", f"{m['late_share_pct']:.0f}%", None)]
        total = ("Refund value", money(m["refund_value"]))
    elif rid == "MAR-001":
        fw, lw = m["first_window"], m["last_window"]
        r = [(f"Gross margin {fw['period_start']}–{fw['period_end']}", f"{fw['gross_margin_pct']:.1f}%", None), (f"Gross margin {lw['period_start']}–{lw['period_end']}", f"{lw['gross_margin_pct']:.1f}%", None, True),
             ("Gross sales growth", f"{m['revenue_growth_pct']:+.0f}%", None), ("Avg unit cost", f"{m['avg_unit_cost_change_pct']:+.1f}%", None, True), ("Avg selling price", f"{m['avg_selling_price_change_pct']:+.1f}%", None)]
        total = ("Margin change", f"{m['margin_change_pp']:+.1f}pp")
    elif rid == "DSC-001":
        r = [("Discount rate", f"{m['discount_rate_pct']:.1f}%", None, True), ("Median other months", f"{m['median_other_months_pct']:.1f}%", None), ("Robust z", f"{m['robust_z']:.1f}", None), ("Gross margin that month", f"{m['gross_margin_pct']:.1f}%", None)]
        total = ("Discounts given", money(m["discounts"]))
    elif rid == "CON-001":
        r = [(t["sku"], f"{t['revenue_share_pct']:.1f}%", t["name"]) for t in m["top3"]]
        total = ("Top-3 share", f"{m['top3_share_pct']:.1f}%")
    elif rid == "INV-001":
        r = [(d["period"], f"{d['variance']:+d}", f"exp. {d['expected']} / counted {d['recorded']}", True) for d in m["detail"]]
        total = ("Cumulative variance", f"{m['cumulative_variance_units']:+d} units" + (f" · {money(abs(m['cumulative_variance_units']) * m['unit_cost'])}" if m.get("unit_cost") else ""))
    elif rid == "INV-003":
        r = [(mm["receipt_ref"], f"{cur} {mm['supplier_unit_cost']:,.2f}", f"{mm['period']} · recorded {cur} {mm['recorded_unit_cost']:,.2f} · {mm['variance_pct']:+.0f}%", True) for mm in m["mismatches"]]
        total = ("Units sold since first mismatch", f"{m['units_sold_since']:,}")
    elif rid == "SEA-001":
        r = [("Gross sales", money(m["gross_sales"]), f"{m['sales_growth_pct']:+.0f}% vs baseline"), ("Completed orders", f"{m['orders_completed']:,}", f"{m['orders_growth_pct']:+.0f}% vs baseline"),
             ("Average order value", money(m["aov"]), f"baseline {money(m['aov_baseline'])}"), ("Discount rate", f"{m['discount_rate_pct']:.1f}%", None), ("Gross margin", f"{m['gross_margin_pct']:.1f}%", None)]
        total = ("Checks passed", f"{sum(1 for v in m['checks'].values() if v)} of {sum(1 for v in m['checks'].values() if v is not None)}")
    else:
        r = [(k.replace("_", " "), str(v), None) for k, v in list(m.items())[:8] if not isinstance(v, (dict, list))]
    return r, total


def _story_visual(conn, bid: int, f, m: dict, cur: str) -> None:
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    rid, subj = f["rule_id"], f["subject"]
    cfg = {"displayModeBar": False}
    st.markdown('<div class="tell-eyebrow muted">The story</div>', unsafe_allow_html=True)
    if rid == "REV-001":
        row = fin[fin["period"] == subj].iloc[0]
        st.plotly_chart(charts.waterfall(row, cur), width="stretch", config=cfg)
    elif rid == "ADV-002":
        st.plotly_chart(charts.statement_vs_platform(fin, cur, subj), width="stretch", config=cfg)
    elif rid == "REF-001":
        prod = data.products(bid, h)
        rr = prod[prod["units"] >= 30].sort_values("return_rate_pct", ascending=False)
        st.plotly_chart(charts.share_bars(rr, "sku", "return_rate_pct", top=10, highlight_over=m.get("threshold_pct"), color=theme.VIOLET), width="stretch", config=cfg)
    elif rid == "REF-002":
        st.plotly_chart(charts.lag_scatter(repo.refund_lags(conn, bid), subj, cur), width="stretch", config=cfg)
    elif rid == "REF-003":
        st.plotly_chart(charts.highlight_line(fin, "period", "refund_rate_pct", "Cohort refund rate", [subj], "%", theme.CORAL, baseline=float(fin["refund_rate_pct"].median())), width="stretch", config=cfg)
    elif rid == "MAR-001":
        st.plotly_chart(charts.margin_story(fin, cur), width="stretch", config=cfg)
    elif rid == "DSC-001":
        st.plotly_chart(charts.highlight_line(fin, "period", "discount_rate_pct", "Discount rate", [subj], "%", theme.VIOLET, baseline=float(fin["discount_rate_pct"].median())), width="stretch", config=cfg)
    elif rid == "CON-001":
        st.plotly_chart(charts.contribution_view(data.products(bid, h)), width="stretch", config=cfg)
    elif rid in ("INV-001", "INV-002"):
        rf = data.inventory_rollforward(bid, h)
        st.plotly_chart(charts.inventory_rollforward(rf[rf["sku"] == subj]), width="stretch", config=cfg)
    elif rid == "INV-003":
        receipts = repo.supplier_receipts(conn, bid)
        rec_cost = repo.product_cost_by_month(conn, bid)
        pid = receipts.loc[receipts["sku"] == subj, "product_id"].iloc[0] if (receipts["sku"] == subj).any() else None
        if pid is not None:
            st.plotly_chart(charts.cost_vs_invoice(rec_cost[rec_cost["product_id"] == pid].sort_values("period"), receipts[receipts["product_id"] == pid], cur), width="stretch", config=cfg)
    elif rid == "SEA-001":
        st.plotly_chart(charts.highlight_line(fin, "period", "gross_sales", f"Gross sales ({cur})", [subj], "", theme.COBALT), width="stretch", config=cfg)
        checks = m.get("checks", {})
        st.markdown(" ".join(c.pill(("✓ " if v else "✗ " if v is False else "– ") + k.replace("_", " "), *(theme.EMERALD, theme.EMERALD_SOFT) if v else (theme.CORAL, theme.CORAL_SOFT) if v is False else (theme.MUTED, theme.SURFACE_ALT)) for k, v in checks.items()), unsafe_allow_html=True)
    else:
        c.caption("No visual for this finding type; see the figures and evidence.")


def _source_rows(conn, ev: pd.DataFrame) -> None:
    with_ids = ev[ev["source_id"].notna()]
    if with_ids.empty:
        return
    table = with_ids["source_table"].iloc[0]
    ids = [int(i) for i in with_ids["source_id"].head(200)]
    marks = ",".join("?" for _ in ids)
    sql = {
        "refunds": f"SELECT r.refund_ref, r.refund_date, r.amount, r.reason, o.order_ref, o.order_date FROM refunds r JOIN orders o ON o.id = r.order_id WHERE r.id IN ({marks})",
        "inventory_snapshots": f"SELECT s.snapshot_date, p.sku, s.quantity_on_hand, s.source FROM inventory_snapshots s JOIN products p ON p.id = s.product_id WHERE s.id IN ({marks})",
        "supplier_receipts": f"SELECT r.receipt_ref, p.sku, r.received_date, r.quantity, r.unit_cost, r.supplier FROM supplier_receipts r JOIN products p ON p.id = r.product_id WHERE r.id IN ({marks})",
        "products": f"SELECT sku, name, category, list_price, standard_cost FROM products WHERE id IN ({marks})",
    }.get(table)
    if sql:
        with st.expander(f"Underlying rows from `{table}` ({len(ids)})"):
            c.table(repo.fetch_df(conn, sql, ids), height=min(360, 38 * len(ids) + 40))


def _compare(bid: int) -> None:
    conn = state.conn()
    runs = [r for r in repo.list_runs(conn, bid) if r["status"] == "completed"]
    c.section("Between runs", "Which findings are new, resolved or changed between two stored runs")
    if len(runs) < 2:
        c.caption("Run the analysis again after importing new data to compare runs.")
        return
    label = {r["id"]: f"Run {r['id']} · {str(r['finished_at'])[:16].replace('T', ' ')} · {r['finding_count']} findings · data {r['data_hash']}" for r in runs}
    a, b = st.columns(2)
    with a:
        base = st.selectbox("Baseline", [r["id"] for r in runs], index=min(1, len(runs) - 1), format_func=lambda i: label[i])
    with b:
        new = st.selectbox("Comparison", [r["id"] for r in runs], index=0, format_func=lambda i: label[i])
    if base == new:
        c.caption("Select two different runs.")
        return
    cmp = compare_runs(conn, int(base), int(new))
    c.hero([("New", str(len(cmp["new"])), None, theme.CORAL if cmp["new"] else None), ("Resolved", str(len(cmp["resolved"])), "rule no longer fires", theme.EMERALD if cmp["resolved"] else None),
            ("Changed", str(len(cmp["changed"])), "severity or impact differs", theme.AMBER if cmp["changed"] else None), ("Unchanged", str(cmp["unchanged_count"]), None)], small=True)
    c.caption(("Same underlying data" if cmp["same_data"] else "Underlying data differs between runs") + " · " + ("same rule versions" if cmp["same_rules"] else "rule versions differ")
              + ". 'Resolved' means the rule no longer fires on the new data; it does not by itself confirm the issue was fixed.")
    for title, items in (("New", cmp["new"]), ("Resolved", cmp["resolved"])):
        if items:
            st.markdown(f"**{title}**")
            for it in items:
                st.markdown(f"- {c.severity_pill(it['severity'])} {c.esc(it['title'])}", unsafe_allow_html=True)
    if cmp["changed"]:
        st.markdown("**Changed**")
        c.table(pd.DataFrame(cmp["changed"]))
