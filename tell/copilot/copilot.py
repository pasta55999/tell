"""Rule-based Analyst Copilot.

Maps a natural-language question to one of a fixed set of analytical intents,
runs the corresponding parameterised query/calculation, and renders a concise
templated answer with evidence references. No free-form SQL is ever generated.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from tell.analysis import metrics
from tell.analysis.rules.advertising import channel_table
from tell.copilot.adapters import LanguageModelAdapter, NullAdapter
from tell.db import repository as repo

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})


@dataclass
class Answer:
    intent: str
    supported: bool
    text: str
    table: pd.DataFrame | None = None
    evidence: list[str] = field(default_factory=list)
    related_findings: list[str] = field(default_factory=list)
    engine: str = NullAdapter.name


INTENTS: dict[str, dict] = {
    "revenue_variance": {"patterns": [r"revenue.*(differ|variance|reconcil|match|overstat)", r"reported revenue", r"reconcil"],
                         "example": "Why did reported revenue differ from order-derived revenue?"},
    "refund_exposure": {"patterns": [r"(refund|return).*(product|sku|exposure|highest|worst)", r"(highest|worst).*(refund|return)"],
                        "example": "Which products have the highest refund exposure?"},
    "margin_decline": {"patterns": [r"margin"], "example": "What is driving the margin decline?"},
    "prioritise": {"patterns": [r"(investigate|look at|start|focus).*(first|priorit)", r"priorit", r"(top|most (material|important|serious)).*finding", r"what should i"],
                   "example": "Which findings should I investigate first?"},
    "evidence": {"patterns": [r"evidence", r"(support|prove|back).*(finding)"], "example": "What evidence supports finding REV-001:2025-07?"},
    "seller_questions": {"patterns": [r"question", r"ask the seller", r"ask .*seller"], "example": "What questions should I ask the seller?"},
    "advertising": {"patterns": [r"roas", r"advertis", r"ad spend", r"marketing"], "example": "What is the ROAS by channel?"},
    "concentration": {"patterns": [r"concentrat", r"depend", r"top (product|sku)s?", r"best.?sell"], "example": "How concentrated is revenue?"},
    "inventory": {"patterns": [r"inventory", r"stock", r"supplier"], "example": "Are there inventory discrepancies?"},
    "seasonality": {"patterns": [r"spike", r"season", r"white friday", r"peak"], "example": "Is the November spike suspicious?"},
    "month_detail": {"patterns": [r"(what happened|how was|how did|performance).*(in|for)\s+\w+", r"\b20\d\d-\d\d\b"], "example": "What happened in 2025-10?"},
    "performance": {"patterns": [r"perform", r"summary", r"overview", r"how is the business", r"net sales", r"total revenue", r"kpi"],
                    "example": "How is the business performing?"},
}


def supported_questions() -> list[str]:
    return [v["example"] for v in INTENTS.values()]


def classify(question: str, adapter: LanguageModelAdapter | None = None) -> str | None:
    q = question.lower().strip()
    # order matters: specific before generic
    order = ["evidence", "seller_questions", "prioritise", "revenue_variance", "refund_exposure", "margin_decline", "advertising",
             "concentration", "inventory", "seasonality", "month_detail", "performance"]
    for name in order:
        if any(re.search(p, q) for p in INTENTS[name]["patterns"]):
            return name
    if adapter is not None:
        guess = adapter.classify_intent(question, list(INTENTS))
        if guess in INTENTS:
            return guess
    return None


def _findings(conn: sqlite3.Connection, run_id: int | None) -> pd.DataFrame:
    return repo.findings_for_run(conn, run_id) if run_id else pd.DataFrame()


def _money(cur: str, v: float | None) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{cur} {v:,.0f}"


def ask(conn: sqlite3.Connection, brand_id: int, question: str, run_id: int | None = None, adapter: LanguageModelAdapter | None = None) -> Answer:
    adapter = adapter or NullAdapter()
    brand = repo.get_brand(conn, brand_id)
    cur = brand["reporting_currency"] if brand else "AED"
    intent = classify(question, adapter)
    if run_id is None:
        latest = repo.latest_run(conn, brand_id)
        run_id = int(latest["id"]) if latest else None
    if intent is None:
        return Answer("unsupported", False,
                      "I can only answer a fixed set of analytical questions computed from the database. Try one of: "
                      + "; ".join(f'"{q}"' for q in supported_questions()[:6]) + ".", engine=adapter.name)
    handler = globals()[f"_h_{intent}"]
    ans: Answer = handler(conn, brand_id, cur, question, run_id)
    ans.engine = adapter.name
    ans.text = adapter.rephrase(ans.text)
    return ans


# ----------------------------------------------------------------- handlers

def _h_revenue_variance(conn, brand_id, cur, question, run_id) -> Answer:
    fin = metrics.monthly_financials(conn, brand_id)
    if fin.empty or fin["reported_revenue"].notna().sum() == 0:
        return Answer("revenue_variance", True, "No seller-reported revenue is available, so a reconciliation cannot be performed.")
    f = _findings(conn, run_id)
    rev = f[f["rule_id"] == "REV-001"] if not f.empty else pd.DataFrame()
    tot_rep, tot_net = fin["reported_revenue"].sum(), fin.loc[fin["reported_revenue"].notna(), "net_sales"].sum()
    lines = [f"Across {int(fin['reported_revenue'].notna().sum())} reported months, the seller reports {_money(cur, tot_rep)} against "
             f"{_money(cur, tot_net)} of order-derived net sales (gross sales less refunds posted), a difference of {_money(cur, tot_rep - tot_net)} "
             f"({(tot_rep / tot_net - 1) * 100:+.1f}%)."]
    if rev.empty:
        lines.append("No month breaches the 2% variance threshold; the statements reconcile within tolerance.")
    else:
        lines.append(f"{len(rev)} month(s) breach the 2% threshold:")
        for _, r in rev.iterrows():
            m = json.loads(r["measured"])
            attr = f" - matches {m['attribution']}" if m.get("attribution") else " - no standard reconciling item explains it"
            lines.append(f"  - {r['subject']}: reported {_money(cur, m['reported_revenue'])} vs net sales {_money(cur, m['net_sales'])} ({m['variance_pct']:+.1f}%){attr}.")
        lines.append("Interpretation: a consistent match to refunds + cancellations indicates the seller's figure is gross of refunds and includes cancelled orders. This is a detected discrepancy, not a confirmed misstatement - request the revenue bridge.")
    table = fin[["period", "reported_revenue", "gross_sales", "refunds_posted", "net_sales", "revenue_variance", "revenue_variance_pct"]].round(2)
    return Answer("revenue_variance", True, "\n".join(lines), table,
                  evidence=[f"seller_statements {p}" for p in rev["subject"]] if not rev.empty else ["seller_statements (all months)"],
                  related_findings=rev["finding_key"].tolist() if not rev.empty else [])


def _h_refund_exposure(conn, brand_id, cur, question, run_id) -> Answer:
    prod = metrics.product_table(conn, brand_id)
    if prod.empty:
        return Answer("refund_exposure", True, "No sales data available.")
    portfolio = prod["refunded_units"].sum() / prod["units"].sum() * 100 if prod["units"].sum() else 0
    eligible = prod[prod["units"] >= 30].sort_values("return_rate_pct", ascending=False)
    top = eligible.head(5)
    lines = [f"Portfolio return rate is {portfolio:.1f}% of units sold. Highest return rates (products with at least 30 units sold):"]
    for _, r in top.iterrows():
        lines.append(f"  - {r['sku']} {r['name']}: {r['return_rate_pct']:.1f}% ({int(r['refunded_units'])}/{int(r['units'])} units), refunded value {_money(cur, r['refunded_amount'])}, {r['revenue_share_pct']:.1f}% of gross sales.")
    by_value = prod.sort_values("refunded_amount", ascending=False).head(3)
    lines.append("By refunded value: " + "; ".join(f"{r['sku']} {_money(cur, r['refunded_amount'])}" for _, r in by_value.iterrows()) + ".")
    f = _findings(conn, run_id)
    rel = f[f["rule_id"].isin(["REF-001", "REF-002", "REF-003"])]["finding_key"].tolist() if not f.empty else []
    return Answer("refund_exposure", True, "\n".join(lines),
                  top[["sku", "name", "units", "refunded_units", "return_rate_pct", "refunded_amount", "revenue_share_pct"]].round(2),
                  evidence=[f"refund_items for {s}" for s in top["sku"]], related_findings=rel)


def _h_margin_decline(conn, brand_id, cur, question, run_id) -> Answer:
    fin = metrics.monthly_financials(conn, brand_id)
    if fin.empty:
        return Answer("margin_decline", True, "No data.")
    f = _findings(conn, run_id)
    mar = f[f["rule_id"] == "MAR-001"] if not f.empty else pd.DataFrame()
    first, last = fin.head(len(fin) // 2), fin.tail(len(fin) // 2)
    gm = lambda d: (d["gross_sales"].sum() - d["cogs"].sum()) / d["gross_sales"].sum() * 100  # noqa: E731
    lines = [f"Gross margin was {gm(first):.1f}% in {first['period'].iloc[0]}..{first['period'].iloc[-1]} and {gm(last):.1f}% in {last['period'].iloc[0]}..{last['period'].iloc[-1]} "
             f"(gross profit = gross sales - order-line COGS; excludes freight, fulfilment and overheads)."]
    if mar.empty:
        lines.append("No margin-decline finding was raised in the selected run.")
    else:
        m = json.loads(mar.iloc[0]["measured"])
        lines.append(f"Drivers: average unit cost {m['avg_unit_cost_change_pct']:+.1f}% versus average selling price {m['avg_selling_price_change_pct']:+.1f}% - "
                     + ("cost inflation not passed on to customers." if m["avg_unit_cost_change_pct"] > abs(m["avg_selling_price_change_pct"]) else "lower realised prices."))
        if m.get("largest_cost_increases"):
            lines.append("Largest recorded unit-cost increases: " + "; ".join(f"{d['sku']} {d['change_pct']:+.1f}%" for d in m["largest_cost_increases"][:5]) + ".")
        lines.append(f"Estimated gross profit forgone in the later window: {_money(cur, mar.iloc[0]['estimated_impact'])}.")
    return Answer("margin_decline", True, "\n".join(lines), fin[["period", "gross_sales", "cogs", "gross_profit", "gross_margin_pct", "discount_rate_pct"]].round(2),
                  evidence=["order_items.unit_cost by month"], related_findings=mar["finding_key"].tolist() if not mar.empty else [])


def _h_prioritise(conn, brand_id, cur, question, run_id) -> Answer:
    f = _findings(conn, run_id)
    if f.empty:
        return Answer("prioritise", True, "No analysis run is available yet. Run the analysis first.")
    actionable = f[f["classification"] != "observation"].head(5)
    lines = ["Ranked by severity, then estimated impact:"]
    for i, (_, r) in enumerate(actionable.iterrows(), 1):
        lines.append(f"  {i}. [{r['severity']}] {r['title']} - impact {_money(cur, r['estimated_impact'])}; {r['evidence_count']} evidence rows. Next: {r['next_action']}")
    obs = f[f["classification"] == "observation"]
    if not obs.empty:
        lines.append(f"{len(obs)} observation(s) (e.g. seasonal spikes) are informational and not ranked as risks.")
    return Answer("prioritise", True, "\n".join(lines), actionable[["finding_key", "severity", "title", "estimated_impact", "evidence_count"]],
                  related_findings=actionable["finding_key"].tolist())


def _h_evidence(conn, brand_id, cur, question, run_id) -> Answer:
    f = _findings(conn, run_id)
    if f.empty:
        return Answer("evidence", True, "No analysis run available.")
    key_match = re.search(r"([A-Z]{2,3}-\d{3}(?::[\w\-.]+)?)", question.upper())
    sel = pd.DataFrame()
    if key_match:
        key = key_match.group(1)
        sel = f[f["finding_key"].str.upper() == key] if ":" in key else f[f["rule_id"] == key]
    if sel.empty:
        return Answer("evidence", True, "Specify a finding key, e.g. 'What evidence supports REV-001:2025-07?'. Available: " + ", ".join(f["finding_key"].tolist()))
    r = sel.iloc[0]
    ev = repo.evidence_for_finding(conn, int(r["id"]))
    lines = [f"{r['title']}", f"Method: {r['method']}", f"Evidence ({len(ev)} rows):"]
    for _, e in ev.head(12).iterrows():
        lines.append(f"  - [{e['source_table']}{(' #' + str(int(e['source_id']))) if pd.notna(e['source_id']) else ''}] {e['description']}" + (f" = {e['value']:,.2f}" if pd.notna(e["value"]) else ""))
    if len(ev) > 12:
        lines.append(f"  ... {len(ev) - 12} more rows in the Findings view.")
    return Answer("evidence", True, "\n".join(lines), ev[["source_table", "source_id", "source_ref", "description", "value"]],
                  evidence=[f"{e['source_table']}:{e['source_ref']}" for _, e in ev.iterrows()], related_findings=[r["finding_key"]])


def _h_seller_questions(conn, brand_id, cur, question, run_id) -> Answer:
    if not run_id:
        return Answer("seller_questions", True, "No analysis run available.")
    q = repo.questions_for_run(conn, run_id)
    if q.empty:
        return Answer("seller_questions", True, "No findings, so no seller questions were generated.")
    top = q[q["status"] != "resolved"].head(8)
    lines = [f"{len(q)} questions were generated from findings ({int((q['priority'] == 'high').sum())} high priority). Start with:"]
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(f"  {i}. ({r['priority']}) {r['question']}")
    return Answer("seller_questions", True, "\n".join(lines), top[["priority", "question", "requested_items", "status"]],
                  related_findings=[k for k in top["finding_key"].dropna().tolist()])


def _h_advertising(conn, brand_id, cur, question, run_id) -> Answer:
    ads = repo.monthly_ad_spend(conn, brand_id)
    if ads.empty:
        return Answer("advertising", True, "No advertising records are available.")
    ch = channel_table(ads)
    fin = metrics.monthly_financials(conn, brand_id)
    total = ch["spend"].sum()
    lines = [f"Total advertising spend {_money(cur, total)}, {total / fin['gross_sales'].sum() * 100:.1f}% of gross sales."]
    for _, r in ch.iterrows():
        roas = f"ROAS {r['roas']:.2f}x (platform-attributed)" if pd.notna(r["roas"]) else "ROAS not computable - no attributed revenue data"
        lines.append(f"  - {r['channel']}: {_money(cur, r['spend'])} ({r['spend'] / total * 100:.0f}%); {roas}.")
    lines.append("Tell does not infer attribution from aggregate sales, so blended ROAS is not reported.")
    f = _findings(conn, run_id)
    rel = f[f["rule_id"].str.startswith("ADV")] if not f.empty else pd.DataFrame()
    if not rel.empty:
        lines.append("Related findings: " + "; ".join(rel["title"].tolist()) + ".")
    return Answer("advertising", True, "\n".join(lines), ch[["channel", "spend", "attributed_revenue", "roas", "attribution_available"]].round(2),
                  evidence=["ad_spend (all months)"], related_findings=rel["finding_key"].tolist() if not rel.empty else [])


def _h_concentration(conn, brand_id, cur, question, run_id) -> Answer:
    prod = metrics.product_table(conn, brand_id)
    if prod.empty:
        return Answer("concentration", True, "No sales data.")
    cats = metrics.category_table(prod)
    top3 = prod.head(3)
    lines = [f"Top SKU {top3.iloc[0]['sku']} {top3.iloc[0]['name']} = {top3.iloc[0]['revenue_share_pct']:.1f}% of gross sales; top-3 = {top3['revenue_share_pct'].sum():.1f}%; top-10 = {prod.head(10)['revenue_share_pct'].sum():.1f}% of {len(prod)} SKUs.",
             "By category: " + "; ".join(f"{r['category']} {r['revenue_share_pct']:.1f}%" for _, r in cats.iterrows()) + "."]
    f = _findings(conn, run_id)
    rel = f[f["rule_id"].str.startswith("CON")] if not f.empty else pd.DataFrame()
    return Answer("concentration", True, "\n".join(lines), prod.head(10)[["sku", "name", "category", "gross_sales", "revenue_share_pct", "gross_margin_pct"]].round(2),
                  evidence=["order_items by product"], related_findings=rel["finding_key"].tolist() if not rel.empty else [])


def _h_inventory(conn, brand_id, cur, question, run_id) -> Answer:
    f = _findings(conn, run_id)
    inv = f[f["rule_id"].str.startswith("INV")] if not f.empty else pd.DataFrame()
    snaps = repo.inventory_snapshots(conn, brand_id)
    if snaps.empty:
        return Answer("inventory", True, "No inventory snapshots are available, so the roll-forward cannot be performed.")
    lines = [f"{snaps['product_id'].nunique()} SKUs with {snaps['snapshot_date'].nunique()} snapshot dates."]
    if inv.empty:
        lines.append("All month-end counts reconcile to receipts, sales and restocked returns within tolerance.")
    else:
        for _, r in inv.iterrows():
            lines.append(f"  - [{r['severity']}] {r['title']} - {r['summary']} Impact {_money(cur, r['estimated_impact'])}.")
    return Answer("inventory", True, "\n".join(lines), inv[["finding_key", "severity", "title", "estimated_impact"]] if not inv.empty else None,
                  related_findings=inv["finding_key"].tolist() if not inv.empty else [])


def _h_seasonality(conn, brand_id, cur, question, run_id) -> Answer:
    f = _findings(conn, run_id)
    sea = f[f["rule_id"] == "SEA-001"] if not f.empty else pd.DataFrame()
    if sea.empty:
        return Answer("seasonality", True, "No sales spike above the robust-z threshold was detected.")
    lines = []
    for _, r in sea.iterrows():
        m = json.loads(r["measured"])
        verdict = "consistent with seasonal demand (observation, not a risk)" if r["classification"] == "observation" else "NOT explained by normal demand signals - needs investigation"
        checks = ", ".join(f"{k.replace('_', ' ')}={'yes' if v else 'no' if v is False else 'n/a'}" for k, v in m["checks"].items())
        lines.append(f"{r['subject']}: gross sales {_money(cur, m['gross_sales'])} ({m['sales_growth_pct']:+.0f}% vs baseline), orders {m['orders_growth_pct']:+.0f}%, AOV {_money(cur, m['aov'])}, discounts {m['discount_rate_pct']:.1f}%, margin {m['gross_margin_pct']:.1f}%. Verdict: {verdict}. Checks: {checks}.")
    return Answer("seasonality", True, "\n".join(lines), sea[["finding_key", "severity", "classification", "title"]], related_findings=sea["finding_key"].tolist())


def _h_month_detail(conn, brand_id, cur, question, run_id) -> Answer:
    fin = metrics.monthly_financials(conn, brand_id)
    if fin.empty:
        return Answer("month_detail", True, "No data.")
    q = question.lower()
    m = re.search(r"\b(20\d\d)-(\d\d)\b", q)
    period = None
    if m:
        period = f"{m.group(1)}-{m.group(2)}"
    else:
        for name, num in MONTHS.items():
            if re.search(rf"\b{name}\b", q):
                yr = re.search(r"\b(20\d\d)\b", q)
                year = yr.group(1) if yr else fin["period"].iloc[-1][:4]
                period = f"{year}-{num:02d}"
                break
    if period is None or period not in set(fin["period"]):
        return Answer("month_detail", True, f"I could not identify a month in the data range {fin['period'].iloc[0]}..{fin['period'].iloc[-1]}. Ask e.g. 'What happened in {fin['period'].iloc[-1]}?'.")
    r = fin[fin["period"] == period].iloc[0]
    f = _findings(conn, run_id)
    rel = f[(f["period_start"] <= period) & (f["period_end"] >= period)] if not f.empty else pd.DataFrame()
    text = (f"{period}: {int(r['orders_completed'])} completed orders, gross sales {_money(cur, r['gross_sales'])}, refunds posted {_money(cur, r['refunds_posted'])}, net sales {_money(cur, r['net_sales'])}, "
            f"gross margin {r['gross_margin_pct']:.1f}%, discounts {r['discount_rate_pct']:.1f}% of GMS, ad spend {_money(cur, r['ad_spend'])} ({r['ad_pct_of_gross_sales']:.1f}% of gross sales)."
            + (f" Seller reported revenue {_money(cur, r['reported_revenue'])} ({r['revenue_variance_pct']:+.1f}% vs net sales)." if pd.notna(r["reported_revenue"]) else ""))
    if not rel.empty:
        text += "\nFindings touching this month: " + "; ".join(f"[{x['severity']}] {x['title']}" for _, x in rel.iterrows()) + "."
    return Answer("month_detail", True, text, fin[fin["period"] == period].T.reset_index().rename(columns={"index": "metric"}), related_findings=rel["finding_key"].tolist() if not rel.empty else [])


def _h_performance(conn, brand_id, cur, question, run_id) -> Answer:
    fin = metrics.monthly_financials(conn, brand_id)
    if fin.empty:
        return Answer("performance", True, "No orders have been imported.")
    t = metrics.period_totals(fin)
    h1, h2 = fin.head(len(fin) // 2), fin.tail(len(fin) // 2)
    growth = (h2["gross_sales"].sum() / h1["gross_sales"].sum() - 1) * 100 if h1["gross_sales"].sum() else 0
    text = (f"{t['period_start']}..{t['period_end']}: {t['orders_completed']:,} completed orders, gross sales {_money(cur, t['gross_sales'])}, net sales {_money(cur, t['net_sales'])} after {_money(cur, t['refunds_posted'])} refunds. "
            f"Gross margin {t['gross_margin_pct']:.1f}%, advertising {t['ad_pct_of_gross_sales']:.1f}% of gross sales, contribution proxy (gross profit - ads) {_money(cur, t['contribution_proxy'])}. "
            f"Second-half gross sales were {growth:+.0f}% versus the first half; gross margin moved from {(h1['gross_sales'].sum() - h1['cogs'].sum()) / h1['gross_sales'].sum() * 100:.1f}% to {(h2['gross_sales'].sum() - h2['cogs'].sum()) / h2['gross_sales'].sum() * 100:.1f}%. "
            "Contribution proxy excludes fulfilment, payroll, payment fees and overheads.")
    f = _findings(conn, run_id)
    if not f.empty:
        sev = f["severity"].value_counts().to_dict()
        text += f"\nOpen findings: " + ", ".join(f"{sev.get(s, 0)} {s}" for s in ["critical", "high", "medium", "low", "info"] if sev.get(s)) + "."
    return Answer("performance", True, text, fin[["period", "orders_completed", "gross_sales", "net_sales", "gross_margin_pct", "ad_spend"]].round(2))
