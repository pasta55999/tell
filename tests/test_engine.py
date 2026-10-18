"""Planted-anomaly detection, hard negative, evidence traceability, reproducibility and run comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tell.analysis.engine import analyse, compare_runs, run_analysis, update_finding_status, update_question_status
from tell.data.demo_generator import generate_demo
from tell.db import repository as repo
from tell.db.connection import open_db

GT = json.loads((Path(__file__).resolve().parent.parent / "data" / "demo" / "ground_truth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def findings(demo_conn, brand_id):
    f, skipped, notes = analyse(demo_conn, brand_id)
    return {x.finding_key: x for x in f}


@pytest.mark.parametrize("scenario", [s for s in GT["scenarios"]], ids=[s["id"] for s in GT["scenarios"]])
def test_planted_scenario_detected(findings, scenario):
    hits = [k for k in scenario["primary"] if k in findings]
    assert hits, f"{scenario['id']} not detected; produced {sorted(findings)}"
    for k in hits:
        assert findings[k].severity == scenario["expected_severity"], (k, findings[k].severity)
        assert findings[k].classification == scenario["expected_classification"]


def test_seasonal_spike_is_hard_negative(findings):
    s9 = next(s for s in GT["scenarios"] if s["id"] == "S9")
    for key in s9["must_not_flag"]:
        assert key not in findings, f"{key} wrongly raised on the legitimate seasonal month"
    nov = findings["SEA-001:2025-11"]
    assert nov.severity == "info" and nov.classification == "observation"
    assert nov.measured["checks"]["volume_driven"] and nov.measured["checks"]["aov_stable"]


def test_no_unexpected_findings(findings):
    acceptable = set()
    for s in GT["scenarios"]:
        acceptable |= set(s["primary"]) | set(s.get("secondary", []))
    assert set(findings) <= acceptable, set(findings) - acceptable


def test_revenue_variance_attributed_to_refunds_and_cancellations(findings):
    f = findings["REV-001:2025-07"]
    assert "refunds" in f.measured["attribution"] and "cancelled" in f.measured["attribution"]
    assert abs(f.measured["attribution_residual"]) < 1.0
    assert f.estimated_impact == pytest.approx(abs(f.measured["variance"]))


def test_every_finding_has_evidence_and_required_fields(findings):
    for k, f in findings.items():
        assert f.evidence, f"{k} has no evidence"
        assert f.title and f.summary and f.explanation and f.method and f.next_action
        assert f.questions, f"{k} has no diligence question"
        assert f.rule_id and f.rule_version and f.confidence
        for e in f.evidence:
            assert e.source_table and e.description


def test_evidence_rows_reference_real_records(demo_conn, run_id):
    ev = repo.fetch_df(demo_conn, "SELECT source_table, source_id FROM finding_evidence e JOIN findings f ON f.id = e.finding_id WHERE f.run_id = ? AND e.source_id IS NOT NULL", (run_id,))
    assert len(ev) > 50
    for table, grp in ev.groupby("source_table"):
        ids = [int(i) for i in grp["source_id"]]
        marks = ",".join("?" * len(ids))
        found = repo.scalar(demo_conn, f"SELECT COUNT(*) FROM {table} WHERE id IN ({marks})", ids)  # noqa: S608 - table from evidence
        assert found == len(set(ids)), f"dangling evidence in {table}"


def test_run_is_persisted_with_traceability(demo_conn, brand_id, run_id):
    run = repo.get_run(demo_conn, run_id)
    assert run["status"] == "completed" and run["finished_at"]
    snap = json.loads(run["data_snapshot"])
    assert snap["counts"]["orders"] >= 1000 and run["data_hash"] == snap["hash"]
    assert "REV-001" in json.loads(run["rule_versions"])
    df = repo.findings_for_run(demo_conn, run_id)
    assert len(df) == run["finding_count"] > 0
    assert (df["evidence_count"] > 0).all()
    qs = repo.questions_for_run(demo_conn, run_id)
    assert len(qs) >= len(df)
    assert qs["finding_id"].isna().sum() >= 2     # consolidated questions


def test_repeated_run_is_identical(demo_conn, brand_id, run_id):
    second = run_analysis(demo_conn, brand_id)
    cmp = compare_runs(demo_conn, run_id, second)
    assert cmp["same_data"] and cmp["same_rules"]
    assert cmp["new"] == [] and cmp["resolved"] == [] and cmp["changed"] == []
    a = repo.findings_for_run(demo_conn, run_id)[["finding_key", "severity", "estimated_impact", "measured"]].reset_index(drop=True)
    b = repo.findings_for_run(demo_conn, second)[["finding_key", "severity", "estimated_impact", "measured"]].reset_index(drop=True)
    assert a.equals(b)


def test_compare_runs_detects_resolved_and_new():
    conn = open_db(":memory:")
    b = generate_demo(conn)
    base = run_analysis(conn, b)
    # "Seller corrects" the September advertising statement -> ADV-002 should resolve
    actual = repo.scalar(conn, "SELECT SUM(spend) FROM ad_spend WHERE brand_id=? AND period='2025-09'", (b,))
    conn.execute("UPDATE seller_statements SET reported_ad_spend = ? WHERE brand_id=? AND period='2025-09'", (actual, b))
    # New data: a negative stock snapshot -> INV-002 should appear
    conn.execute("UPDATE inventory_snapshots SET quantity_on_hand = -5 WHERE id = (SELECT MIN(id) FROM inventory_snapshots WHERE brand_id=? AND snapshot_date='2025-12-31')", (b,))
    new = run_analysis(conn, b)
    cmp = compare_runs(conn, base, new)
    assert not cmp["same_data"]
    assert "ADV-002:2025-09" in {f["finding_key"] for f in cmp["resolved"]}
    assert any(k["finding_key"].startswith("INV-002") for k in cmp["new"])


def test_status_updates(demo_conn, run_id):
    fid = int(repo.findings_for_run(demo_conn, run_id)["id"].iloc[0])
    update_finding_status(demo_conn, fid, "needs_investigation", "called the seller")
    f = repo.get_finding(demo_conn, fid)
    assert f["status"] == "needs_investigation" and f["analyst_note"] == "called the seller"
    with pytest.raises(ValueError):
        update_finding_status(demo_conn, fid, "confirmed_fraud")
    qid = int(repo.questions_for_run(demo_conn, run_id)["id"].iloc[0])
    update_question_status(demo_conn, qid, "answered", "policy received")
    assert repo.fetch_one(demo_conn, "SELECT status FROM diligence_questions WHERE id=?", (qid,))["status"] == "answered"


def test_missing_inputs_are_reported_not_invented():
    conn = open_db(":memory:")
    b = generate_demo(conn)
    conn.execute("DELETE FROM seller_statements WHERE brand_id=?", (b,))
    conn.execute("DELETE FROM inventory_snapshots WHERE brand_id=?", (b,))
    conn.execute("DELETE FROM supplier_receipts WHERE brand_id=?", (b,))
    findings, skipped, notes = analyse(conn, b)
    keys = {f.finding_key for f in findings}
    assert not any(k.startswith(("REV-001", "ADV-002", "INV-")) for k in keys)
    assert any("REV-001" in s for s in skipped) and any("INV-001" in s for s in skipped) and any("INV-003" in s for s in skipped)
    assert "DQ-001:coverage" in keys


def test_engine_runs_on_empty_brand(fresh_conn):
    fresh_conn.execute("INSERT INTO workspaces(name) VALUES ('w')")
    fresh_conn.execute("INSERT INTO brands(workspace_id, slug, name) VALUES (1, 'empty', 'Empty')")
    rid = run_analysis(fresh_conn, 1)
    run = repo.get_run(fresh_conn, rid)
    assert run["status"] == "completed" and run["finding_count"] == 0
