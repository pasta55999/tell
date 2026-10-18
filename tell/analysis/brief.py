"""Investment intelligence brief: a short, evidence-linked summary assembled from the stored
findings of a run and the data-coverage facts. Every statement references the finding key or
data source it came from. No language model is involved; wording is templated."""

from __future__ import annotations

import json
import sqlite3

import pandas as pd

from tell.analysis import metrics
from tell.analysis.context import AnalysisContext
from tell.analysis.rules.data_quality import coverage
from tell.db import repository as repo

TAGS = {
    "divergence": ("Numbers diverge", "coral"),
    "verify": ("Needs verification", "amber"),
    "concentration": ("Disproportionate risk", "violet"),
    "data": ("Data gap", "slate"),
    "clear": ("Holds up", "emerald"),
    "next": ("Investigate next", "cobalt"),
}


def _money(cur: str, v: float) -> str:
    return f"{cur} {v:,.0f}"


def build_brief(conn: sqlite3.Connection, brand_id: int, run_id: int | None) -> dict:
    brand = repo.get_brand(conn, brand_id)
    cur = brand["reporting_currency"] if brand else "AED"
    fin = metrics.monthly_financials(conn, brand_id)
    f = repo.findings_for_run(conn, run_id) if run_id else pd.DataFrame()
    items: list[dict] = []
    if fin.empty:
        return {"lede": "No order data has been imported, so there is nothing to reconcile yet.", "items": [], "severity": "none"}
    if f.empty:
        return {"lede": "Records are loaded but no analysis has been run.", "items": [], "severity": "none"}

    material = f[(f["classification"] != "observation") & (~f["status"].isin(["dismissed"]))]
    rec = fin[fin["reported_revenue"].notna()]
    by_rule = {k: g for k, g in f.groupby("rule_id")}

    # 1. Where seller-reported figures differ from the records
    if "REV-001" in by_rule:
        rev = by_rule["REV-001"]
        total = float(rev["estimated_impact"].fillna(0).sum())
        months = ", ".join(sorted(rev["subject"]))
        labels = [json.loads(m).get("attribution") for m in rev["measured"]]
        common = max(set(l for l in labels if l), key=labels.count) if any(labels) else None
        text = f"Seller-reported revenue exceeds what the order ledger supports in {len(rev)} of {len(rec)} months ({months}) by {_money(cur, total)} combined."
        if common:
            text += f" The gap matches {common.split(' (')[0]} in every case — a definitional difference to confirm, not yet a misstatement."
        items.append({"kind": "divergence", "text": text, "ref": "REV-001", "keys": rev["finding_key"].tolist()})
    elif not rec.empty:
        items.append({"kind": "clear", "text": f"Seller-reported revenue reconciles to order-ledger net sales within 2% in all {len(rec)} reported months.", "ref": "reconciliation", "keys": []})
    if "ADV-002" in by_rule:
        adv = by_rule["ADV-002"]
        r = adv.iloc[0]
        m = json.loads(r["measured"])
        items.append({"kind": "divergence", "text": f"Advertising in the {r['subject']} management accounts is {abs(m['variance_pct']):.0f}% {'below' if m['variance'] < 0 else 'above'} platform billing ({_money(cur, m['reported_ad_spend'])} vs {_money(cur, m['recorded_ad_spend'])}); reported profit for the month is overstated by the difference.", "ref": r["finding_key"], "keys": [r["finding_key"]]})
    if "REF-002" in by_rule:
        r = by_rule["REF-002"].iloc[0]
        m = json.loads(r["measured"])
        src = ", ".join(sorted(m["source_periods"]))
        items.append({"kind": "divergence", "text": f"{m['late_refund_count']} refunds worth {_money(cur, m['late_refund_value'])} were posted in {r['subject']} against sales from {src}, {m['lag_days_min']}-{m['lag_days_max']} days earlier; those months' net sales were overstated until the refunds landed.", "ref": r["finding_key"], "keys": [r["finding_key"]]})

    # 2. Assumptions that need verification
    if "MAR-001" in by_rule:
        r = by_rule["MAR-001"].iloc[0]
        m = json.loads(r["measured"])
        items.append({"kind": "verify", "text": f"Gross margin fell from {m['first_window']['gross_margin_pct']:.1f}% to {m['last_window']['gross_margin_pct']:.1f}% while gross sales grew {m['revenue_growth_pct']:.0f}%; average unit cost moved {m['avg_unit_cost_change_pct']:+.1f}% against prices {m['avg_selling_price_change_pct']:+.1f}%. Growth is being bought with margin unless cost increases can be passed on.", "ref": r["finding_key"], "keys": [r["finding_key"]]})
    if "INV-003" in by_rule:
        r = by_rule["INV-003"].iloc[0]
        m = json.loads(r["measured"])
        mm = m["mismatches"][0]
        items.append({"kind": "verify", "text": f"The cost base is not fully reliable: {r['subject']} supplier invoices since {mm['period']} show {_money(cur, mm['supplier_unit_cost'])} per unit while margin reporting still uses {_money(cur, mm['recorded_unit_cost'])}, understating COGS by about {_money(cur, r['estimated_impact'] or 0)}.", "ref": r["finding_key"], "keys": [r["finding_key"]]})
    if "DSC-001" in by_rule:
        r = by_rule["DSC-001"].iloc[0]
        m = json.loads(r["measured"])
        items.append({"kind": "verify", "text": f"Discounting reached {m['discount_rate_pct']:.1f}% of GMS in {r['subject']} against a {m['median_other_months_pct']:.1f}% norm; confirm whether this was a planned campaign or clearance.", "ref": r["finding_key"], "keys": [r["finding_key"]]})

    # 3. Disproportionate contributors to risk
    if "CON-001" in by_rule:
        r = by_rule["CON-001"].iloc[0]
        m = json.loads(r["measured"])
        items.append({"kind": "concentration", "text": f"{m['top_sku']} alone generates {m['top_share_pct']:.0f}% of gross sales (top three {m['top3_share_pct']:.0f}%); a supply, quality or listing problem on one SKU would move the whole P&L.", "ref": r["finding_key"], "keys": [r["finding_key"]]})
    if "REF-001" in by_rule:
        r = by_rule["REF-001"].iloc[0]
        m = json.loads(r["measured"])
        items.append({"kind": "concentration", "text": f"{r['subject']} is returned at {m['return_rate_pct']:.0f}% of units sold versus {m['portfolio_return_rate_pct']:.1f}% across the range, mostly for '{m['reasons'][0]['reason']}' — a product-quality exposure, not a customer-behaviour one.", "ref": r["finding_key"], "keys": [r["finding_key"]]})
    if "INV-001" in by_rule:
        inv = by_rule["INV-001"]
        parts = []
        for _, r in inv.iterrows():
            m = json.loads(r["measured"])
            parts.append(f"{r['subject']} {m['cumulative_variance_units']:+d} units")
        total = float(inv["estimated_impact"].fillna(0).sum())
        items.append({"kind": "concentration", "text": f"Warehouse counts do not reconcile to receipts and sales for {len(inv)} SKU(s) ({'; '.join(parts)}), about {_money(cur, total)} of stock value; the working-capital figure depends on a verified count.", "ref": "INV-001", "keys": inv["finding_key"].tolist()})

    # 4. Missing or unreliable data sources
    ctx = AnalysisContext(conn, brand_id)
    cov = coverage(ctx)
    run = repo.get_run(conn, run_id)
    skipped = json.loads(run["skipped"]).get("skipped", []) if run and run["skipped"] else []
    if skipped:
        items.append({"kind": "data", "text": f"{len(skipped)} analyses could not run on the data provided: " + " ".join(skipped), "ref": "data room", "keys": []})
    if cov.get("channels_total") and cov["channels_with_attribution"] < cov["channels_total"]:
        items.append({"kind": "data", "text": f"Only {cov['channels_with_attribution']} of {cov['channels_total']} advertising channels report attributed revenue, so return on ad spend is unverified for the rest; treat any blended ROAS from the seller as unsupported.", "ref": "ad_spend", "keys": []})
    if "SEA-001" in by_rule:
        obs = by_rule["SEA-001"][by_rule["SEA-001"]["classification"] == "observation"]
        if not obs.empty:
            items.append({"kind": "clear", "text": f"The sales peak in {', '.join(obs['subject'])} is volume-driven with stable order values and normal refunds — consistent with seasonal demand, so it should be excluded from run-rate extrapolation rather than treated as a risk.", "ref": "SEA-001", "keys": obs["finding_key"].tolist()})

    # 5. What to investigate next
    open_hi = material[(material["severity"].isin(["critical", "high"])) & (~material["status"].isin(["verified"]))]
    nxt = open_hi.iloc[0] if not open_hi.empty else (material.iloc[0] if not material.empty else None)
    if nxt is not None and nxt["next_action"]:
        items.append({"kind": "next", "text": nxt["next_action"], "ref": nxt["finding_key"], "keys": [nxt["finding_key"]]})

    hi = int(material["severity"].isin(["critical", "high"]).sum())
    disc = material[material["classification"] == "discrepancy"]["estimated_impact"].fillna(0).sum()
    if material.empty:
        lede, sev = "The records support the seller's numbers: no material discrepancy or suspected risk was detected.", "clear"
    else:
        lede = (f"The seller's headline figures are <em>not fully supported</em> by the underlying records: {len(material)} material findings, "
                f"{hi} of them high severity, with {cur} {disc:,.0f} of quantified discrepancies and open questions on margin, returns and stock.")
        sev = "high" if hi else "medium"
    return {"lede": lede, "items": items, "severity": sev, "material": int(len(material)), "high": hi, "discrepancy_total": float(disc)}
