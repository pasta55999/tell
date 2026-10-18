"""Inventory and supplier reconciliation (INV-001, INV-002, INV-003).

Convention: inventory snapshots are month-end counts. Expected closing stock for a
month = previous recorded snapshot + supplier receipts in the month - units sold
(completed orders) in the month + refunded units flagged as restocked in the month.
"""

from __future__ import annotations

import pandas as pd

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.models import Evidence, Finding, ModuleResult, Question
from tell.db import repository as repo

NAME = "inventory"


def roll_forward(ctx: AnalysisContext) -> pd.DataFrame:
    """Per product per snapshot: recorded vs expected quantity."""
    snaps = ctx.inventory
    if snaps.empty:
        return snaps
    receipts = ctx.receipts.assign(period=lambda d: d["received_date"].str[:7]).groupby(["product_id", "period"])["quantity"].sum()
    sold = repo.units_sold_by_product_month(ctx.conn, ctx.brand_id).set_index(["product_id", "period"])["units"]
    restocked = repo.restocked_units_by_product_month(ctx.conn, ctx.brand_id).set_index(["product_id", "period"])["units"]
    rows = []
    for pid, grp in snaps.sort_values("snapshot_date").groupby("product_id"):
        prev = None
        for _, s in grp.iterrows():
            period = s["snapshot_date"][:7]
            if prev is not None:
                rec = int(receipts.get((pid, period), 0))
                out = int(sold.get((pid, period), 0))
                back = int(restocked.get((pid, period), 0))
                expected = int(prev["quantity_on_hand"]) + rec - out + back
                rows.append({"product_id": pid, "sku": s["sku"], "name": s["name"], "period": period, "snapshot_id": int(s["id"]),
                             "opening": int(prev["quantity_on_hand"]), "received": rec, "sold": out, "restocked": back,
                             "expected": expected, "recorded": int(s["quantity_on_hand"]), "variance": int(s["quantity_on_hand"]) - expected})
            prev = s
    return pd.DataFrame(rows)


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    snaps = ctx.inventory
    if snaps.empty:
        res.skipped.append("No inventory snapshots; inventory roll-forward (INV-001/002) skipped.")
    else:
        rf = roll_forward(ctx)
        costs = ctx.products.set_index("product_id")
        if rf.empty:
            res.skipped.append("Only one inventory snapshot per product; roll-forward needs at least two.")
        for pid, grp in rf.groupby("product_id"):
            base = (grp["opening"] + grp["received"]).clip(lower=1)
            flagged = grp[(grp["variance"].abs() >= T["inventory_variance_min_units"]) & (grp["variance"].abs() / base * 100 >= T["inventory_variance_min_pct"])]
            if flagged.empty:
                continue
            sku, name = grp["sku"].iloc[0], grp["name"].iloc[0]
            unit_cost = float(costs.loc[pid, "standard_cost"]) if pid in costs.index and pd.notna(costs.loc[pid, "standard_cost"]) else None
            cum = int(flagged["variance"].sum())
            direction = "below" if cum < 0 else "above"
            impact = abs(cum) * unit_cost if unit_cost else None
            pattern = ("a recurring monthly shortfall (consistent with shrinkage, unrecorded sales or write-offs)" if (flagged["variance"] < 0).all() and len(flagged) >= 3
                       else "stock recorded above what movements support (possible phantom stock, unrecorded returns or a count error)" if cum > 0
                       else "intermittent count differences")
            res.findings.append(Finding(
                rule_id="INV-001", rule_version=RULES["INV-001"]["version"], subject=sku,
                title=f"{sku} {name}: recorded stock {abs(cum)} units {direction} movement-based expectation",
                category="Inventory", severity="high" if impact and impact >= 10000 else "medium", classification="discrepancy",
                summary=f"{len(flagged)} month-end count(s) differ from the roll-forward; pattern: {pattern.split(' (')[0]}.",
                explanation=(
                    f"For {sku} ({name}) the month-end warehouse count differs from the quantity implied by the previous count plus receipts, "
                    f"less units sold, plus restocked returns in {len(flagged)} month(s): {', '.join(f'{r.period} ({r.variance:+d})' for r in flagged.itertuples())}. "
                    f"The cumulative difference is {cum:+d} units, {pattern}."
                    + (f" At the standard cost of {ctx.money(unit_cost)} per unit this is {ctx.money(impact)} of inventory value." if impact else "")
                ),
                method=f"Expected = previous snapshot + receipts - units sold + restocked returns (calendar month). Flagged when |variance| >= {T['inventory_variance_min_units']} units and >= {T['inventory_variance_min_pct']}% of opening + receipts.",
                period_start=flagged["period"].iloc[0], period_end=flagged["period"].iloc[-1],
                measured={"cumulative_variance_units": cum, "months_flagged": int(len(flagged)), "unit_cost": unit_cost,
                          "detail": flagged[["period", "opening", "received", "sold", "restocked", "expected", "recorded", "variance"]].to_dict("records")},
                estimated_impact=impact, impact_basis="Cumulative unit variance x product standard cost (inventory value at risk; not yet a P&L charge)." if impact else None,
                confidence="high" if len(flagged) >= 3 else "medium",
                confidence_note="Relies on complete receipt and sales records; a missing goods-received note would also produce a variance.",
                next_action="Request the stock count sheets and write-off register for the flagged months; perform a test count at close.",
                evidence=[Evidence(source_table="inventory_snapshots", source_id=int(r.snapshot_id), source_ref=f"{sku}:{r.period}",
                                   description=f"{r.period}: opening {r.opening} + received {r.received} - sold {r.sold} + restocked {r.restocked} = expected {r.expected}; recorded {r.recorded}",
                                   value=float(r.variance), extra={"expected": r.expected, "recorded": r.recorded}) for r in flagged.itertuples()],
                questions=[Question(
                    question=f"Warehouse counts for {sku} ({name}) are {abs(cum)} units {direction} what receipts and sales support since {flagged['period'].iloc[0]}. Has stock been written off, transferred or sold through an unrecorded channel?",
                    rationale="Inventory variances affect the working-capital figure in the deal and may reveal unrecorded sales channels or shrinkage.",
                    requested_items="Stock count sheets; write-off and damage register; inter-location transfer log; 3PL reports.",
                    priority="high" if impact and impact >= 10000 else "medium")],
            ))

        neg = snaps[snaps["quantity_on_hand"] < 0]
        for sku, grp in neg.groupby("sku"):
            res.findings.append(Finding(
                rule_id="INV-002", rule_version=RULES["INV-002"]["version"], subject=str(sku),
                title=f"{sku}: negative stock recorded in {len(grp)} snapshot(s)",
                category="Inventory", severity="medium", classification="discrepancy",
                summary=f"Lowest recorded quantity {int(grp['quantity_on_hand'].min())}.",
                explanation="Negative on-hand quantities indicate sales recorded against stock that was never received, or missing receipts.",
                method="Any inventory snapshot with quantity_on_hand < 0.", period_start=grp["snapshot_date"].min()[:7], period_end=grp["snapshot_date"].max()[:7],
                measured={"snapshots": grp[["snapshot_date", "quantity_on_hand"]].to_dict("records")}, confidence="high",
                next_action="Request goods-received notes for the period.",
                evidence=[Evidence(source_table="inventory_snapshots", source_id=int(r["id"]), source_ref=f"{sku}:{r['snapshot_date']}", description=f"Snapshot {r['snapshot_date']}", value=float(r["quantity_on_hand"])) for _, r in grp.iterrows()],
                questions=[Question(question=f"Why does {sku} show negative stock?", rationale="Record integrity.", requested_items="GRNs and stock ledger.", priority="medium")],
            ))

    # ---- INV-003 supplier cost vs recorded unit cost
    receipts = ctx.receipts
    if receipts.empty:
        res.skipped.append("No supplier receipts; INV-003 (supplier cost reconciliation) skipped.")
        return res
    recorded = repo.product_cost_by_month(ctx.conn, ctx.brand_id)
    if recorded.empty:
        res.skipped.append("Order lines carry no unit cost; INV-003 skipped.")
        return res
    rec_idx = recorded.set_index(["product_id", "period"])
    sold_by_month = repo.units_sold_by_product_month(ctx.conn, ctx.brand_id).set_index(["product_id", "period"])["units"]
    r = receipts.assign(period=receipts["received_date"].str[:7])
    for pid, grp in r.groupby("product_id"):
        mismatches = []
        for row in grp.itertuples():
            key = (pid, row.period)
            if key not in rec_idx.index:
                continue
            rec_cost = float(rec_idx.loc[key, "avg_unit_cost"])
            if rec_cost <= 0:
                continue
            diff_pct = (row.unit_cost - rec_cost) / rec_cost * 100
            if abs(diff_pct) >= T["supplier_cost_variance_pct"]:
                mismatches.append({"receipt_id": int(row.id), "receipt_ref": row.receipt_ref, "period": row.period, "supplier_unit_cost": float(row.unit_cost),
                                   "recorded_unit_cost": round(rec_cost, 2), "variance_pct": round(diff_pct, 1), "supplier": row.supplier})
        if not mismatches:
            continue
        sku = grp["sku"].iloc[0]
        first_period = min(m["period"] for m in mismatches)
        units_after = int(sum(v for (p, per), v in sold_by_month.items() if p == pid and per >= first_period))
        avg_gap = sum(m["supplier_unit_cost"] - m["recorded_unit_cost"] for m in mismatches) / len(mismatches)
        impact = avg_gap * units_after
        name = ctx.products.set_index("product_id").loc[pid, "name"] if pid in ctx.products["product_id"].values else sku
        res.findings.append(Finding(
            rule_id="INV-003", rule_version=RULES["INV-003"]["version"], subject=str(sku),
            title=f"{sku} {name}: supplier invoices {mismatches[0]['variance_pct']:+.0f}% vs unit cost used in COGS",
            category="Inventory", severity="medium" if abs(impact) < 10000 else "high", classification="discrepancy",
            summary=f"{len(mismatches)} receipt(s) since {first_period} priced at {ctx.money(mismatches[0]['supplier_unit_cost'])} vs {ctx.money(mismatches[0]['recorded_unit_cost'])} recorded on sales.",
            explanation=(
                f"Supplier receipts for {sku} from {first_period} show a unit cost of {ctx.money(mismatches[0]['supplier_unit_cost'])}, while order lines in the same "
                f"months still carry {ctx.money(mismatches[0]['recorded_unit_cost'])}. If the newer invoice price is the true cost, COGS on the {units_after} units sold "
                f"since {first_period} is understated by about {ctx.money(impact)} and the SKU's gross margin is overstated."
            ),
            method=f"Compare each supplier receipt's unit cost with the average unit cost recorded on order lines for the same product and month. Flagged when |difference| >= {T['supplier_cost_variance_pct']}%.",
            period_start=first_period, period_end=ctx.period_end,
            measured={"mismatches": mismatches, "units_sold_since": units_after, "avg_unit_cost_gap": round(avg_gap, 2)},
            estimated_impact=abs(impact), impact_basis="(Supplier unit cost - recorded unit cost) x units sold since the first mismatched receipt (COGS understatement).",
            confidence="medium", confidence_note="Assumes FIFO-like consumption; actual timing of when the new cost should flow through depends on stock on hand.",
            next_action="Request the supplier price change notice and confirm which cost the seller uses for margin reporting.",
            evidence=[Evidence(source_table="supplier_receipts", source_id=m["receipt_id"], source_ref=m["receipt_ref"],
                               description=f"Receipt {m['receipt_ref']} ({m['period']}, {m['supplier']}): unit cost {m['supplier_unit_cost']} vs recorded {m['recorded_unit_cost']}",
                               value=m["supplier_unit_cost"], extra=m) for m in mismatches],
            questions=[Question(
                question=f"Supplier invoices for {sku} since {first_period} show a unit cost of {ctx.money(mismatches[0]['supplier_unit_cost'])}, yet margin reporting still uses {ctx.money(mismatches[0]['recorded_unit_cost'])}. Which figure is correct and when was the standard cost last updated?",
                rationale="Stale standard costs overstate gross margin on a top-selling SKU.",
                requested_items="Supplier invoices and price notices; standard cost update log; landed-cost calculation.",
                priority="medium")],
        ))
    return res
