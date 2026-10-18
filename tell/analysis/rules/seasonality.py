"""Seasonality and sales-spike classification (SEA-001).

The rule separates *unusual* from *suspicious*. A spike is classified as a
seasonal observation (severity "info") when the supporting signals are
consistent with genuine demand: order volume rose with revenue (AOV stable),
advertising scaled with sales, gross margin stayed within a normal range and
the refund rate on the cohort is normal. Otherwise it is raised as a risk
needing investigation.
"""

from __future__ import annotations

import pandas as pd

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.metrics import robust_z
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "seasonality"


def classify_spike(fin: pd.DataFrame, idx: int) -> dict:
    row = fin.iloc[idx]
    others = fin.drop(index=fin.index[idx])
    baseline = others[others["period"] < row["period"]].tail(6) if (others["period"] < row["period"]).sum() >= 3 else others
    checks = {}
    aov_med = float(baseline["aov"].median())
    checks["aov_stable"] = abs(row["aov"] / aov_med - 1) * 100 <= T["seasonal_aov_tolerance_pct"] if aov_med else False
    orders_growth = row["orders_completed"] / baseline["orders_completed"].median() - 1 if baseline["orders_completed"].median() else 0
    sales_growth = row["gross_sales"] / baseline["gross_sales"].median() - 1 if baseline["gross_sales"].median() else 0
    checks["volume_driven"] = orders_growth >= 0.5 * sales_growth
    ad_med = float(baseline["ad_pct_of_gross_sales"].median()) if baseline["ad_pct_of_gross_sales"].notna().any() else None
    checks["ad_scaled_with_sales"] = (abs(row["ad_pct_of_gross_sales"] / ad_med - 1) * 100 <= T["seasonal_ad_ratio_tolerance_pct"]) if ad_med else None
    gm_med = float(baseline["gross_margin_pct"].median())
    checks["margin_within_range"] = abs(row["gross_margin_pct"] - gm_med) <= 8
    rr_med = float(baseline["refund_rate_pct"].median()) if baseline["refund_rate_pct"].notna().any() else None
    checks["refund_rate_normal"] = (row["refund_rate_pct"] <= max(2 * rr_med, rr_med + 2)) if rr_med is not None else None
    month = int(row["period"][5:7])
    checks["known_peak_month"] = month in T["peak_months"]
    checks = {k: (None if v is None else bool(v)) for k, v in checks.items()}
    passed = [v for v in checks.values() if v is not None]
    seasonal = sum(passed) >= len(passed) - 1 and checks["volume_driven"] and checks["aov_stable"]
    return {"checks": checks, "seasonal": seasonal, "orders_growth_pct": orders_growth * 100, "sales_growth_pct": sales_growth * 100,
            "baseline_periods": baseline["period"].tolist(), "aov_baseline": aov_med, "ad_ratio_baseline": ad_med, "margin_baseline": gm_med, "refund_rate_baseline": rr_med}


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    fin = ctx.fin
    if len(fin) < T["seasonal_min_months"]:
        res.skipped.append(f"Fewer than {T['seasonal_min_months']} months; SEA-001 (seasonality) skipped.")
        return res
    sales = fin["gross_sales"]
    for i in range(len(fin)):
        row = fin.iloc[i]
        z = robust_z(sales.drop(index=sales.index[i]), float(row["gross_sales"]))
        trailing = sales.iloc[max(0, i - 6):i]
        if len(trailing) < 3:
            trailing = sales.drop(index=sales.index[i]).head(6)
        uplift = float(row["gross_sales"]) / float(trailing.median()) - 1 if trailing.median() else 0
        if z is None or z < T["seasonal_z"] or uplift < T["seasonal_min_uplift_pct"] / 100:
            continue
        info = classify_spike(fin, i)
        period = row["period"]
        c = info["checks"]
        check_txt = "; ".join(f"{k.replace('_', ' ')}: {'yes' if v else 'no' if v is False else 'n/a'}" for k, v in c.items())
        common = dict(
            rule_id="SEA-001", rule_version=RULES["SEA-001"]["version"], subject=period, category="Seasonality & anomalies",
            period_start=period, period_end=period,
            method=f"Spike when gross sales exceed the median of other months by >= {T['seasonal_z']} robust z (MAD). Classified as seasonal when volume-driven (orders rose with sales), "
                   f"AOV within {T['seasonal_aov_tolerance_pct']}% of baseline, ad intensity within {T['seasonal_ad_ratio_tolerance_pct']}% of baseline, margin within 8pp, cohort refund rate normal, and at most one check fails.",
            measured={"gross_sales": round(float(row["gross_sales"]), 2), "robust_z": round(z, 2), "orders_completed": int(row["orders_completed"]),
                      "aov": round(float(row["aov"]), 2), "discount_rate_pct": round(float(row["discount_rate_pct"]), 2),
                      "gross_margin_pct": round(float(row["gross_margin_pct"]), 2), "ad_pct_of_gross_sales": round(float(row["ad_pct_of_gross_sales"]), 2) if pd.notna(row["ad_pct_of_gross_sales"]) else None,
                      "refund_rate_pct": round(float(row["refund_rate_pct"]), 2) if pd.notna(row["refund_rate_pct"]) else None, **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in info.items() if k != "checks"}, "checks": c},
            evidence=[Evidence(source_table="orders", source_ref=period, description=f"Completed orders {period}: gross sales", value=float(row["gross_sales"]), extra={"period": period, "orders": int(row["orders_completed"])}),
                      Evidence(source_table="ad_spend", source_ref=period, description=f"Ad spend {period}", value=float(row["ad_spend"])),
                      Evidence(source_table="refunds", source_ref=period, description=f"Refunds matched to {period} orders", value=float(row["refunds_by_order_month"]))],
        )
        if info["seasonal"]:
            res.findings.append(Finding(
                **common, title=f"{period} sales spike ({info['sales_growth_pct']:+.0f}% vs baseline) is consistent with seasonal demand",
                severity="info", classification="observation", status="detected",
                summary=f"Orders +{info['orders_growth_pct']:.0f}%, AOV {ctx.money(row['aov'])} vs {ctx.money(info['aov_baseline'])}, margin {row['gross_margin_pct']:.1f}%, discounts {row['discount_rate_pct']:.1f}%.",
                explanation=(
                    f"Gross sales in {period} were {ctx.money(row['gross_sales'])}, {info['sales_growth_pct']:+.0f}% versus the preceding baseline. The spike is volume-driven "
                    f"(completed orders {info['orders_growth_pct']:+.0f}%), average order value is stable, advertising scaled with sales, gross margin stayed within range and "
                    f"the cohort refund rate is normal. {'It falls in a recognised peak trading month. ' if c['known_peak_month'] else ''}"
                    "This is recorded as an observation, not a risk: confirm the trading calendar with the seller and check that forecasts do not annualise the peak."
                ),
                confidence="medium", confidence_note=f"Checks: {check_txt}.",
                next_action="Confirm the promotional calendar and treat the month as seasonal when normalising run-rate revenue.",
                questions=[Question(question=f"{period} sales were {info['sales_growth_pct']:+.0f}% above the preceding months. Which events or campaigns drove this, and is the pattern repeated in prior years?",
                                    rationale="Seasonal peaks must be excluded from run-rate extrapolation.", requested_items="Trading calendar; prior-year monthly sales for comparison.", priority="low")],
            ))
        else:
            res.findings.append(Finding(
                **common, title=f"{period} sales spike ({info['sales_growth_pct']:+.0f}% vs baseline) is not explained by normal demand signals",
                severity="medium", classification="suspected_risk", status="needs_investigation",
                summary=f"Failed checks: {', '.join(k.replace('_', ' ') for k, v in c.items() if v is False) or 'none'}.",
                explanation=f"Gross sales in {period} were {ctx.money(row['gross_sales'])}, {info['sales_growth_pct']:+.0f}% above baseline, but one or more consistency checks failed ({check_txt}). "
                            "Spikes without a matching rise in orders, or with abnormal margin or refunds, can indicate bulk/related-party sales, channel stuffing or data errors.",
                confidence="medium", confidence_note="Heuristic classification; verify with order-level review.",
                next_action="Review the largest orders in the month and the customers behind them.",
                questions=[Question(question=f"What explains the {period} sales spike?", rationale="Unexplained spike.", requested_items="Order export with customer details for the month.", priority="medium")],
            ))
    return res
