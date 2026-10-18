"""Profitability: gross margin trend vs revenue trend (MAR-001)."""

from __future__ import annotations

import pandas as pd

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "profitability"


def margin_windows(fin: pd.DataFrame, window: int) -> tuple[dict, dict] | None:
    """Compare the first `window` months with the last `window` months."""
    if len(fin) < 2 * window:
        return None
    first, last = fin.head(window), fin.tail(window)

    def agg(df: pd.DataFrame) -> dict:
        gs, cogs = float(df["gross_sales"].sum()), float(df["cogs"].sum())
        return {"period_start": df["period"].iloc[0], "period_end": df["period"].iloc[-1], "gross_sales": gs,
                "cogs": cogs, "gross_margin_pct": (gs - cogs) / gs * 100 if gs else None,
                "units": int(df["units"].sum()), "avg_unit_cost": cogs / int(df["units"].sum()) if df["units"].sum() else None,
                "avg_selling_price": gs / int(df["units"].sum()) if df["units"].sum() else None}

    return agg(first), agg(last)


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    fin = ctx.fin
    window = min(T["margin_window_months"], len(fin) // 2)
    if fin.empty or window < 3:
        res.skipped.append("Fewer than 6 months of data; MAR-001 (margin trend) skipped.")
        return res
    if fin["units_without_cost"].sum() > 0 and fin["cogs"].sum() == 0:
        res.skipped.append("No unit costs available; MAR-001 (margin trend) skipped.")
        return res

    first, last = margin_windows(fin, window)
    if first["gross_margin_pct"] is None or last["gross_margin_pct"] is None:
        return res
    margin_change = last["gross_margin_pct"] - first["gross_margin_pct"]
    revenue_growth = (last["gross_sales"] / first["gross_sales"] - 1) * 100 if first["gross_sales"] else 0
    if margin_change > -T["margin_decline_pp"] or revenue_growth <= 0:
        res.notes.append(f"Gross margin moved {margin_change:+.1f}pp between the first and last {window} months; no decline above threshold.")
        return res

    # Decompose: cost per unit vs price per unit
    cost_change = (last["avg_unit_cost"] / first["avg_unit_cost"] - 1) * 100 if first["avg_unit_cost"] else 0
    price_change = (last["avg_selling_price"] / first["avg_selling_price"] - 1) * 100 if first["avg_selling_price"] else 0
    # Product-level cost drift: SKUs whose recorded unit cost increased the most
    pm = ctx.product_monthly
    drift_rows = []
    if not pm.empty:
        def avg_cost(df: pd.DataFrame) -> pd.Series:
            g = df.groupby(["sku", "name"])[["cogs", "units"]].sum()
            return g["cogs"] / g["units"]

        early = avg_cost(pm[pm["period"] <= first["period_end"]]).rename("early")
        late = avg_cost(pm[pm["period"] >= last["period_start"]]).rename("late")
        drift = pd.concat([early, late], axis=1).dropna()
        drift["change_pct"] = (drift["late"] / drift["early"] - 1) * 100
        drift_rows = drift.sort_values("change_pct", ascending=False).head(5).reset_index().to_dict("records")

    lost_gp = (first["gross_margin_pct"] - last["gross_margin_pct"]) / 100 * last["gross_sales"]
    subject = f"{last['period_start']}..{last['period_end']}"
    evidence = [
        Evidence(source_table="orders", source_ref=f"{first['period_start']}..{first['period_end']}",
                 description=f"First {window} months: gross margin", value=round(first["gross_margin_pct"], 2),
                 extra={"gross_sales": first["gross_sales"], "cogs": first["cogs"]}),
        Evidence(source_table="orders", source_ref=subject,
                 description=f"Last {window} months: gross margin", value=round(last["gross_margin_pct"], 2),
                 extra={"gross_sales": last["gross_sales"], "cogs": last["cogs"]}),
    ] + [Evidence(source_table="order_items", source_ref=r["sku"], description=f"{r['sku']} {r['name']}: recorded unit cost change",
                  value=round(r["change_pct"], 2), extra={"early_unit_cost": round(r["early"], 2), "late_unit_cost": round(r["late"], 2)})
         for r in drift_rows]
    res.findings.append(Finding(
        rule_id="MAR-001", rule_version=RULES["MAR-001"]["version"], subject=subject,
        title=f"Gross margin fell {abs(margin_change):.1f}pp while gross sales grew {revenue_growth:.0f}%",
        category="Profitability", severity="high" if abs(margin_change) >= 5 else "medium", classification="suspected_risk",
        summary=f"Margin {first['gross_margin_pct']:.1f}% -> {last['gross_margin_pct']:.1f}%; average unit cost {cost_change:+.1f}%, average selling price {price_change:+.1f}%.",
        explanation=(
            f"Comparing {first['period_start']}..{first['period_end']} with {last['period_start']}..{last['period_end']}, gross sales grew "
            f"{revenue_growth:.0f}% but gross margin declined from {first['gross_margin_pct']:.1f}% to {last['gross_margin_pct']:.1f}%. "
            f"Average recorded unit cost moved {cost_change:+.1f}% while average selling price moved {price_change:+.1f}%, so the "
            "decline is driven mainly by " + ("cost inflation that has not been passed on to customers." if cost_change > abs(price_change) else "lower realised prices / discounting.")
            + " Growth that is bought with margin is less valuable than it appears on the top line."
        ),
        method=f"Gross margin = (gross sales - COGS) / gross sales, using unit costs recorded on order lines. Flagged when the last {window}-month margin is at least "
               f"{T['margin_decline_pp']}pp below the first {window}-month margin while gross sales grew. COGS excludes freight, duties and fulfilment unless embedded in unit cost.",
        period_start=first["period_start"], period_end=last["period_end"],
        measured={"first_window": first, "last_window": last, "margin_change_pp": round(margin_change, 2),
                  "revenue_growth_pct": round(revenue_growth, 2), "avg_unit_cost_change_pct": round(cost_change, 2),
                  "avg_selling_price_change_pct": round(price_change, 2), "largest_cost_increases": drift_rows},
        estimated_impact=lost_gp,
        impact_basis=f"Gross profit forgone in the last {window} months had the earlier margin been maintained (margin gap x recent gross sales).",
        confidence="high", confidence_note="Calculated from order-line costs; depends on the seller recording cost changes accurately.",
        next_action="Obtain supplier price lists and freight invoices for the period; test whether price increases are planned or feasible.",
        evidence=evidence,
        questions=[Question(
            question=f"Gross margin declined from {first['gross_margin_pct']:.1f}% to {last['gross_margin_pct']:.1f}% while sales grew. What drove the unit-cost increase, is it permanent, and what pricing actions are planned?",
            rationale="Margin compression changes the earnings base used for valuation and may indicate supplier dependence or lost pricing power.",
            requested_items="Supplier price change notices; landed cost workings by SKU; pricing history; forward purchase orders.",
            priority="high")],
    ))
    return res
