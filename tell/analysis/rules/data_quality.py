"""Data coverage checks (DQ-001). Reports gaps that limit other analyses rather than inventing results."""

from __future__ import annotations

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import RULES
from tell.analysis.models import Evidence, Finding, ModuleResult, Question

NAME = "data_quality"


def coverage(ctx: AnalysisContext) -> dict:
    fin = ctx.fin
    periods = fin["period"].tolist() if not fin.empty else []
    stmt_periods = set(ctx.statements["period"]) if not ctx.statements.empty else set()
    ad_periods = set(ctx.ad_spend["period"]) if not ctx.ad_spend.empty else set()
    inv_periods = set(ctx.inventory["snapshot_date"].str[:7]) if not ctx.inventory.empty else set()
    units_without_cost = int(fin["units_without_cost"].sum()) if not fin.empty else 0
    attribution_channels = int(ctx.ad_spend.groupby("channel")["attributed_revenue"].apply(lambda s: s.notna().all()).sum()) if not ctx.ad_spend.empty else 0
    total_channels = int(ctx.ad_spend["channel"].nunique()) if not ctx.ad_spend.empty else 0
    return {
        "order_months": len(periods),
        "statements_missing": [p for p in periods if p not in stmt_periods],
        "ad_spend_missing": [p for p in periods if p not in ad_periods],
        "inventory_missing": [p for p in periods if p not in inv_periods],
        "units_without_cost": units_without_cost,
        "channels_with_attribution": attribution_channels,
        "channels_total": total_channels,
        "has_statements": bool(stmt_periods),
        "has_receipts": not ctx.receipts.empty,
    }


def score(cov: dict) -> tuple[int, str]:
    """0-100 coverage score with a label. Purely descriptive."""
    if not cov or cov["order_months"] == 0:
        return 0, "No data"
    n = cov["order_months"]
    parts = [1 - len(cov["statements_missing"]) / n, 1 - len(cov["ad_spend_missing"]) / n, 1 - len(cov["inventory_missing"]) / n,
             1.0 if cov["units_without_cost"] == 0 else 0.5, 1.0 if cov["has_receipts"] else 0.5]
    s = int(round(sum(parts) / len(parts) * 100))
    return s, "Complete" if s >= 95 else "Good" if s >= 80 else "Partial" if s >= 50 else "Limited"


def run(ctx: AnalysisContext) -> ModuleResult:
    res = ModuleResult(module=NAME)
    cov = coverage(ctx)
    gaps = []
    if cov["statements_missing"]:
        gaps.append(f"seller statements missing for {len(cov['statements_missing'])} month(s)")
    if cov["ad_spend_missing"]:
        gaps.append(f"advertising records missing for {len(cov['ad_spend_missing'])} month(s)")
    if cov["inventory_missing"]:
        gaps.append(f"inventory snapshots missing for {len(cov['inventory_missing'])} month(s)")
    if cov["units_without_cost"]:
        gaps.append(f"{cov['units_without_cost']} units sold without any unit cost (excluded from COGS)")
    if not gaps:
        res.notes.append("All source datasets cover the full order period.")
        return res
    res.findings.append(Finding(
        rule_id="DQ-001", rule_version=RULES["DQ-001"]["version"], subject="coverage",
        title="Source data gaps limit parts of the analysis", category="Data quality", severity="low", classification="observation",
        summary="; ".join(gaps) + ".",
        explanation="The following gaps were found: " + "; ".join(gaps) + ". Analyses depending on the missing data were skipped or are partial; no values were imputed.",
        method="Compare the set of months with orders against months covered by each other dataset.",
        period_start=ctx.period_start, period_end=ctx.period_end, measured=cov, confidence="high",
        next_action="Request the missing records from the seller before relying on affected analyses.",
        evidence=[Evidence(source_table="import_files", description=g) for g in gaps],
        questions=[Question(question="Please provide the missing records: " + "; ".join(gaps) + ".", rationale="Incomplete data prevents full reconciliation.", requested_items="The missing monthly files.", priority="medium")],
    ))
    return res
