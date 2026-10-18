"""Analyst copilot intents, report generation and exports, no-API-key operation."""

from __future__ import annotations

import json
import os

import pytest

from tell.copilot import ask, supported_questions
from tell.copilot.copilot import classify
from tell.copilot.adapters import NullAdapter
from tell.reports import build_report, findings_csv, questions_csv, reconciliation_csv, report_json, report_pdf, save_report


@pytest.mark.parametrize("question,intent", [
    ("Why did reported revenue differ from order-derived revenue?", "revenue_variance"),
    ("Which products have the highest refund exposure?", "refund_exposure"),
    ("What is driving the margin decline?", "margin_decline"),
    ("Which findings should I investigate first?", "prioritise"),
    ("What evidence supports finding REV-001:2025-07?", "evidence"),
    ("What questions should I ask the seller?", "seller_questions"),
    ("What is the ROAS by channel?", "advertising"),
    ("How concentrated is revenue?", "concentration"),
    ("Are there inventory discrepancies?", "inventory"),
    ("Is the November spike suspicious?", "seasonality"),
    ("What happened in 2025-10?", "month_detail"),
    ("How is the business performing?", "performance"),
])
def test_intent_classification(question, intent):
    assert classify(question) == intent


def test_all_supported_questions_answer_with_data(demo_conn, brand_id, run_id):
    for q in supported_questions():
        a = ask(demo_conn, brand_id, q, run_id)
        assert a.supported and len(a.text) > 40, q
        assert "language model" in a.engine or "Rule-based" in a.engine


def test_revenue_answer_uses_database_values(demo_conn, brand_id, run_id):
    a = ask(demo_conn, brand_id, "Why did reported revenue differ?", run_id)
    assert "2025-07" in a.text and "refunds" in a.text and "cancelled" in a.text
    assert "REV-001:2025-07" in a.related_findings
    assert a.table is not None and "revenue_variance" in a.table.columns


def test_roas_not_fabricated(demo_conn, brand_id, run_id):
    a = ask(demo_conn, brand_id, "What is the ROAS?", run_id)
    assert "Meta" in a.text and "not computable" in a.text
    assert "does not infer attribution" in a.text


def test_unsupported_question_is_declined(demo_conn, brand_id, run_id):
    a = ask(demo_conn, brand_id, "Should we buy this company for 20 million?", run_id)
    assert not a.supported and a.intent == "unsupported" and "Try one of" in a.text


def test_evidence_intent_lists_source_rows(demo_conn, brand_id, run_id):
    a = ask(demo_conn, brand_id, "Show me the evidence for REF-002:2025-10", run_id)
    assert "[refunds #" in a.text and len(a.evidence) >= 40


def test_month_detail_parses_month_names(demo_conn, brand_id, run_id):
    a = ask(demo_conn, brand_id, "How did we do in October 2025?", run_id)
    assert a.intent == "month_detail" and "2025-10" in a.text


def test_copilot_without_run(demo_conn, brand_id):
    from tell.db.connection import open_db
    from tell.data.demo_generator import generate_demo
    conn = open_db(":memory:")
    b = generate_demo(conn)
    a = ask(conn, b, "Which findings should I investigate first?")
    assert a.supported and "Run the analysis" in a.text


def test_null_adapter_does_not_change_text():
    assert NullAdapter().rephrase("x") == "x" and NullAdapter().classify_intent("q", ["a"]) is None


# ------------------------------------------------------------------ reports

def test_report_structure_and_exports(demo_conn, run_id, tmp_path):
    rep = build_report(demo_conn, run_id)
    for section in ["meta", "executive_summary", "performance", "reconciliation", "findings", "questions", "methodology", "data_limitations", "next_steps"]:
        assert section in rep
    assert rep["meta"]["is_demo"] and "SYNTHETIC" in rep["meta"]["disclaimer"]
    assert rep["reconciliation"]["months_breaching_threshold"] == 3
    assert all(f["evidence"] for f in rep["findings"])
    pdf = report_pdf(rep)
    assert pdf[:4] == b"%PDF" and len(pdf) > 10000
    (tmp_path / "r.pdf").write_bytes(pdf)
    js = json.loads(report_json(rep))
    assert js["meta"]["run_id"] == run_id
    assert findings_csv(rep).splitlines()[0].startswith("finding_key,severity")
    assert len(reconciliation_csv(rep).splitlines()) == 13
    assert "question" in questions_csv(rep).splitlines()[0]


def test_report_versions_persist(demo_conn, run_id):
    rep = build_report(demo_conn, run_id)
    v1 = save_report(demo_conn, run_id, rep)
    v2 = save_report(demo_conn, run_id, rep)
    assert v2 == v1 + 1
    stored = json.loads(demo_conn.execute("SELECT content_json FROM reports WHERE run_id=? AND version=?", (run_id, v2)).fetchone()[0])
    assert stored["executive_summary"]["headline"] == rep["executive_summary"]["headline"]


def test_impact_total_only_sums_discrepancies(demo_conn, run_id):
    rep = build_report(demo_conn, run_id)
    disc = sum((f["estimated_impact"] or 0) for f in rep["findings"] if f["classification"] == "discrepancy" and f["severity"] in ("critical", "high", "medium"))
    assert f"{disc:,.0f}" in rep["executive_summary"]["headline"]


def test_no_api_keys_needed():
    assert not any(k in os.environ for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"))
    import tell.analysis.engine, tell.copilot, tell.reports, tell.ingest  # noqa: F401 - importable with no network/keys
