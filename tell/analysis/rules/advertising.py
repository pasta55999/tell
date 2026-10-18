"""Advertising efficiency and statement reconciliation (ADV-001, ADV-002)."""

from __future__ import annotations

import pandas as pd

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.metrics import robust_z
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "advertising"


def channel_table(ads: pd.DataFrame) -> pd.DataFrame:
    """Per-channel totals; ROAS only where attributed revenue exists for every row of the channel."""
    if ads.empty:
        return ads
    g = ads.groupby("channel", as_index=False).agg(spend=("spend", "sum"), impressions=("impressions", "sum"), clicks=("clicks", "sum"),
                                                   attributed_revenue=("attributed_revenue", "sum"), months=("period", "nunique"),
                                                   months_with_attribution=("attributed_revenue", "count"))
    g["roas"] = g.apply(lambda r: r["attributed_revenue"] / r["spend"] if r["months_with_attribution"] == r["months"] and r["spend"] > 0 else None, axis=1)
    g["attribution_available"] = g["months_with_attribution"] == g["months"]
    return g.sort_values("spend", ascending=False).reset_index(drop=True)


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    fin, ads = ctx.fin, ctx.ad_spend
    if ads.empty:
        res.skipped.append("No advertising spend records; advertising analyses skipped.")
        return res

    ch = channel_table(ads)
    without = ch.loc[~ch["attribution_available"], "channel"].tolist()
    if without:
        res.notes.append("ROAS not computed for channels without platform-attributed revenue: " + ", ".join(without) + ".")

    # ---- ADV-002 statement vs records
    if fin["reported_ad_spend"].notna().sum() == 0:
        res.skipped.append("Seller statements do not include advertising; ADV-002 skipped.")
    else:
        for _, row in fin[fin["reported_ad_spend"].notna()].iterrows():
            pct = row["ad_variance_pct"]
            if pd.isna(pct) or abs(pct) < T["ad_variance_pct"]:
                continue
            period = row["period"]
            per_channel = ads[ads["period"] == period]
            direction = "understates" if row["ad_variance"] < 0 else "overstates"
            res.findings.append(Finding(
                rule_id="ADV-002", rule_version=RULES["ADV-002"]["version"], subject=period,
                title=f"Seller statement {direction} advertising spend in {period} by {ctx.money(abs(row['ad_variance']))}",
                category="Advertising", severity="high" if abs(pct) >= 25 else "medium", classification="discrepancy",
                summary=f"Reported {ctx.money(row['reported_ad_spend'])} vs {ctx.money(row['ad_spend'])} in channel records ({pct:+.0f}%).",
                explanation=(
                    f"The seller's {period} statement reports advertising of {ctx.money(row['reported_ad_spend'])}, but platform spend records "
                    f"across {len(per_channel)} channels total {ctx.money(row['ad_spend'])}. Understated marketing cost inflates reported "
                    "profit; if the figure feeds an EBITDA bridge, normalised earnings must be adjusted."
                ),
                method=f"Variance = reported ad spend - sum of channel spend for the month. Flagged when |variance| >= {T['ad_variance_pct']}% of recorded spend.",
                period_start=period, period_end=period,
                measured={"reported_ad_spend": round(float(row["reported_ad_spend"]), 2), "recorded_ad_spend": round(float(row["ad_spend"]), 2),
                          "variance": round(float(row["ad_variance"]), 2), "variance_pct": round(float(pct), 2),
                          "channels": per_channel[["channel", "spend"]].to_dict("records")},
                estimated_impact=abs(float(row["ad_variance"])),
                impact_basis="Profit overstatement equal to the unreported advertising spend for the month.",
                confidence="high", confidence_note="Channel-level spend records are itemised by platform; statement figure is a single reported number.",
                next_action="Request platform billing invoices for the month and the seller's marketing cost schedule; adjust normalised EBITDA.",
                evidence=[Evidence(source_table="seller_statements", source_ref=period, description=f"Seller statement {period}: reported advertising", value=float(row["reported_ad_spend"]))]
                + [Evidence(source_table="ad_spend", source_ref=f"{period}:{r['channel']}", description=f"{r['channel']} spend {period}", value=float(r["spend"]))
                   for _, r in per_channel.iterrows()],
                questions=[Question(
                    question=f"Your {period} accounts show advertising of {ctx.money(row['reported_ad_spend'])}, but platform records total {ctx.money(row['ad_spend'])}. Which channels or invoices are excluded from the reported figure, and why?",
                    rationale="Unreported marketing cost directly overstates profitability and the earnings base.",
                    requested_items="Platform invoices (Meta, Google, TikTok, marketplace) for the month; marketing cost ledger; agency fee schedule.",
                    priority="high")],
            ))

    # ---- ADV-001 ad intensity anomaly (spend / gross sales)
    ratios = fin["ad_pct_of_gross_sales"]
    if ratios.notna().sum() < 6:
        res.skipped.append("Fewer than 6 months with ad spend; ADV-001 (ad intensity anomaly) skipped.")
        return res
    for _, row in fin.iterrows():
        r = row["ad_pct_of_gross_sales"]
        if pd.isna(r):
            continue
        others = ratios[fin["period"] != row["period"]]
        z = robust_z(others, float(r))
        median = float(others.median())
        if z is None or abs(z) < T["ad_ratio_mad_multiplier"] or abs(r - median) < T["ad_ratio_min_pp"]:
            continue
        period = row["period"]
        res.findings.append(Finding(
            rule_id="ADV-001", rule_version=RULES["ADV-001"]["version"], subject=period,
            title=f"Advertising intensity in {period} was {r:.1f}% of gross sales vs {median:.1f}% typical",
            category="Advertising", severity="medium", classification="observation",
            summary=f"Spend {ctx.money(row['ad_spend'])} on gross sales {ctx.money(row['gross_sales'])}.",
            explanation=f"Advertising was {r:.1f}% of gross sales in {period} against a median of {median:.1f}% (robust z {z:+.1f}). "
                        "A sharp change in paid-media intensity changes the quality of the revenue in that month and should be explained.",
            method=f"Ratio = ad spend / gross sales. Flagged when robust z >= {T['ad_ratio_mad_multiplier']} and the deviation is at least {T['ad_ratio_min_pp']}pp.",
            period_start=period, period_end=period,
            measured={"ad_pct_of_gross_sales": round(float(r), 2), "median_pct": round(median, 2), "robust_z": round(z, 2)},
            confidence="medium", confidence_note="Attribution is not inferred; this is an intensity ratio only.",
            next_action="Ask what campaign ran and whether it was tied to a product launch, liquidation or growth test.",
            evidence=[Evidence(source_table="ad_spend", source_ref=period, description=f"Total ad spend {period}", value=float(row["ad_spend"]))],
            questions=[Question(question=f"Why did advertising intensity change to {r:.1f}% of sales in {period}?",
                                rationale="Explains revenue quality in that month.", requested_items="Campaign plan and results.", priority="low")],
        ))
    return res
