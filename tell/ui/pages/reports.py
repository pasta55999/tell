"""Reports: an investment-ready diligence document composed from a stored run, with versioning
and PDF / JSON / CSV exports."""

from __future__ import annotations

import json

import streamlit as st

from tell.analysis.brief import TAGS, build_brief
from tell.db import repository as repo
from tell.reports import build_report, findings_csv, questions_csv, reconciliation_csv, report_json, report_pdf, save_report
from tell.ui import charts, components as c, data, state, theme
from tell.analysis.rules.revenue import attribute_variance

TAG_COLORS = {"coral": theme.CORAL, "amber": theme.AMBER, "violet": theme.VIOLET, "slate": theme.SLATE, "emerald": theme.EMERALD, "cobalt": theme.COBALT_DEEP}


def render() -> None:
    brand = state.brand()
    run = state.run()
    cur = brand["reporting_currency"]
    bid = int(brand["id"])
    conn = state.conn()
    c.page_header("Reports", eyebrow=brand["name"])
    if run is None:
        c.empty_state("No analysis run yet", "Run the analysis first; reports always reflect a stored run.")
        return
    versions = repo.fetch_df(conn, "SELECT id, version, title, created_at FROM reports WHERE run_id = ? ORDER BY version DESC", (int(run["id"]),))
    top_l, top_r = st.columns([3, 2], gap="large")
    with top_l:
        c.caption(f"Built from run {run['id']} (finished {str(run['finished_at'])[:16].replace('T', ' ')} UTC, data hash {run['data_hash']}, {run['finding_count']} findings). "
                  f"{len(versions)} saved version(s). Generating a version freezes the content so later status changes do not alter what was circulated.")
    with top_r:
        with st.container(horizontal=True, horizontal_alignment="right"):
            if not versions.empty:
                vmap = versions.set_index("id")
                choice = st.selectbox("Version", versions["id"].tolist(), format_func=lambda i: f"v{int(vmap.loc[i, 'version'])} · {vmap.loc[i, 'created_at']}", label_visibility="collapsed")
                content = json.loads(repo.scalar(conn, "SELECT content_json FROM reports WHERE id = ?", (int(choice),)))
                label = f"v{int(vmap.loc[choice, 'version'])}"
            else:
                content, label = build_report(conn, int(run["id"])), "preview"
            if st.button("Generate version", type="primary", icon=":material/save:"):
                v = save_report(conn, int(run["id"]), build_report(conn, int(run["id"])))
                st.toast(f"Saved report v{v}.")
                st.rerun()
    base = f"{brand['slug']}-diligence-run{run['id']}-{label}"
    with st.container(horizontal=True):
        st.download_button("PDF", report_pdf(content), file_name=f"{base}.pdf", mime="application/pdf", icon=":material/picture_as_pdf:")
        st.download_button("JSON", report_json(content), file_name=f"{base}.json", mime="application/json")
        st.download_button("Findings CSV", findings_csv(content), file_name=f"{base}-findings.csv", mime="text/csv")
        st.download_button("Questions CSV", questions_csv(content), file_name=f"{base}-questions.csv", mime="text/csv")
        st.download_button("Reconciliation CSV", reconciliation_csv(content), file_name=f"{base}-reconciliation.csv", mime="text/csv")
    if label == "preview":
        c.note("Unsaved preview — generate a version to freeze it.")

    # ------------------------------------------------------------ document
    c.divider()
    doc, margin = st.columns([5, 2], gap="large")
    with doc:
        meta = content["meta"]
        st.markdown(f'<div class="tell-doc"><div class="masthead"><div class="tell-eyebrow">Acquisition diligence report · {c.esc(label)}</div><div class="t">{c.esc(meta["brand"])}</div>'
                    f'<div class="s">{c.esc(brand["category"] or "")} · {c.esc(brand["location"] or "")} · {cur} · generated {meta["generated_at"][:16].replace("T", " ")} UTC · run {meta["run_id"]} · data {meta["data_hash"]}</div></div></div>', unsafe_allow_html=True)

        br = build_brief(conn, bid, int(run["id"]))
        st.markdown('<div class="tell-doc"><h2><span class="num">1</span>Executive diligence brief</h2></div>', unsafe_allow_html=True)
        c.brief("", br["lede"], [{"tag": TAGS[i["kind"]][0], "tag_color": TAG_COLORS[TAGS[i["kind"]][1]], "text": i["text"], "ref": i["ref"]} for i in br["items"]])
        c.note(meta["disclaimer"])

        t = content["performance"]["totals"]
        rec = content["reconciliation"]
        st.markdown('<div class="tell-doc"><h2><span class="num">2</span>Financial reconciliation</h2></div>', unsafe_allow_html=True)
        if rec["monthly"]:
            fin = data.financials(bid, data.data_hash(bid))
            st.plotly_chart(charts.annual_bridge(fin, cur, attribute_variance), width="stretch", config={"displayModeBar": False})
            st.markdown(f"{rec['months_reported']} months reported; **{rec['months_breaching_threshold']}** breach the 2% threshold. Seller-reported {c.money(rec['reported_revenue_total'], cur)} against {c.money(rec['net_sales_total'], cur)} supported by the ledger (variance {c.signed_money(rec['variance_total'], cur)}).")
            bad = [m for m in rec["monthly"] if abs(m["revenue_variance_pct"] or 0) >= 2]
            if bad:
                c.ledger([(m["period"], c.signed_money(m["revenue_variance"], cur), f"reported {c.money(m['reported_revenue'], cur)} · supported {c.money(m['net_sales'], cur)}", True) for m in bad])
        else:
            st.markdown("No seller-reported revenue available; reconciliation not performed.")
        if t:
            c.hero([("Gross sales", c.money(t["gross_sales"], cur), None), ("Net sales", c.money(t["net_sales"], cur), None), ("Gross margin", c.pct(t["gross_margin_pct"]), None),
                    ("Contribution proxy", c.money(t["contribution_proxy"], cur), "GP less advertising; not EBITDA")], small=True)

        st.markdown('<div class="tell-doc"><h2><span class="num">3</span>Material findings, ranked</h2></div>', unsafe_allow_html=True)
        for i, f in enumerate([x for x in content["findings"] if x["classification"] != "observation"], 1):
            st.markdown(f'<div class="tell-signal" style="--sig-color:{theme.SEVERITY_BAR.get(f["severity"], theme.LINE_STRONG)}"><div class="bar"></div><div><div class="t">{i}. {c.esc(f["title"])}</div>'
                        f'<div class="m">{c.severity_pill(f["severity"])}{c.class_pill(f["classification"])}{c.esc(f["explanation"])}</div>'
                        f'<div class="tell-note" style="margin-top:4px">{f["finding_key"]} · {len(f["evidence"])} evidence rows · status {f["status"]}' + (f' · impact basis: {c.esc(f["impact_basis"])}' if f["impact_basis"] else "") + '</div></div>'
                        f'<div class="impact">{c.esc(c.money(f["estimated_impact"], cur) if f["estimated_impact"] is not None else "—")}<small>{"est. impact" if f["estimated_impact"] is not None else "not quantified"}</small></div></div>', unsafe_allow_html=True)

        st.markdown('<div class="tell-doc"><h2><span class="num">4</span>Product and operational risks</h2></div>', unsafe_allow_html=True)
        ops = [x for x in content["findings"] if x["category"] in ("Concentration", "Refunds & returns", "Inventory", "Pricing & promotions", "Advertising")]
        tp = content["performance"]["top_products"]
        if tp:
            c.ledger([(f"{p['sku']} {p['name']}", f"{p['revenue_share_pct']:.1f}%", f"GM {p['gross_margin_pct']:.1f}% · returns {p['return_rate_pct']:.1f}%", p["revenue_share_pct"] >= 25 or (p["return_rate_pct"] or 0) >= 10) for p in tp[:6]],
                     ("Top-3 share of gross sales", f"{sum(p['revenue_share_pct'] for p in tp[:3]):.1f}%"))
        for f in ops:
            st.markdown(f"- {c.severity_pill(f['severity'])} **{c.esc(f['title'])}** — {c.esc(f['summary'])}", unsafe_allow_html=True)
        obs = [x for x in content["findings"] if x["classification"] == "observation"]
        if obs:
            c.note("Observations (informational, not risks): " + "; ".join(f"{o['title']}" for o in obs))

        st.markdown('<div class="tell-doc"><h2><span class="num">5</span>Evidence and methodology</h2></div>', unsafe_allow_html=True)
        c.caption("Every finding above is produced by a versioned rule against the imported records and carries evidence rows naming the source table and record. Definitions:")
        for k, v in content["methodology"]["definitions"].items():
            st.markdown(f"- **{k}.** {v}")

        st.markdown('<div class="tell-doc"><h2><span class="num">6</span>Questions requiring seller clarification</h2></div>', unsafe_allow_html=True)
        for q in [x for x in content["questions"] if x.get("status") != "resolved"][:15]:
            st.markdown(f"{c.priority_pill(q['priority'])} {c.esc(q['question'])}" + (f' <span class="tell-note">{c.esc(q["finding_key"])}</span>' if q.get("finding_key") else ""), unsafe_allow_html=True)

        st.markdown('<div class="tell-doc"><h2><span class="num">7</span>Limitations and unresolved data gaps</h2></div>', unsafe_allow_html=True)
        lim = content["data_limitations"]
        st.markdown(f"Data coverage **{lim['coverage_score']}/100** ({lim['coverage_label']}).")
        for s in lim["skipped_analyses"] + lim["general"]:
            st.markdown(f"- {s}")
        st.markdown("**Recommended next steps**")
        for i, s in enumerate(content["next_steps"], 1):
            st.markdown(f"{i}. {s}")
    with margin:
        st.markdown('<div class="tell-eyebrow muted">In this report</div>', unsafe_allow_html=True)
        sev = content["severity_counts"]
        c.ledger([("Material findings", str(sum(1 for x in content["findings"] if x["classification"] != "observation")), None),
                  ("High / critical", str(sev.get("high", 0) + sev.get("critical", 0)), None, bool(sev.get("high") or sev.get("critical"))),
                  ("Open seller questions", str(sum(1 for x in content["questions"] if x.get("status") != "resolved")), None),
                  ("Evidence rows", str(sum(len(x["evidence"]) for x in content["findings"])), None),
                  ("Rules applied", f"{len(content['meta']['rule_versions'])} · engine {content['meta']['engine_version']}", None)])
        st.write("")
        c.insight("Findings are stated as detected discrepancies or suspected risks. Nothing in this document is a confirmed fact until verified with the seller's records.", "cobalt")
