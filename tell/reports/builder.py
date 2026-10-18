"""Assemble a structured diligence report from a stored analysis run."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from tell import __version__
from tell.analysis import metrics
from tell.analysis.conventions import DEFINITIONS
from tell.analysis.rules.data_quality import coverage, score
from tell.analysis.context import AnalysisContext
from tell.db import repository as repo


def _records(df: pd.DataFrame, cols: list[str] | None = None) -> list[dict]:
    if df.empty:
        return []
    d = df[cols] if cols else df
    return json.loads(d.to_json(orient="records", date_format="iso"))


def build_report(conn: sqlite3.Connection, run_id: int) -> dict:
    run = repo.get_run(conn, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    brand = repo.get_brand(conn, run["brand_id"])
    brand_id = int(brand["id"])
    cur = brand["reporting_currency"]
    fin = metrics.monthly_financials(conn, brand_id)
    totals = metrics.period_totals(fin)
    findings = repo.findings_for_run(conn, run_id)
    questions = repo.questions_for_run(conn, run_id)
    products = metrics.product_table(conn, brand_id)
    ctx = AnalysisContext(conn, brand_id)
    cov = coverage(ctx)
    cov_score, cov_label = score(cov)
    skipped = json.loads(run["skipped"]) if run["skipped"] else {"skipped": [], "notes": []}

    material = findings[(findings["classification"] != "observation") & (findings["severity"].isin(["critical", "high", "medium"]))]
    sev_counts = findings["severity"].value_counts().to_dict() if not findings.empty else {}
    # Only sum impacts of the same kind: quantified discrepancies (reported vs supported values).
    # Suspected-risk impacts (e.g. gross profit exposed to a concentrated SKU) are not additive.
    discrepancies = material[material["classification"] == "discrepancy"] if not material.empty else material
    total_impact = float(discrepancies["estimated_impact"].fillna(0).sum()) if not discrepancies.empty else 0.0

    rec_months = fin[fin["reported_revenue"].notna()] if not fin.empty else fin
    breaches = findings[findings["rule_id"] == "REV-001"] if not findings.empty else pd.DataFrame()

    def finding_dict(r: pd.Series) -> dict:
        ev = repo.evidence_for_finding(conn, int(r["id"]))
        qs = repo.questions_for_finding(conn, int(r["id"]))
        return {
            "id": int(r["id"]), "finding_key": r["finding_key"], "rule_id": r["rule_id"], "rule_version": r["rule_version"],
            "title": r["title"], "category": r["category"], "severity": r["severity"], "status": r["status"], "classification": r["classification"],
            "summary": r["summary"], "explanation": r["explanation"], "method": r["method"], "period_start": r["period_start"], "period_end": r["period_end"],
            "measured": json.loads(r["measured"]) if r["measured"] else {}, "estimated_impact": r["estimated_impact"], "impact_basis": r["impact_basis"],
            "confidence": r["confidence"], "confidence_note": r["confidence_note"], "next_action": r["next_action"], "analyst_note": r["analyst_note"],
            "evidence": _records(ev, ["source_table", "source_id", "source_ref", "description", "value"]),
            "questions": _records(qs, ["question", "rationale", "requested_items", "priority", "status"]),
        }

    exec_summary = _executive_summary(brand["name"], cur, totals, findings, material, total_impact, breaches, rec_months)
    return {
        "meta": {
            "product": "Tell", "version": __version__, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "brand": brand["name"], "brand_slug": brand["slug"], "is_demo": bool(brand["is_demo"]), "currency": cur,
            "run_id": run_id, "run_started_at": run["started_at"], "run_finished_at": run["finished_at"], "data_hash": run["data_hash"],
            "engine_version": run["engine_version"], "rule_versions": json.loads(run["rule_versions"]),
            "disclaimer": "Decision-support output generated from the records provided. Findings are detected discrepancies or suspected risks, not confirmed facts, until verified with the seller. "
                          + ("This report is based on a SYNTHETIC demo dataset and does not describe any real company." if brand["is_demo"] else ""),
        },
        "executive_summary": exec_summary,
        "performance": {"totals": totals, "monthly": _records(fin.round(2)) if not fin.empty else [],
                        "top_products": _records(products.head(10).round(2), ["sku", "name", "category", "units", "gross_sales", "revenue_share_pct", "gross_margin_pct", "return_rate_pct"])},
        "reconciliation": {
            "months_reported": int(len(rec_months)), "months_breaching_threshold": int(len(breaches)),
            "reported_revenue_total": totals.get("reported_revenue"), "net_sales_total": float(rec_months["net_sales"].sum()) if not rec_months.empty else None,
            "variance_total": totals.get("revenue_variance"),
            "monthly": _records(rec_months[["period", "reported_revenue", "gms", "discounts", "gross_sales", "refunds_posted", "cancelled_value", "net_sales", "revenue_variance", "revenue_variance_pct", "reported_ad_spend", "ad_spend", "ad_variance_pct"]].round(2)) if not rec_months.empty else [],
        },
        "findings": [finding_dict(r) for _, r in findings.iterrows()],
        "severity_counts": sev_counts,
        "questions": _records(questions, ["priority", "question", "rationale", "requested_items", "status", "finding_key"]),
        "methodology": {"definitions": DEFINITIONS, "notes": skipped.get("notes", [])},
        "data_limitations": {"coverage": cov, "coverage_score": cov_score, "coverage_label": cov_label, "skipped_analyses": skipped.get("skipped", []),
                             "general": ["Unit costs are as recorded by the seller; landed cost components may be missing.",
                                         "Refunds are assigned to posting month; cohort views are shown separately.",
                                         "ROAS is only reported for channels with platform-attributed revenue.",
                                         "Contribution proxy excludes fulfilment, payroll, payment fees and overheads and is not EBITDA."]},
        "next_steps": _next_steps(material, questions),
    }


def _executive_summary(name: str, cur: str, t: dict, findings: pd.DataFrame, material: pd.DataFrame, total_impact: float, breaches: pd.DataFrame, rec: pd.DataFrame) -> dict:
    if not t:
        return {"headline": "No order data available.", "bullets": []}
    bullets = [
        f"{name} generated gross sales of {cur} {t['gross_sales']:,.0f} and net sales of {cur} {t['net_sales']:,.0f} over {t['months']} months ({t['period_start']} to {t['period_end']}) from {t['orders_completed']:,} completed orders.",
        f"Gross margin was {t['gross_margin_pct']:.1f}%; advertising absorbed {t['ad_pct_of_gross_sales']:.1f}% of gross sales, leaving a contribution proxy of {cur} {t['contribution_proxy']:,.0f} before fulfilment and overheads.",
    ]
    if not rec.empty:
        var = t.get("revenue_variance") or 0
        bullets.append(f"Seller-reported revenue totals {cur} {t['reported_revenue']:,.0f} versus {cur} {rec['net_sales'].sum():,.0f} supported by order records ({var:+,.0f}; {len(breaches)} month(s) breach the 2% threshold).")
    if not findings.empty:
        hi = material[material["severity"].isin(["critical", "high"])]
        n_disc = int((material["classification"] == "discrepancy").sum())
        bullets.append(f"{len(material)} material findings were detected ({len(hi)} high or critical): {n_disc} quantified discrepancies totalling {cur} {total_impact:,.0f} "
                       f"and {len(material) - n_disc} suspected risks; {int((findings['classification'] == 'observation').sum())} further item(s) are informational observations.")
        for _, r in material.head(3).iterrows():
            bullets.append(f"[{r['severity']}] {r['title']}: {r['summary']}")
    headline = (f"{len(material)} material findings; quantified discrepancies of {cur} {total_impact:,.0f}" if not material.empty else "No material findings detected")
    return {"headline": headline, "bullets": bullets}


def _next_steps(material: pd.DataFrame, questions: pd.DataFrame) -> list[str]:
    steps = []
    if not material.empty:
        for _, r in material.head(5).iterrows():
            if r["next_action"]:
                steps.append(r["next_action"])
    if not questions.empty:
        steps.append(f"Send the {int((questions['priority'] == 'high').sum())} high-priority seller questions and track responses in the Seller Questions view.")
    steps.append("Re-run the analysis after the seller provides additional records and compare runs to confirm which findings are resolved.")
    return steps


def save_report(conn: sqlite3.Connection, run_id: int, content: dict) -> int:
    version = int(repo.scalar(conn, "SELECT COALESCE(MAX(version), 0) + 1 FROM reports WHERE run_id = ?", (run_id,)))
    title = f"{content['meta']['brand']} - Acquisition diligence report (run {run_id}, v{version})"
    conn.execute("INSERT INTO reports(run_id, version, title, content_json) VALUES (?,?,?,?)", (run_id, version, title, json.dumps(content, default=str)))
    return version
