"""Runs all analysis modules against a brand and persists a reproducible analysis run."""

from __future__ import annotations

import json
import sqlite3
import traceback
from datetime import datetime, timezone

from tell.analysis.context import AnalysisContext
from tell.analysis.conventions import ENGINE_VERSION, rule_versions
from tell.analysis.models import Finding, ModuleResult
from tell.analysis.rules import MODULES
from tell.db import repository as repo
from tell.db.connection import transaction


def analyse(conn: sqlite3.Connection, brand_id: int) -> tuple[list[Finding], list[str], list[str]]:
    """Run every module in memory. Returns (findings, skipped, notes)."""
    ctx = AnalysisContext(conn, brand_id)
    findings: list[Finding] = []
    skipped: list[str] = []
    notes: list[str] = []
    for module in MODULES:
        result: ModuleResult = module.run(ctx)
        findings.extend(result.findings)
        skipped.extend(result.skipped)
        notes.extend(result.notes)
    findings.sort(key=lambda f: f.finding_key)
    return findings, skipped, notes


def run_analysis(conn: sqlite3.Connection, brand_id: int, label: str | None = None) -> int:
    """Execute the analysis and store the run, findings, evidence and questions. Returns run id."""
    from tell.analysis.questions import build_questions

    snapshot, data_hash = repo.data_snapshot(conn, brand_id)
    versions = rule_versions()
    with transaction(conn):
        cur = conn.execute(
            """INSERT INTO analysis_runs(brand_id, status, data_snapshot, data_hash, rule_versions, engine_version, label)
               VALUES (?, 'running', ?, ?, ?, ?, ?)""",
            (brand_id, json.dumps(snapshot), data_hash, json.dumps(versions), ENGINE_VERSION, label),
        )
        run_id = int(cur.lastrowid)
    try:
        findings, skipped, notes = analyse(conn, brand_id)
        with transaction(conn):
            for f in findings:
                fcur = conn.execute(
                    """INSERT INTO findings(run_id, finding_key, rule_id, rule_version, subject, title, category, severity, status, classification,
                                            summary, explanation, method, period_start, period_end, measured, estimated_impact, impact_basis,
                                            confidence, confidence_note, next_action)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, f.finding_key, f.rule_id, f.rule_version, f.subject, f.title, f.category, f.severity, f.status, f.classification,
                     f.summary, f.explanation, f.method, f.period_start, f.period_end, json.dumps(f.measured, default=str),
                     f.estimated_impact, f.impact_basis, f.confidence, f.confidence_note, f.next_action),
                )
                finding_id = int(fcur.lastrowid)
                conn.executemany(
                    "INSERT INTO finding_evidence(finding_id, source_table, source_id, source_ref, description, value, extra) VALUES (?,?,?,?,?,?,?)",
                    [(finding_id, e.source_table, e.source_id, e.source_ref, e.description, e.value, json.dumps(e.extra, default=str) if e.extra else None)
                     for e in f.evidence],
                )
                for i, q in enumerate(f.questions):
                    conn.execute(
                        """INSERT INTO diligence_questions(run_id, finding_id, question_key, question, rationale, evidence_note, requested_items, priority)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (run_id, finding_id, f"{f.finding_key}#{i}", q.question, q.rationale, f.summary, q.requested_items, q.priority),
                    )
            for q in build_questions(findings):
                conn.execute(
                    """INSERT OR IGNORE INTO diligence_questions(run_id, finding_id, question_key, question, rationale, evidence_note, requested_items, priority)
                       VALUES (?, NULL, ?, ?, ?, ?, ?, ?)""",
                    (run_id, q["key"], q["question"], q["rationale"], q.get("evidence_note"), q["requested_items"], q["priority"]),
                )
            conn.execute(
                "UPDATE analysis_runs SET status='completed', finished_at=?, finding_count=?, skipped=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), len(findings), json.dumps({"skipped": skipped, "notes": notes}), run_id),
            )
    except Exception as exc:  # pragma: no cover - defensive
        conn.execute("UPDATE analysis_runs SET status='failed', finished_at=?, error=? WHERE id=?",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"), f"{exc}\n{traceback.format_exc()}", run_id))
        raise
    return run_id


def update_finding_status(conn: sqlite3.Connection, finding_id: int, status: str, note: str | None = None) -> None:
    if status not in ("detected", "needs_investigation", "verified", "dismissed"):
        raise ValueError("invalid status")
    conn.execute("UPDATE findings SET status = ?, analyst_note = COALESCE(?, analyst_note) WHERE id = ?", (status, note, finding_id))


def update_question_status(conn: sqlite3.Connection, question_id: int, status: str, note: str | None = None) -> None:
    if status not in ("pending", "answered", "resolved"):
        raise ValueError("invalid status")
    conn.execute("UPDATE diligence_questions SET status = ?, answer_note = COALESCE(?, answer_note) WHERE id = ?", (status, note, question_id))


def compare_runs(conn: sqlite3.Connection, base_run_id: int, new_run_id: int) -> dict:
    """Diff findings between two runs by stable finding_key. Reports new, resolved and
    changed findings. 'Changed' means severity or estimated impact differ; nothing is
    inferred about whether the business improved."""
    base = {r["finding_key"]: dict(r) for _, r in repo.findings_for_run(conn, base_run_id).iterrows()}
    new = {r["finding_key"]: dict(r) for _, r in repo.findings_for_run(conn, new_run_id).iterrows()}
    added = [new[k] for k in new.keys() - base.keys()]
    resolved = [base[k] for k in base.keys() - new.keys()]
    changed, unchanged = [], []
    for k in base.keys() & new.keys():
        b, n = base[k], new[k]
        bi, ni = b.get("estimated_impact"), n.get("estimated_impact")
        impact_changed = (bi is None) != (ni is None) or (bi is not None and ni is not None and abs(float(bi) - float(ni)) > 0.5)
        if b["severity"] != n["severity"] or impact_changed:
            changed.append({"finding_key": k, "title": n["title"], "severity_before": b["severity"], "severity_after": n["severity"],
                            "impact_before": bi, "impact_after": ni})
        else:
            unchanged.append(n)
    base_run, new_run = repo.get_run(conn, base_run_id), repo.get_run(conn, new_run_id)
    return {
        "base_run": dict(base_run) if base_run else None, "new_run": dict(new_run) if new_run else None,
        "same_data": bool(base_run and new_run and base_run["data_hash"] == new_run["data_hash"]),
        "same_rules": bool(base_run and new_run and base_run["rule_versions"] == new_run["rule_versions"]),
        "new": sorted(added, key=lambda f: f["finding_key"]), "resolved": sorted(resolved, key=lambda f: f["finding_key"]),
        "changed": sorted(changed, key=lambda f: f["finding_key"]), "unchanged_count": len(unchanged),
    }
