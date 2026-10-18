"""Cross-cutting seller questions assembled from the set of findings in a run.

Finding-specific questions are attached to each finding by the rules. This
module adds consolidated requests that only make sense when several findings
point at the same underlying records, so the seller is not asked the same
thing month by month.
"""

from __future__ import annotations

from collections import defaultdict

from tell.analysis.models import Finding


def build_questions(findings: list[Finding]) -> list[dict]:
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_rule[f.rule_id].append(f)
    out: list[dict] = []

    rev = by_rule.get("REV-001", [])
    if len(rev) >= 2:
        months = ", ".join(sorted(f.subject for f in rev))
        total = sum(f.estimated_impact or 0 for f in rev)
        out.append({
            "key": "GEN:revenue-definition",
            "question": f"Revenue in your management accounts exceeds order-derived net sales in {len(rev)} months ({months}), by a combined "
                        f"{total:,.0f}. Please provide a month-by-month bridge from the order export to reported revenue for the full period, "
                        "stating the treatment of refunds, cancellations, shipping income and VAT.",
            "rationale": "A consistent definitional difference changes the trailing revenue figure used for valuation; a bridge resolves all months at once.",
            "evidence_note": f"REV-001 findings for {months}.",
            "requested_items": "Revenue bridge workbook; accounting policy note; order and refund exports used to prepare the accounts.",
            "priority": "high",
        })

    refund_rules = [r for r in ("REF-001", "REF-002", "REF-003") if r in by_rule]
    if len(refund_rules) >= 2:
        out.append({
            "key": "GEN:refund-policy",
            "question": "Several refund patterns were flagged (product-level return rates, late-posted refunds, cohort spikes). Please describe the "
                        "refund approval policy, who can authorise refunds outside the standard window, and provide the full refund ledger with approver and reason codes.",
            "rationale": "Determines whether refunds are controlled and whether reported net sales are reliable.",
            "evidence_note": "Findings under " + ", ".join(refund_rules) + ".",
            "requested_items": "Refund policy; refund ledger with approver; customer service ticket export.",
            "priority": "high",
        })

    if "MAR-001" in by_rule and "INV-003" in by_rule:
        out.append({
            "key": "GEN:cost-basis",
            "question": "Gross margin has declined and at least one SKU's supplier invoice cost differs from the cost used in margin reporting. "
                        "Please confirm the costing method (standard vs actual, FIFO/weighted average), when standard costs were last updated, and provide landed-cost workings per SKU.",
            "rationale": "Establishes whether reported gross margin is reliable across the range, not just for the flagged SKU.",
            "evidence_note": "MAR-001 and INV-003 findings.",
            "requested_items": "Costing policy; standard cost update log; landed-cost model; supplier price lists for the period.",
            "priority": "medium",
        })

    if "INV-001" in by_rule:
        out.append({
            "key": "GEN:stock-count",
            "question": "Please confirm the date and scope of the last full physical stock count, who performed it, and whether any adjustments were booked. "
                        "We would like to attend or commission a count before completion.",
            "rationale": "Inventory variances were found in the roll-forward; a verified count underpins the working-capital adjustment.",
            "evidence_note": "INV-001 findings: " + ", ".join(f.subject for f in by_rule["INV-001"]) + ".",
            "requested_items": "Last count report and adjustments; 3PL/warehouse stock reports; write-off register.",
            "priority": "medium",
        })
    return out
