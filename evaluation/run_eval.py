"""Evaluate the analysis engine against the labelled demo dataset.

Usage: python -m evaluation.run_eval [--write]

Definitions
-----------
Scenario recall   = planted scenarios with at least one *primary* expected finding key present
                    / total planted scenarios (the hard-negative S9 counts as detected when SEA-001:2025-11
                    is raised as an observation with severity 'info').
Finding precision = findings whose key appears in any scenario's primary or secondary list
                    / all findings produced (observations included).
Finding recall    = primary keys produced / primary keys expected (key-level).
F1                = harmonic mean of key-level precision and recall.
Hard negative     = S9 passes only if no 'must_not_flag' key is produced and SEA-001:2025-11 is not
                    raised with severity in must_not_be_severity.

Also runs value-level correctness checks: reconciliation identities on the generated data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tell.analysis import metrics
from tell.analysis.engine import analyse
from tell.data.demo_generator import generate_demo
from tell.db import repository as repo
from tell.db.connection import open_db

ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / "data" / "demo" / "ground_truth.json"


def evaluate(conn=None) -> dict:
    conn = conn or open_db(":memory:")
    brand_id = generate_demo(conn)
    findings, skipped, notes = analyse(conn, brand_id)
    produced = {f.finding_key: f for f in findings}
    gt = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))

    primary_expected: set[str] = set()
    acceptable: set[str] = set()
    scenario_rows = []
    for s in gt["scenarios"]:
        primary_expected |= set(s["primary"])
        acceptable |= set(s["primary"]) | set(s.get("secondary", []))
        hits = [k for k in s["primary"] if k in produced]
        detected = bool(hits)
        hard_neg_ok = None
        if s.get("must_not_flag"):
            violations = [k for k in s["must_not_flag"] if k in produced]
            bad_sev = [k for k in s["primary"] if k in produced and produced[k].severity in s.get("must_not_be_severity", [])]
            hard_neg_ok = not violations and not bad_sev
            detected = detected and hard_neg_ok
        sev_match = all(produced[k].severity == s["expected_severity"] for k in hits) if hits else False
        cls_match = all(produced[k].classification == s["expected_classification"] for k in hits) if hits else False
        scenario_rows.append({"id": s["id"], "name": s["name"], "detected": detected, "hits": hits, "expected_severity": s["expected_severity"],
                              "produced_severity": [produced[k].severity for k in hits], "severity_match": sev_match, "classification_match": cls_match,
                              "hard_negative_ok": hard_neg_ok})

    produced_keys = set(produced)
    tp_keys = produced_keys & acceptable
    fp_keys = sorted(produced_keys - acceptable)
    fn_keys = sorted(primary_expected - produced_keys)
    precision = len(tp_keys) / len(produced_keys) if produced_keys else 0.0
    recall = len(primary_expected & produced_keys) / len(primary_expected) if primary_expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    scenario_recall = sum(r["detected"] for r in scenario_rows) / len(scenario_rows)

    # Value-level correctness checks on the generated data
    fin = metrics.monthly_financials(conn, brand_id)
    checks = {}
    orders_net = float(repo.scalar(conn, "SELECT SUM(net_amount) FROM orders WHERE brand_id=? AND status='completed'", (brand_id,)))
    checks["gross_sales_equals_sum_of_completed_order_net"] = abs(fin["gross_sales"].sum() - orders_net) < 0.01
    lines = float(repo.scalar(conn, """SELECT SUM(oi.quantity*oi.unit_price - oi.line_discount) FROM order_items oi JOIN orders o ON o.id=oi.order_id
                                       WHERE o.brand_id=? AND o.status='completed'""", (brand_id,)))
    checks["order_net_equals_sum_of_lines"] = abs(orders_net - lines) < 0.5
    refunds_total = float(repo.scalar(conn, "SELECT SUM(amount) FROM refunds WHERE brand_id=?", (brand_id,)))
    refunds_in_window = float(fin["refunds_posted"].sum())
    checks["refunds_posted_within_order_months_lte_total"] = refunds_in_window <= refunds_total + 0.01
    checks["net_sales_identity"] = bool(((fin["gross_sales"] - fin["refunds_posted"] - fin["net_sales"]).abs() < 0.01).all())
    clean_months = fin[~fin["period"].isin(["2025-06", "2025-07", "2025-08"])]
    checks["clean_months_reconcile_within_0_5pct"] = bool((clean_months["revenue_variance_pct"].abs() < 0.5).all())

    return {
        "n_findings": len(findings), "n_scenarios": len(scenario_rows), "scenario_recall": scenario_recall,
        "key_precision": precision, "key_recall": recall, "key_f1": f1,
        "true_positive_keys": sorted(tp_keys), "false_positive_keys": fp_keys, "false_negative_keys": fn_keys,
        "scenarios": scenario_rows, "skipped": skipped, "notes": notes, "value_checks": checks,
        "denominators": {"produced_findings": len(produced_keys), "expected_primary_keys": len(primary_expected), "acceptable_keys": len(acceptable)},
    }


def to_markdown(r: dict) -> str:
    lines = ["# Evaluation results", "",
             "Generated by `python -m evaluation.run_eval --write` against the synthetic demo dataset and `data/demo/ground_truth.json`.", "",
             "## Headline metrics", "",
             "| Metric | Value | Definition |", "|---|---|---|",
             f"| Scenario recall | {r['scenario_recall']:.0%} ({sum(s['detected'] for s in r['scenarios'])}/{r['n_scenarios']}) | Planted scenarios with a primary finding key produced (hard negative must also pass its constraints) |",
             f"| Finding-key precision | {r['key_precision']:.0%} ({len(r['true_positive_keys'])}/{r['denominators']['produced_findings']}) | Produced finding keys that are primary or secondary expected keys |",
             f"| Finding-key recall | {r['key_recall']:.0%} ({r['denominators']['expected_primary_keys'] - len(r['false_negative_keys'])}/{r['denominators']['expected_primary_keys']}) | Primary expected keys that were produced |",
             f"| F1 (key level) | {r['key_f1']:.2f} | Harmonic mean of key precision and recall |",
             "", "## Scenario detail", "", "| Scenario | Detected | Finding keys | Expected severity | Produced severity | Classification match |", "|---|---|---|---|---|---|"]
    for s in r["scenarios"]:
        lines.append(f"| {s['id']} {s['name']} | {'yes' if s['detected'] else 'NO'} | {', '.join(s['hits']) or '-'} | {s['expected_severity']} | {', '.join(s['produced_severity']) or '-'} | {'yes' if s['classification_match'] else 'no'} |")
    lines += ["", "## False positives (produced but not expected)", ""]
    lines += [f"- {k}" for k in r["false_positive_keys"]] or ["- none"]
    lines += ["", "## False negatives (expected primary keys not produced)", ""]
    lines += [f"- {k}" for k in r["false_negative_keys"]] or ["- none"]
    lines += ["", "## Value-level correctness checks", ""]
    lines += [f"- {k}: {'pass' if v else 'FAIL'}" for k, v in r["value_checks"].items()]
    lines += ["", "## Notes and known limitations", "",
              "- Secondary keys (e.g. REF-003 cohort spikes caused by the planted late refunds, SEA-001 for December) are counted as true positives because they arise from the same planted facts; they are listed in the ground truth.",
              "- The evaluation covers one synthetic dataset whose scenarios were planted by the same author who wrote the rules. Two thresholds (the 35% minimum uplift for SEA-001 and the 6-month window for MAR-001) were tuned after inspecting demo output, which initially produced spurious seasonal observations on a growth trend. These numbers therefore demonstrate correctness of the implementation on labelled data, not generalisation to real businesses.",
              "- Rules that found nothing on this dataset (ADV-001, CON-002, INV-002, DQ-001) are exercised by unit tests with constructed inputs instead.",
              ""] + [f"- Engine note: {n}" for n in r["notes"]]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write EVALUATION.md")
    args = ap.parse_args()
    result = evaluate()
    md = to_markdown(result)
    print(md)
    if args.write:
        (ROOT / "EVALUATION.md").write_text(md, encoding="utf-8")
        print("\nWrote EVALUATION.md")
