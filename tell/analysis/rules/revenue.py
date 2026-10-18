"""Revenue reconciliation (REV-001) and discounting anomalies (DSC-001)."""

from __future__ import annotations

from itertools import combinations

import pandas as pd

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.metrics import robust_z
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "revenue"


def attribute_variance(row: pd.Series) -> tuple[str | None, float]:
    """Try to explain a reported-vs-derived variance with combinations of the
    standard reconciling items. Returns (label, residual) for the best match
    within 10% of the variance, else (None, variance)."""
    variance = float(row["revenue_variance"])
    if variance == 0:
        return None, 0.0
    items = {
        "refunds posted in the month (i.e. reported figure is gross of refunds)": float(row.get("refunds_posted", 0) or 0),
        "value of cancelled orders": float(row.get("cancelled_value", 0) or 0),
        "shipping charged to customers": float(row.get("shipping", 0) or 0),
        "discounts (i.e. reported figure is before discounts)": float(row.get("discounts", 0) or 0),
    }
    best: tuple[str | None, float] = (None, variance)
    for n in (1, 2, 3):
        for combo in combinations(items.items(), n):
            total = sum(v for _, v in combo)
            residual = variance - total
            if abs(residual) <= abs(variance) * 0.10 and abs(residual) < abs(best[1]):
                best = (" + ".join(k for k, _ in combo), residual)
    return best


