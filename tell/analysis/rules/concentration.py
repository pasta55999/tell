"""Revenue concentration and dependency (CON-001, CON-002)."""

from __future__ import annotations

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES, THRESHOLDS as T
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "concentration"


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    products = ctx.products
    if products.empty:
        res.skipped.append("No product sales; concentration analysis skipped.")
        return res
    top = products.iloc[0]
    top3 = products.head(3)
    top3_share = float(top3["revenue_share_pct"].sum())
    res.notes.append(f"Top SKU share {top['revenue_share_pct']:.1f}%, top-3 share {top3_share:.1f}% over {ctx.period_start}..{ctx.period_end}.")

    if top["revenue_share_pct"] >= T["concentration_top1_pct"] or top3_share >= T["concentration_top3_pct"]:
        # how has the top SKU's share moved over time?
        pm = ctx.product_monthly
        trend = []
        if not pm.empty:
            tot = pm.groupby("period")["gross_sales"].sum()
            sku_m = pm[pm["sku"] == top["sku"]].set_index("period")["gross_sales"]
            trend = [{"period": p, "share_pct": round(float(sku_m.get(p, 0) / tot[p] * 100), 1)} for p in tot.index]
        res.findings.append(Finding(
            rule_id="CON-001", rule_version=RULES["CON-001"]["version"], subject=top["sku"],
            title=f"{top['sku']} {top['name']} generates {top['revenue_share_pct']:.0f}% of gross sales",
            category="Concentration", severity="high" if top["revenue_share_pct"] >= 35 else "medium", classification="suspected_risk",
            summary=f"Top-3 SKUs account for {top3_share:.0f}% of gross sales; {int(len(products))} SKUs in total.",
            explanation=(
                f"Over {ctx.period_start}..{ctx.period_end}, {top['sku']} ({top['name']}) produced {ctx.money(top['gross_sales'])} of gross sales, "
                f"{top['revenue_share_pct']:.1f}% of the total, and the three largest SKUs together produced {top3_share:.1f}%. "
                "A single-product dependency magnifies the effect of a supply interruption, quality issue, marketplace delisting or competitor copy. "
                f"The SKU's gross margin is {top['gross_margin_pct']:.1f}% and its return rate {top['return_rate_pct']:.1f}%."
            ),
            method=f"Share = SKU gross sales / total gross sales (completed orders, after discounts). Flagged when the top SKU >= {T['concentration_top1_pct']}% or top-3 >= {T['concentration_top3_pct']}%.",
            period_start=ctx.period_start, period_end=ctx.period_end,
            measured={"top_sku": top["sku"], "top_share_pct": round(float(top["revenue_share_pct"]), 2), "top3_share_pct": round(top3_share, 2),
                      "top3": top3[["sku", "name", "gross_sales", "revenue_share_pct"]].round(2).to_dict("records"), "share_trend": trend},
            estimated_impact=float(top["gross_sales"] - top["cogs"]),
            impact_basis="Gross profit at risk if the SKU were lost (annualised to the observation period). Not a probability-weighted loss.",
            confidence="high", confidence_note="Direct share calculation; no assumptions beyond the observation window.",
            next_action="Assess supplier contracts, IP/brand protection and the pipeline of products that could reduce reliance on this SKU.",
            evidence=[Evidence(source_table="products", source_id=int(r["product_id"]), source_ref=r["sku"],
                               description=f"{r['sku']} {r['name']}: gross sales ({r['revenue_share_pct']:.1f}%)", value=float(r["gross_sales"]))
                      for _, r in top3.iterrows()],
            questions=[Question(
                question=f"{top['sku']} drives {top['revenue_share_pct']:.0f}% of sales. What supply, IP and channel protections exist for it, and what is the plan to diversify?",
                rationale="Concentration risk affects valuation multiples and deal structure (e.g., earn-outs).",
                requested_items="Supplier agreement and exclusivity terms; trademark/design registrations; new product pipeline with launch dates.",
                priority="medium")],
        ))

    cats = ctx.categories
    if not cats.empty and cats.iloc[0]["revenue_share_pct"] >= T["concentration_category_pct"]:
        c = cats.iloc[0]
        res.findings.append(Finding(
            rule_id="CON-002", rule_version=RULES["CON-002"]["version"], subject=str(c["category"]),
            title=f"{c['category']} category generates {c['revenue_share_pct']:.0f}% of gross sales",
            category="Concentration", severity="medium", classification="suspected_risk",
            summary=f"{int(c['skus'])} SKUs in {c['category']} produce {ctx.money(c['gross_sales'])}.",
            explanation=f"The {c['category']} category represents {c['revenue_share_pct']:.1f}% of gross sales over the observation period.",
            method=f"Share = category gross sales / total gross sales. Flagged when >= {T['concentration_category_pct']}%.",
            period_start=ctx.period_start, period_end=ctx.period_end,
            measured={"category": c["category"], "share_pct": round(float(c["revenue_share_pct"]), 2)},
            confidence="high", next_action="Review category-level competitive dynamics.",
            evidence=[Evidence(source_table="products", source_ref=str(c["category"]), description=f"{c['category']} gross sales", value=float(c["gross_sales"]))],
            questions=[Question(question=f"What is the strategy to reduce dependence on the {c['category']} category?",
                                rationale="Category concentration.", requested_items="Category plan.", priority="low")],
        ))
    return res
