"""Refund and returns intelligence (REF-001, REF-002, REF-003)."""

from __future__ import annotations

import pandas as pd

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "refunds"


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    products = ctx.products
    lags = ctx.refund_lags
    if lags.empty:
        res.skipped.append("No refund records; refund analyses skipped.")
        return res

    # ---- REF-001 product return rate
    total_units = products["units"].sum()
    portfolio_rate = products["refunded_units"].sum() / total_units * 100 if total_units else 0
    threshold = max(T["return_rate_min_pct"], T["return_rate_multiple_of_portfolio"] * portfolio_rate)
    eligible = products[products["units"] >= T["return_rate_min_units"]]
    for _, p in eligible[eligible["return_rate_pct"] >= threshold].iterrows():
        reasons = ctx.conn.execute(
            """SELECT r.reason, COUNT(*) AS n FROM refund_items ri JOIN refunds r ON r.id = ri.refund_id
               WHERE ri.product_id = ? GROUP BY r.reason ORDER BY n DESC""", (int(p["product_id"]),)).fetchall()
        refund_rows = ctx.conn.execute(
            """SELECT r.id, r.refund_ref, r.refund_date, ri.quantity, ri.amount, r.reason FROM refund_items ri
               JOIN refunds r ON r.id = ri.refund_id WHERE ri.product_id = ? ORDER BY r.refund_date""", (int(p["product_id"]),)).fetchall()
        top_reason = f"{reasons[0]['reason']} ({reasons[0]['n']} of {sum(r['n'] for r in reasons)})" if reasons else "n/a"
        excess_units = p["refunded_units"] - portfolio_rate / 100 * p["units"]
        impact = excess_units * (p["gross_sales"] / p["units"]) if p["units"] else 0
        res.findings.append(Finding(
            rule_id="REF-001", rule_version=RULES["REF-001"]["version"], subject=p["sku"],
            title=f"{p['sku']} {p['name']}: return rate {p['return_rate_pct']:.1f}% vs {portfolio_rate:.1f}% portfolio",
            category="Refunds & returns", severity="high" if p["return_rate_pct"] >= 2 * threshold else "medium",
            classification="suspected_risk",
            summary=f"{int(p['refunded_units'])} of {int(p['units'])} units refunded; most common reason: {top_reason}.",
            explanation=(
                f"{p['sku']} ({p['name']}) sold {int(p['units'])} units and had {int(p['refunded_units'])} units refunded "
                f"({p['return_rate_pct']:.1f}%), against a portfolio return rate of {portfolio_rate:.1f}%. The most common "
                f"recorded reason is '{top_reason}'. A product-specific quality or description problem erodes margin "
                f"(this SKU represents {p['revenue_share_pct']:.1f}% of gross sales) and may create warranty or reputational exposure."
            ),
            method=f"Return rate = refunded units / units sold over the full period, products with >= {T['return_rate_min_units']} units sold. "
                   f"Flagged when rate >= max({T['return_rate_min_pct']}%, {T['return_rate_multiple_of_portfolio']} x portfolio rate).",
            period_start=ctx.period_start, period_end=ctx.period_end,
            measured={"units_sold": int(p["units"]), "refunded_units": int(p["refunded_units"]), "return_rate_pct": round(float(p["return_rate_pct"]), 2),
                      "portfolio_return_rate_pct": round(portfolio_rate, 2), "threshold_pct": round(threshold, 2),
                      "refunded_amount": round(float(p["refunded_amount"]), 2), "reasons": [dict(r) for r in reasons]},
            estimated_impact=max(0.0, impact),
            impact_basis="Refund value attributable to returns above the portfolio rate (excess units x average realised price).",
            confidence="high" if p["units"] >= 60 else "medium",
            confidence_note=f"Sample of {int(p['units'])} units; reason codes are as recorded by the seller.",
            next_action="Request quality complaints log, supplier QC reports and any product reformulation history for this SKU.",
            evidence=[Evidence(source_table="refunds", source_id=int(r["id"]), source_ref=r["refund_ref"],
                               description=f"Refund {r['refund_ref']} on {r['refund_date']}: {int(r['quantity'])} unit(s), reason '{r['reason']}'",
                               value=float(r["amount"])) for r in refund_rows],
            questions=[Question(
                question=f"{p['sku']} ({p['name']}) shows a {p['return_rate_pct']:.0f}% return rate, mostly for '{reasons[0]['reason'] if reasons else 'unspecified'}'. What is the root cause and what corrective action has been taken with the supplier?",
                rationale="A structural quality issue on a material SKU affects margin, customer lifetime value and inventory valuation.",
                requested_items="Customer complaint log; supplier QC and inspection reports; batch/lot records; any credit notes from the supplier.",
                priority="high")],
        ))

    # ---- REF-002 late refunds by posting month
    late = lags[lags["lag_days"] > T["late_refund_lag_days"]]
    totals_by_period = lags.groupby("refund_period")["amount"].sum()
    for period, grp in late.groupby("refund_period"):
        share = grp["amount"].sum() / totals_by_period[period] * 100 if totals_by_period.get(period) else 0
        if len(grp) < T["late_refund_min_count"] or share < T["late_refund_min_share_pct"]:
            continue
        source_periods = grp["order_period"].value_counts().to_dict()
        source_txt = ", ".join(f"{k} ({v})" for k, v in sorted(source_periods.items()))
        reasons = grp["reason"].value_counts().to_dict()
        res.findings.append(Finding(
            rule_id="REF-002", rule_version=RULES["REF-002"]["version"], subject=period,
            title=f"{len(grp)} refunds posted in {period} relate to sales {int(grp['lag_days'].min())}-{int(grp['lag_days'].max())} days earlier",
            category="Refunds & returns", severity="high", classification="discrepancy",
            summary=f"{ctx.money(grp['amount'].sum())} ({share:.0f}% of the month's refunds) relates to orders from {source_txt}.",
            explanation=(
                f"In {period}, {len(grp)} refunds totalling {ctx.money(grp['amount'].sum())} were posted against orders placed in "
                f"{source_txt}, with lags of {int(grp['lag_days'].min())}-{int(grp['lag_days'].max())} days (normal lag in this dataset is "
                f"{lags.loc[lags['lag_days'] <= T['late_refund_lag_days'], 'lag_days'].median():.0f} days). The dominant reason code is "
                f"'{max(reasons, key=reasons.get)}'. Late refunds shift cost out of the sale month, flattering the earlier months' net "
                "sales, and can indicate deferred customer complaints, a product recall, or refunds processed to manage reported results."
            ),
            method=f"Lag = refund date - order date. Flagged when a posting month has >= {T['late_refund_min_count']} refunds with lag > "
                   f"{T['late_refund_lag_days']} days and they represent >= {T['late_refund_min_share_pct']}% of that month's refund value.",
            period_start=min(source_periods), period_end=period,
            measured={"late_refund_count": int(len(grp)), "late_refund_value": round(float(grp["amount"].sum()), 2),
                      "share_of_month_refunds_pct": round(share, 1), "source_periods": source_periods, "reasons": reasons,
                      "lag_days_min": int(grp["lag_days"].min()), "lag_days_max": int(grp["lag_days"].max())},
            estimated_impact=float(grp["amount"].sum()),
            impact_basis="Value of late refunds; the same amount overstates net sales in the original sale months.",
            confidence="high", confidence_note="Dates taken directly from order and refund records.",
            next_action="Re-state net sales for the source months with refunds matched to original orders; request the refund approval trail.",
            evidence=[Evidence(source_table="refunds", source_id=int(r["refund_id"]), source_ref=r["refund_ref"],
                               description=f"Refund {r['refund_ref']} posted {r['refund_date']} for order {r['order_ref']} dated {r['order_date']} ({int(r['lag_days'])} days)",
                               value=float(r["amount"]), extra={"order_id": int(r["order_id"]), "reason": r["reason"]}) for _, r in grp.iterrows()],
            questions=[Question(
                question=f"{len(grp)} refunds worth {ctx.money(grp['amount'].sum())} were processed in {period} for orders from {source_txt}. Why were these refunds issued so long after the sale, and who approved them?",
                rationale="Establishes whether the earlier months' results are overstated and whether there is an undisclosed product or customer issue.",
                requested_items="Refund approval log; customer correspondence for the affected orders; any recall or complaint batch documentation.",
                priority="high")],
        ))

    # ---- REF-003 refund-rate spike by order cohort
    fin = ctx.fin
    rates = fin["refund_rate_pct"]
    if rates.notna().sum() >= 4:
        for _, row in fin.iterrows():
            rate = row["refund_rate_pct"]
            if pd.isna(rate) or row["refunds_by_order_month_count"] < T["refund_rate_min_refunds"]:
                continue
            median_other = float(rates[fin["period"] != row["period"]].median())
            if median_other <= 0 or rate < T["refund_rate_spike_multiple"] * median_other:
                continue
            period = row["period"]
            cohort = lags[lags["order_period"] == period]
            late_share = cohort.loc[cohort["lag_days"] > T["late_refund_lag_days"], "amount"].sum() / cohort["amount"].sum() * 100 if len(cohort) else 0
            res.findings.append(Finding(
                rule_id="REF-003", rule_version=RULES["REF-003"]["version"], subject=period,
                title=f"Orders placed in {period} were refunded at {rate:.1f}% of gross sales ({rate / median_other:.1f}x normal)",
                category="Refunds & returns", severity="medium", classification="suspected_risk",
                summary=f"{int(row['refunds_by_order_month_count'])} refunds against {period} orders; {late_share:.0f}% of the value was refunded more than {T['late_refund_lag_days']} days after sale.",
                explanation=(
                    f"Refunds matched back to orders placed in {period} total {ctx.money(row['refunds_by_order_month'])}, or {rate:.1f}% of that month's gross sales, "
                    f"compared with a median of {median_other:.1f}% for other months. {late_share:.0f}% of this value was refunded more than "
                    f"{T['late_refund_lag_days']} days after the sale, so the cohort's true net sales only became visible later."
                ),
                method=f"Cohort refund rate = refunds (by original order month) / gross sales of that month. Flagged when >= {T['refund_rate_spike_multiple']}x the median of other months and at least {T['refund_rate_min_refunds']} refunds.",
                period_start=period, period_end=period,
                measured={"cohort_refund_rate_pct": round(float(rate), 2), "median_other_months_pct": round(median_other, 2),
                          "refund_count": int(row["refunds_by_order_month_count"]), "refund_value": round(float(row["refunds_by_order_month"]), 2),
                          "late_share_pct": round(late_share, 1)},
                estimated_impact=float(row["refunds_by_order_month"]) - median_other / 100 * float(row["gross_sales"]),
                impact_basis="Refund value above the normal cohort refund rate.",
                confidence="medium", confidence_note="Depends on refunds being linked to the correct original orders.",
                next_action="Review the quality of orders fulfilled in this month (supplier batch, courier, promotion) and confirm no further refunds are pending.",
                evidence=[Evidence(source_table="refunds", source_id=int(r["refund_id"]), source_ref=r["refund_ref"],
                                   description=f"Refund {r['refund_ref']} ({int(r['lag_days'])} days after order {r['order_ref']})", value=float(r["amount"]))
                          for _, r in cohort.iterrows()],
                questions=[Question(
                    question=f"Orders from {period} were refunded at {rate:.1f}% of sales, well above other months. Was there a specific batch, courier or campaign issue with these orders?",
                    rationale="Identifies whether the spike is a one-off operational event or a recurring quality problem.",
                    requested_items="Fulfilment and courier incident reports; supplier batch records for the month; customer service ticket export.",
                    priority="medium")],
            ))
    return res