def _severity(pct: float) -> str:
    a = abs(pct)
    if a >= 10:
        return "critical" if a >= 20 else "high"
    if a >= T["revenue_variance_pct_high"]:
        return "high"
    return "medium"


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    fin = ctx.fin
    if fin.empty:
        res.skipped.append("No orders available; revenue reconciliation skipped.")
        return res

    if fin["reported_revenue"].notna().sum() == 0:
        res.skipped.append("No seller-reported statements; REV-001 (revenue reconciliation) skipped.")
    else:
        rule = RULES["REV-001"]
        for _, row in fin[fin["reported_revenue"].notna()].iterrows():
            pct = row["revenue_variance_pct"]
            if pd.isna(pct) or abs(pct) < T["revenue_variance_pct_medium"]:
                continue
            period = row["period"]
            label, residual = attribute_variance(row)
            variance = float(row["revenue_variance"])
            direction = "above" if variance > 0 else "below"
            explanation = (
                f"Seller-reported revenue for {period} is {ctx.money(row['reported_revenue'])}, "
                f"while net sales derived from {int(row['orders_completed'])} completed orders "
                f"(gross sales {ctx.money(row['gross_sales'])} less refunds posted {ctx.money(row['refunds_posted'])}) "
                f"are {ctx.money(row['net_sales'])}: a variance of {ctx.money(variance)} ({pct:+.1f}%)."
            )
            if label:
                explanation += (
                    f" The variance is approximately equal to {label} "
                    f"(residual {ctx.money(residual)}), which suggests a definitional difference rather than random error."
                )
            else:
                explanation += " The variance does not match any standard reconciling item and needs explanation."
            evidence = [
                Evidence(source_table="seller_statements", source_ref=period,
                         description=f"Seller statement {period}: reported revenue", value=float(row["reported_revenue"])),
                Evidence(source_table="orders", source_ref=period,
                         description=f"Completed orders {period}: gross sales (after discounts)", value=float(row["gross_sales"]),
                         extra={"orders_completed": int(row["orders_completed"]), "period": period}),
                Evidence(source_table="refunds", source_ref=period,
                         description=f"Refunds posted in {period}", value=float(row["refunds_posted"]),
                         extra={"refund_count": int(row["refunds_posted_count"]), "period": period}),
                Evidence(source_table="orders", source_ref=f"{period}:cancelled",
                         description=f"Cancelled orders {period}: value", value=float(row["cancelled_value"]),
                         extra={"orders_cancelled": int(row["orders_cancelled"]), "period": period, "status": "cancelled"}),
            ]
            res.findings.append(Finding(
                rule_id="REV-001", rule_version=rule["version"], subject=period,
                title=f"Reported revenue {direction} order-derived net sales in {period}",
                category="Revenue reconciliation", severity=_severity(pct), classification="discrepancy",
                summary=f"Seller reports {ctx.money(row['reported_revenue'])}; records support {ctx.money(row['net_sales'])} ({pct:+.1f}%).",
                explanation=explanation,
                method="Net sales = gross sales of completed orders placed in the month - refunds posted in the month. "
                       f"Variance flagged when |variance| >= {T['revenue_variance_pct_medium']}% of net sales. "
                       "Variance attribution tests combinations of refunds, cancellations, shipping and discounts within a 10% residual.",
                period_start=period, period_end=period,
                measured={"reported_revenue": round(float(row["reported_revenue"]), 2), "net_sales": round(float(row["net_sales"]), 2),
                          "gross_sales": round(float(row["gross_sales"]), 2), "refunds_posted": round(float(row["refunds_posted"]), 2),
                          "cancelled_value": round(float(row["cancelled_value"]), 2), "variance": round(variance, 2),
                          "variance_pct": round(float(pct), 2), "attribution": label, "attribution_residual": round(residual, 2)},
                estimated_impact=abs(variance),
                impact_basis="Absolute revenue variance for the month. If the seller's definition is used in the valuation, trailing revenue is overstated by this amount.",
                confidence="high" if label else "medium",
                confidence_note="Both figures come from the same reporting period and currency; attribution matched a reconciling item." if label
                else "Variance confirmed but its cause is not identifiable from the records provided.",
                next_action="Request the seller's revenue recognition policy and the working file behind the monthly figure; re-state revenue net of refunds and cancellations.",
                evidence=evidence,
                questions=[Question(
                    question=f"Your management accounts report revenue of {ctx.money(row['reported_revenue'])} for {period}, but order records net of refunds support {ctx.money(row['net_sales'])}. How is revenue defined in your reporting, and are cancelled orders or refunds included?",
                    rationale="Determines whether headline revenue in the information memorandum is overstated and whether the same definition affects other months.",
                    requested_items="Revenue recognition policy; reconciliation of the monthly revenue figure to order exports; refund and cancellation reports.",
                    priority="high" if abs(pct) >= T["revenue_variance_pct_high"] else "medium",
                )],
            ))

    # DSC-001 heavy discounting
    rule = RULES["DSC-001"]
    rates = fin["discount_rate_pct"]
    if rates.notna().sum() < 4:
        res.skipped.append("Fewer than 4 months of data; DSC-001 (discounting anomaly) skipped.")
        return res
    for _, row in fin.iterrows():
        rate = row["discount_rate_pct"]
        if pd.isna(rate) or rate < T["discount_rate_min_pct"]:
            continue
        others = rates[fin["period"] != row["period"]]
        z = robust_z(others, float(rate))
        if z is None or z < T["discount_rate_mad_multiplier"]:
            continue
        period = row["period"]
        median_rate = float(others.median())
        excess_discount = float(row["discounts"]) - median_rate / 100 * float(row["gms"])
        res.findings.append(Finding(
            rule_id="DSC-001", rule_version=rule["version"], subject=period,
            title=f"Heavy discounting in {period} ({rate:.1f}% of GMS)",
            category="Pricing & promotions", severity="medium", classification="suspected_risk",
            summary=f"Discounts were {rate:.1f}% of GMS versus a {median_rate:.1f}% median in other months.",
            explanation=(
                f"In {period} the brand gave {ctx.money(row['discounts'])} of discounts on GMS of {ctx.money(row['gms'])} "
                f"({rate:.1f}%), compared with a median of {median_rate:.1f}% across the other months (robust z = {z:.1f}). "
                f"Gross margin that month was {row['gross_margin_pct']:.1f}%. Heavy promotions can pull demand forward, "
                "mask underlying weakness, or indicate stock clearance; the cause should be confirmed."
            ),
            method=f"Discount rate = discounts / GMS. Flagged when rate >= {T['discount_rate_min_pct']}% and robust z-score "
                   f"(median/MAD of other months) >= {T['discount_rate_mad_multiplier']}.",
            period_start=period, period_end=period,
            measured={"discount_rate_pct": round(float(rate), 2), "median_other_months_pct": round(median_rate, 2),
                      "robust_z": round(z, 2), "discounts": round(float(row["discounts"]), 2), "gms": round(float(row["gms"]), 2),
                      "gross_margin_pct": round(float(row["gross_margin_pct"]), 2)},
            estimated_impact=max(0.0, excess_discount),
            impact_basis="Discounts above the median discount rate applied to the month's GMS (margin given away relative to normal pricing).",
            confidence="high", confidence_note="Computed directly from order-level discount fields.",
            next_action="Ask for the promotion calendar and the commercial rationale; check whether the following months show a demand hangover.",
            evidence=[Evidence(source_table="orders", source_ref=period, description=f"Completed orders {period}: discounts",
                               value=float(row["discounts"]), extra={"period": period, "gms": float(row["gms"])})],
            questions=[Question(
                question=f"Discounts in {period} reached {rate:.1f}% of GMS versus roughly {median_rate:.0f}% in other months. What promotion ran, what was its objective, and was any of it stock clearance?",
                rationale="Distinguishes a planned marketing event from distress discounting or clearance of slow-moving stock.",
                requested_items="Promotion calendar; campaign brief and results; stock ageing report for the period.",
                priority="medium")],
        ))
    return res
