from __future__ import annotations

import html

import streamlit as st

from tell.analysis import metrics
from tell.analysis.engine import run_analysis
from tell.ui import charts, components as c, data, state


def render() -> None:
    brand = state.brand()
    if brand is None:
        c.page_header("Overview")
        c.empty_state("No brand yet", "Add a brand in Settings or reset the demo data to begin.")
        return
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    run = state.run()
    c.page_header(brand["name"], f"{brand['category'] or ''} · reporting currency {cur}" + (f" · {fin['period'].iloc[0]} to {fin['period'].iloc[-1]}" if not fin.empty else ""),
                  eyebrow="Acquisition diligence workspace")
    if brand["is_demo"]:
        c.note("Synthetic demo business. All figures are generated; nothing here describes a real company.")

    if fin.empty:
        if c.empty_state("No orders imported", "Import orders, refunds, advertising and statements in Settings, or reset the demo dataset.", "Go to Settings") and st.session_state.get("pages"):
            st.switch_page(st.session_state.pages["settings"])
        return

    t = metrics.period_totals(fin)
    h1, h2 = fin.head(len(fin) // 2), fin.tail(len(fin) // 2)
    growth = (h2["gross_sales"].sum() / h1["gross_sales"].sum() - 1) * 100 if h1["gross_sales"].sum() else None
    gm1 = (h1["gross_sales"].sum() - h1["cogs"].sum()) / h1["gross_sales"].sum() * 100 if h1["gross_sales"].sum() else None
    gm2 = (h2["gross_sales"].sum() - h2["cogs"].sum()) / h2["gross_sales"].sum() * 100 if h2["gross_sales"].sum() else None
    c.kpi_row([
        ("Net sales", c.money(t["net_sales"], cur), f"{t['months']} months · {t['orders_completed']:,} orders"),
        ("Gross margin", c.pct(t["gross_margin_pct"]), f"H2 vs H1 {gm2 - gm1:+.1f}pp" if gm1 is not None and gm2 is not None else None),
        ("Advertising", c.pct(t["ad_pct_of_gross_sales"]) + " of sales", c.money(t["ad_spend"], cur)),
        ("Contribution proxy", c.money(t["contribution_proxy"], cur), "gross profit less advertising"),
    ])
    st.write("")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("<h3>Net sales and gross margin</h3>", unsafe_allow_html=True)
        st.plotly_chart(charts.revenue_margin(fin, cur), width="stretch", config={"displayModeBar": False})
        if growth is not None:
            c.caption(f"Second-half gross sales {growth:+.0f}% versus first half. Net sales = gross sales less refunds posted in the month.")
    with right:
        st.markdown("<h3>Reconciliation status</h3>", unsafe_allow_html=True)
        rec = fin[fin["reported_revenue"].notna()]
        if rec.empty:
            c.caption("No seller statements imported; revenue reconciliation not available.")
        else:
            breaches = rec[rec["revenue_variance_pct"].abs() >= 2]
            var = float(rec["revenue_variance"].sum())
            c.kpi("Seller-reported vs supported", c.money(var, cur) if var >= 0 else "-" + c.money(-var, cur),
                  f"{len(breaches)} of {len(rec)} months breach the 2% threshold")
            if not breaches.empty:
                c.caption("Months: " + ", ".join(breaches["period"]) + ". Open Revenue Reconciliation for the bridge and the records.")
            else:
                c.caption("All reported months reconcile within tolerance.")
        cov, score, label = data.coverage_info(bid, h)
        c.kpi("Data coverage", f"{score}/100", label + ("" if score >= 95 else " · see Settings for gaps"))

    c.divider()
    st.markdown("<h3>What deserves attention</h3>", unsafe_allow_html=True)
    if run is None:
        if c.empty_state("No analysis run yet", "Run the analysis to reconcile the records and surface findings. Runs are stored and reproducible.", "Run analysis", key="ov_run"):
            with st.spinner("Analysing records..."):
                rid = run_analysis(state.conn(), bid)
            st.session_state.run_id = rid
            st.rerun()
        return
    f = data.findings(int(run["id"]))
    material = f[f["classification"] != "observation"]
    top = material.head(3)
    a, b = st.columns([3, 2], gap="large")
    with a:
        if top.empty:
            c.caption("No material findings in this run.")
        for _, row in top.iterrows():
            c.finding_row(row, cur)
        st.write("")
        if st.button("Open all findings", key="ov_findings") and st.session_state.get("pages"):
            st.switch_page(st.session_state.pages["findings"])
    with b:
        sev = f["severity"].value_counts()
        obs = int((f["classification"] == "observation").sum())
        rows = "".join(f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #E4E1D8">'
                       f'<span>{c.severity_pill(s)}</span><span style="font-weight:600">{int(sev.get(s, 0))}</span></div>'
                       for s in ["critical", "high", "medium", "low", "info"] if sev.get(s, 0))
        st.markdown(f'<div class="tell-panel"><div class="tell-eyebrow">Run {run["id"]} · {str(run["finished_at"])[:16].replace("T", " ")} UTC</div>{rows}'
                    f'<div class="tell-note" style="margin-top:8px">{len(material)} material findings · {obs} observations · data hash {html.escape(str(run["data_hash"]))}</div></div>',
                    unsafe_allow_html=True)
        st.write("")
        next_q = material.iloc[0] if not material.empty else None
        if next_q is not None:
            c.caption("Investigate next: " + str(next_q["next_action"]))
