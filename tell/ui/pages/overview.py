"""Acquisition command centre: identity, the intelligence brief, the financial story,
the signals to inspect first, and the investigation trail."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tell.analysis.brief import TAGS, build_brief
from tell.analysis.engine import run_analysis
from tell.analysis.rules.revenue import attribute_variance
from tell.db import repository as repo
from tell.ui import charts, components as c, data, state, theme

TAG_COLORS = {"coral": theme.CORAL, "amber": theme.AMBER, "violet": theme.VIOLET, "slate": theme.SLATE, "emerald": theme.EMERALD, "cobalt": theme.COBALT_DEEP}
BRIEF_ORDER = ["divergence", "concentration", "verify", "data", "clear", "next"]


def render() -> None:
    brand = state.brand()
    if brand is None:
        c.page_header("Overview")
        c.empty_state("No target business yet", "Create a deal in Deals or reset the demo data to begin.")
        return
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    conn = state.conn()
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    run = state.run()
    f = data.findings(int(run["id"])) if run is not None else pd.DataFrame()
    material = f[f["classification"] != "observation"] if not f.empty else pd.DataFrame()
    open_f = material[~material["status"].isin(["verified", "dismissed"])] if not material.empty else pd.DataFrame()
    qs = repo.questions_for_run(conn, int(run["id"])) if run is not None else pd.DataFrame()

    # ------------------------------------------------------------ identity
    left, right = st.columns([4, 2], gap="large")
    with left:
        facts = [("", brand["category"] or ""), ("", brand["location"] or ""), ("", cur),
                 ("", f"{fin['period'].iloc[0]} – {fin['period'].iloc[-1]}" if not fin.empty else "no orders")]
        c.identity(brand["name"], facts)
    with right:
        with st.container(horizontal=True, horizontal_alignment="right"):
            if st.button("Data room", key="ov_import"):
                state.go("data_room")
            if st.button("Run analysis", type="primary", key="ov_run"):
                with st.spinner("Reconciling records and running rules..."):
                    st.session_state.run_id = run_analysis(conn, bid)
                st.rerun()

    if fin.empty:
        st.write("")
        if c.empty_state("No records yet", "Import orders, refunds, statements and advertising in the Data room to build the financial picture.", "Open data room", key="ov_dr"):
            state.go("data_room")
        return
    if run is None:
        st.write("")
        if c.empty_state("Records loaded, analysis not run", "Run the analysis to reconcile the seller's statements against the ledger and surface findings.", "Run analysis now", key="ov_run2"):
            with st.spinner("Analysing records..."):
                st.session_state.run_id = run_analysis(conn, bid)
            st.rerun()
        return

    reviewed = int(material["status"].isin(["verified", "dismissed", "needs_investigation"]).sum()) if not material.empty else 0
    answered = int((qs["status"] != "pending").sum()) if not qs.empty else 0
    has_report = bool(repo.scalar(conn, "SELECT COUNT(*) FROM reports WHERE run_id=?", (int(run["id"]),)))
    c.stepper([("Import", "done", None), ("Analyse", "done", None),
               ("Investigate", "done" if material.empty or reviewed == len(material) else "active", f"{reviewed}/{len(material)}"),
               ("Question seller", "done" if not qs.empty and answered == len(qs) else "partial" if answered else "todo", f"{answered}/{len(qs)}" if not qs.empty else None),
               ("Report", "done" if has_report else "todo", None)])

    # ------------------------------------------------------------ brief + glance
    br = build_brief(conn, bid, int(run["id"]))
    st.write("")
    bl, bres = st.columns([3, 2], gap="large")
    with bl:
        ranked = sorted(br["items"], key=lambda i: BRIEF_ORDER.index(i["kind"]))
        keep = [i for i in ranked if i["kind"] != "clear"][:5] + [i for i in ranked if i["kind"] == "clear"][:1]
        items = [{"tag": TAGS[i["kind"]][0], "tag_color": TAG_COLORS[TAGS[i["kind"]][1]], "text": i["text"], "ref": i["ref"]} for i in keep]
        c.brief("Investment intelligence brief", br["lede"], items)
        if len(br["items"]) > len(keep):
            c.note(f"{len(br['items']) - len(keep)} further points appear in the report.")
    with bres:
        rec = fin[fin["reported_revenue"].notna()]
        reported = float(rec["reported_revenue"].sum()) if not rec.empty else None
        net = float(rec["net_sales"].sum()) if not rec.empty else float(fin["net_sales"].sum())
        gap = (reported - net) if reported is not None else None
        st.markdown('<div class="tell-eyebrow muted">At a glance</div>', unsafe_allow_html=True)
        c.hero([("Seller says", c.money(reported, cur) if reported is not None else "no statements", f"{len(rec)} months reported", theme.VIOLET)])
        c.hero([("Records support", c.money(net, cur), "net sales after refunds", theme.EMERALD)])
        c.hero([("Gap", c.signed_money(gap, cur) if gap is not None else "—", f"{gap / net * 100:+.1f}% of supported" if gap is not None and net else "", theme.CORAL if gap and abs(gap / net) >= 0.02 else theme.INK)])
        st.write("")
        st.markdown('<div class="tell-eyebrow muted">Where to look first</div>', unsafe_allow_html=True)
        top = open_f.head(3) if not open_f.empty else material.head(3)
        if top.empty:
            c.panel("Nothing open", "All material findings are verified or dismissed.", "emerald")
        for _, row in top.iterrows():
            c.signal(row, cur, compact=True)
        if st.button("All findings", key="ov_findings"):
            state.go("findings")

    # ------------------------------------------------------------ the financial picture
    c.divider()
    c.section("The financial picture", "From the seller's headline to supported net sales")
    rec = fin[fin["reported_revenue"].notna()]
    main, side = st.columns([3, 2], gap="large")
    with main:
        if rec.empty:
            c.panel("No seller statements", "Import management accounts in the Data room to reconcile headline revenue.", "tint")
        else:
            st.plotly_chart(charts.annual_bridge(fin, cur, attribute_variance), width="stretch", config={"displayModeBar": False})
    with side:
        if not rec.empty:
            breaches = rec[rec["revenue_variance_pct"].abs() >= 2]
            if not breaches.empty:
                st.markdown('<div class="tell-eyebrow muted">Months that diverge</div>', unsafe_allow_html=True)
                c.ledger([(r["period"], c.signed_money(r["revenue_variance"], cur), f"{r['revenue_variance_pct']:+.1f}%", True) for _, r in breaches.iterrows()],
                         ("Combined", c.signed_money(float(breaches["revenue_variance"].sum()), cur)))
            else:
                c.insight("Every reported month reconciles within tolerance.", "emerald")
            st.write("")
        if st.button("Financial story", key="ov_fs"):
            state.go("financial_story")

    # ------------------------------------------------------------ investigation trail
    c.divider()
    c.section("Investigation trail")
    t1, t2 = st.columns([2, 3], gap="large")
    with t1:
        events = []
        for r in repo.list_runs(conn, bid)[:3]:
            events.append((str(r["finished_at"] or r["started_at"])[:16].replace("T", " "), f"Run {r['id']} · {int(r['finding_count'])} findings" + (f" · {c.esc(r['label'])}" if r["label"] else ""), theme.EMERALD))
        for _, e in repo.recent_events(conn, bid, 4).iterrows():
            events.append((str(e["created_at"])[:16], f"{c.esc(e['kind'].capitalize())} marked <b>{c.esc(e['to_status'].replace('_', ' '))}</b> — {c.esc(str(e['subject'])[:70])}", theme.COBALT))
        events.sort(key=lambda x: x[0], reverse=True)
        c.timeline(events[:6])
    with t2:
        st.markdown('<div class="tell-eyebrow muted">Still to verify</div>', unsafe_allow_html=True)
        pending = qs[qs["status"] == "pending"].head(3) if not qs.empty else pd.DataFrame()
        if pending.empty:
            c.caption("No pending seller questions.")
        for _, q in pending.iterrows():
            st.markdown(c.list_item(q["priority"], q["question"], None, theme.PRIORITY_COLORS[q["priority"]][0]), unsafe_allow_html=True)
        if not qs.empty:
            if st.button(f"{int((qs['status'] == 'pending').sum())} open questions", key="ov_q"):
                state.go("questions")
    if brand["is_demo"]:
        st.write("")
        c.note("Synthetic demo business. Nothing here describes a real company.")
