from __future__ import annotations

import json

import streamlit as st

from tell.db import repository as repo
from tell.reports import build_report, findings_csv, questions_csv, reconciliation_csv, report_json, report_pdf, save_report
from tell.ui import components as c, state, theme


def render() -> None:
    brand = state.brand()
    run = state.run()
    cur = brand["reporting_currency"]
    c.page_header("Reports", "A structured acquisition diligence report built from the selected analysis run. Versions are stored; exports are generated from the stored content.", eyebrow=brand["name"])
    if run is None:
        c.empty_state("No analysis run yet", "Run the analysis first; reports always reflect a stored run.")
        return
    conn = state.conn()
    versions = repo.fetch_df(conn, "SELECT id, version, title, created_at FROM reports WHERE run_id = ? ORDER BY version DESC", (int(run["id"]),))
    a, b, d = st.columns([3, 2, 2], gap="large")
    with a:
        c.caption(f"Run {run['id']} · finished {str(run['finished_at'])[:16].replace('T', ' ')} UTC · data hash {run['data_hash']} · {run['finding_count']} findings · {len(versions)} saved version(s).")
    with b:
        if versions.empty:
            content = build_report(conn, int(run["id"]))
            label = "preview"
            c.note("Unsaved preview — generate a version to freeze it.")
        else:
            vmap = versions.set_index("id")
            choice = st.selectbox("Version", versions["id"].tolist(), format_func=lambda i: f"v{int(vmap.loc[i, 'version'])} · {vmap.loc[i, 'created_at']}", label_visibility="collapsed")
            content = json.loads(repo.scalar(conn, "SELECT content_json FROM reports WHERE id = ?", (int(choice),)))
            label = f"v{int(vmap.loc[choice, 'version'])}"
    with d:
        if st.button("Generate report version", type="primary", width="stretch"):
            v = save_report(conn, int(run["id"]), build_report(conn, int(run["id"])))
            st.success(f"Saved report v{v}.")
            st.rerun()

    base = f"{brand['slug']}-diligence-run{run['id']}-{label}"
    c.section("Export", "PDF for circulation; JSON for systems; CSV extracts for working papers")
    d1, d2, d3, d4, d5 = st.columns(5)
    with d1:
        st.download_button("PDF report", report_pdf(content), file_name=f"{base}.pdf", mime="application/pdf", width="stretch", type="primary")
    with d2:
        st.download_button("JSON", report_json(content), file_name=f"{base}.json", mime="application/json", width="stretch")
    with d3:
        st.download_button("Findings CSV", findings_csv(content), file_name=f"{base}-findings.csv", mime="text/csv", width="stretch")
    with d4:
        st.download_button("Questions CSV", questions_csv(content), file_name=f"{base}-questions.csv", mime="text/csv", width="stretch")
    with d5:
        st.download_button("Reconciliation CSV", reconciliation_csv(content), file_name=f"{base}-reconciliation.csv", mime="text/csv", width="stretch")

    # ---- preview, styled like a document
    es = content["executive_summary"]
    c.divider()
    st.markdown(f'<div class="tell-eyebrow">Acquisition diligence report · {label}</div><h2 style="margin-top:0 !important">{c.esc(content["meta"]["brand"])}</h2>'
                f'<div class="tell-note">Generated {content["meta"]["generated_at"][:16].replace("T", " ")} UTC · run {content["meta"]["run_id"]} · data {content["meta"]["data_hash"]} · engine {content["meta"]["engine_version"]}</div>', unsafe_allow_html=True)
    c.section("1. Executive summary")
    c.insight(es["headline"], "coral" if content["severity_counts"].get("high") or content["severity_counts"].get("critical") else "cobalt")
    for bullet in es["bullets"]:
        st.markdown(f"- {bullet}")
    c.note(content["meta"]["disclaimer"])

    t = content["performance"]["totals"]
    if t:
        c.section("2. Business performance")
        c.kpi_row([("Gross sales", c.money(t["gross_sales"], cur), None, theme.COBALT), ("Net sales", c.money(t["net_sales"], cur), None, theme.EMERALD),
                   ("Gross margin", c.pct(t["gross_margin_pct"]), None, theme.VIOLET), ("Contribution proxy", c.money(t["contribution_proxy"], cur), c.delta_text("GP less advertising; not EBITDA", "neutral"), theme.SLATE)], plain=True)
    rec = content["reconciliation"]
    c.section("3. Reconciliation")
    if rec["monthly"]:
        st.markdown(f"{rec['months_reported']} months reported; **{rec['months_breaching_threshold']}** breach the 2% threshold. Reported {c.money(rec['reported_revenue_total'], cur)} vs supported {c.money(rec['net_sales_total'], cur)} (variance {c.signed_money(rec['variance_total'], cur)}).")
    else:
        st.markdown("No seller-reported revenue available.")

    c.section("4. Material findings")
    for f in [x for x in content["findings"] if x["classification"] != "observation"]:
        st.markdown(f"{c.severity_pill(f['severity'])}{c.class_pill(f['classification'])} **{c.esc(f['title'])}**", unsafe_allow_html=True)
        st.markdown(f["explanation"])
        c.note(f"{f['finding_key']} · impact {c.money(f['estimated_impact'], cur) if f['estimated_impact'] is not None else 'not quantified'} · {len(f['evidence'])} evidence rows · status {f['status']}")
        st.write("")
    obs = [x for x in content["findings"] if x["classification"] == "observation"]
    if obs:
        st.markdown("**Observations (informational)**")
        for f in obs:
            st.markdown(f"- {f['title']}: {f['summary']}")

    c.section("5. Open questions for the seller")
    for q in [x for x in content["questions"] if x.get("status") != "resolved"][:15]:
        st.markdown(f"{c.priority_pill(q['priority'])} {c.esc(q['question'])}", unsafe_allow_html=True)

    c.section("6. Data limitations")
    lim = content["data_limitations"]
    st.markdown(f"Data coverage **{lim['coverage_score']}/100** ({lim['coverage_label']}).")
    for s in lim["skipped_analyses"] + lim["general"]:
        st.markdown(f"- {s}")
    c.section("7. Recommended next steps")
    for i, s in enumerate(content["next_steps"], 1):
        st.markdown(f"{i}. {s}")
