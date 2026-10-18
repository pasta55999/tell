from __future__ import annotations

import json

import streamlit as st

from tell.db import repository as repo
from tell.reports import build_report, findings_csv, questions_csv, reconciliation_csv, report_json, report_pdf, save_report
from tell.ui import components as c, state


def render() -> None:
    brand = state.brand()
    run = state.run()
    cur = brand["reporting_currency"]
    c.page_header("Reports", "A structured acquisition diligence report built from the selected analysis run.", eyebrow=brand["name"])
    if run is None:
        c.empty_state("No analysis run yet", "Run the analysis first; reports always reflect a stored run.")
        return
    conn = state.conn()
    versions = repo.fetch_df(conn, "SELECT id, version, title, created_at FROM reports WHERE run_id = ? ORDER BY version DESC", (int(run["id"]),))
    a, b = st.columns([3, 2])
    with a:
        c.caption(f"Run {run['id']} · finished {str(run['finished_at'])[:16].replace('T', ' ')} UTC · data hash {run['data_hash']} · {run['finding_count']} findings. "
                  f"{len(versions)} saved version(s) for this run.")
    with b:
        if st.button("Generate report version", type="primary"):
            content = build_report(conn, int(run["id"]))
            v = save_report(conn, int(run["id"]), content)
            st.success(f"Saved report v{v}.")
            st.rerun()
    if versions.empty:
        content = build_report(conn, int(run["id"]))
        label = "Preview (unsaved)"
    else:
        choice = st.selectbox("Version", versions["id"].tolist(), format_func=lambda i: f"v{int(versions.set_index('id').loc[i, 'version'])} · {versions.set_index('id').loc[i, 'created_at']}", label_visibility="collapsed")
        content = json.loads(repo.scalar(conn, "SELECT content_json FROM reports WHERE id = ?", (int(choice),)))
        label = f"v{int(versions.set_index('id').loc[choice, 'version'])}"

    st.write("")
    d1, d2, d3, d4, d5 = st.columns(5)
    base = f"{brand['slug']}-diligence-run{run['id']}-{label.split(' ')[0]}"
    with d1:
        st.download_button("PDF", report_pdf(content), file_name=f"{base}.pdf", mime="application/pdf", width="stretch")
    with d2:
        st.download_button("JSON", report_json(content), file_name=f"{base}.json", mime="application/json", width="stretch")
    with d3:
        st.download_button("Findings CSV", findings_csv(content), file_name=f"{base}-findings.csv", mime="text/csv", width="stretch")
    with d4:
        st.download_button("Questions CSV", questions_csv(content), file_name=f"{base}-questions.csv", mime="text/csv", width="stretch")
    with d5:
        st.download_button("Reconciliation CSV", reconciliation_csv(content), file_name=f"{base}-reconciliation.csv", mime="text/csv", width="stretch")

    c.divider()
    es = content["executive_summary"]
    st.markdown("<h2>Executive summary</h2>", unsafe_allow_html=True)
    st.markdown(f"**{es['headline']}**")
    for bullet in es["bullets"]:
        st.markdown(f"- {bullet}")
    c.note(content["meta"]["disclaimer"])

    t = content["performance"]["totals"]
    if t:
        st.markdown("<h2>Business performance</h2>", unsafe_allow_html=True)
        c.kpi_row([("Gross sales", c.money(t["gross_sales"], cur), None), ("Net sales", c.money(t["net_sales"], cur), None),
                   ("Gross margin", c.pct(t["gross_margin_pct"]), None), ("Contribution proxy", c.money(t["contribution_proxy"], cur), "GP less advertising")])
    rec = content["reconciliation"]
    st.markdown("<h2>Reconciliation</h2>", unsafe_allow_html=True)
    if rec["monthly"]:
        st.markdown(f"{rec['months_reported']} months reported; {rec['months_breaching_threshold']} breach the 2% threshold. Reported {c.money(rec['reported_revenue_total'], cur)} vs supported {c.money(rec['net_sales_total'], cur)}.")
    else:
        st.markdown("No seller-reported revenue available.")

    st.markdown("<h2>Material findings</h2>", unsafe_allow_html=True)
    for f in [x for x in content["findings"] if x["classification"] != "observation"]:
        st.markdown(f"{c.severity_pill(f['severity'])} **{f['title']}**", unsafe_allow_html=True)
        st.markdown(f["explanation"])
        c.note(f"{f['finding_key']} · impact {c.money(f['estimated_impact'], cur) if f['estimated_impact'] is not None else 'not quantified'} · {len(f['evidence'])} evidence rows · status {f['status']}")
        st.write("")
    obs = [x for x in content["findings"] if x["classification"] == "observation"]
    if obs:
        st.markdown("**Observations (informational)**")
        for f in obs:
            st.markdown(f"- {f['title']}: {f['summary']}")

    st.markdown("<h2>Open questions for the seller</h2>", unsafe_allow_html=True)
    for q in [x for x in content["questions"] if x.get("status") != "resolved"][:15]:
        st.markdown(f"- **({q['priority']})** {q['question']}")

    st.markdown("<h2>Data limitations</h2>", unsafe_allow_html=True)
    lim = content["data_limitations"]
    st.markdown(f"Data coverage {lim['coverage_score']}/100 ({lim['coverage_label']}).")
    for s in lim["skipped_analyses"] + lim["general"]:
        st.markdown(f"- {s}")
    st.markdown("<h2>Recommended next steps</h2>", unsafe_allow_html=True)
    for i, s in enumerate(content["next_steps"], 1):
        st.markdown(f"{i}. {s}")
