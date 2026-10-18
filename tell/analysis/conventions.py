"""Calculation conventions, thresholds and rule registry.

Every rule has a stable ID and a version. Changing a threshold or the logic of a
rule must bump its version so that analysis runs remain comparable.
"""

from __future__ import annotations

ENGINE_VERSION = "1.0.0"

DEFINITIONS = {
    "GMS": "Gross merchandise sales: sum of quantity x unit list price on completed (non-cancelled) orders, before discounts.",
    "Discounts": "Order and line-level price reductions applied at checkout.",
    "Gross sales": "GMS minus discounts. Excludes shipping charged to customers and VAT.",
    "Refunds": "Cash refunded to customers, assigned to the month in which the refund was POSTED (not the original order month).",
    "Net sales": "Gross sales of orders placed in the period minus refunds posted in the period. This is the figure compared to seller-reported revenue.",
    "COGS": "Quantity x unit cost recorded on the order line at the time of sale (falls back to the product standard cost). Excludes freight-in, duties, packaging and warehousing unless embedded in the unit cost.",
    "Gross profit": "Gross sales minus COGS. Refunds are not deducted from gross profit because returned stock is tracked separately.",
    "Gross margin": "Gross profit / gross sales.",
    "Advertising spend": "Paid media spend as recorded in the advertising records, by month and channel.",
    "Contribution proxy": "Gross profit minus advertising spend. It is NOT EBITDA or net profit: payroll, fulfilment, payment fees, software, rent, shipping cost and overheads are excluded.",
    "ROAS": "Platform-attributed revenue / spend. Only computed for channels that report attributed revenue; never inferred from aggregate sales.",
    "Return rate": "Refunded units / units sold for the same product over the same order period (minimum sample applies).",
    "Discount rate": "Discounts / GMS for the month.",
}

# Thresholds (documented so results are explainable)
THRESHOLDS = {
    "revenue_variance_pct_medium": 2.0,
    "revenue_variance_pct_high": 5.0,
    "ad_variance_pct": 10.0,
    "return_rate_min_units": 30,
    "return_rate_min_pct": 10.0,
    "return_rate_multiple_of_portfolio": 2.0,
    "late_refund_lag_days": 45,
    "late_refund_min_count": 8,
    "late_refund_min_share_pct": 25.0,
    "refund_rate_spike_multiple": 2.0,
    "refund_rate_min_refunds": 8,
    "margin_decline_pp": 3.0,
    "margin_window_months": 6,
    "concentration_top1_pct": 25.0,
    "concentration_top3_pct": 50.0,
    "concentration_category_pct": 60.0,
    "discount_rate_min_pct": 12.0,
    "discount_rate_mad_multiplier": 3.0,
    "inventory_variance_min_units": 5,
    "inventory_variance_min_pct": 3.0,
    "supplier_cost_variance_pct": 5.0,
    "ad_ratio_mad_multiplier": 3.0,
    "ad_ratio_min_pp": 5.0,
    "seasonal_z": 2.5,
    "seasonal_min_uplift_pct": 35.0,
    "seasonal_min_months": 6,
    "seasonal_aov_tolerance_pct": 15.0,
    "seasonal_ad_ratio_tolerance_pct": 30.0,
    "peak_months": [11, 12],
}

RULES: dict[str, dict] = {
    "REV-001": {"version": "1.0", "name": "Seller-reported revenue vs order-derived net sales", "module": "revenue"},
    "ADV-002": {"version": "1.0", "name": "Seller-reported advertising vs recorded ad spend", "module": "advertising"},
    "ADV-001": {"version": "1.0", "name": "Advertising intensity anomaly (spend / gross sales)", "module": "advertising"},
    "REF-001": {"version": "1.0", "name": "Product return rate materially above portfolio", "module": "refunds"},
    "REF-002": {"version": "1.0", "name": "Refunds posted long after the original sale period", "module": "refunds"},
    "REF-003": {"version": "1.0", "name": "Order-cohort refund rate spike", "module": "refunds"},
    "MAR-001": {"version": "1.0", "name": "Gross margin decline while revenue grows", "module": "profitability"},
    "CON-001": {"version": "1.0", "name": "Revenue concentration in a single SKU", "module": "concentration"},
    "CON-002": {"version": "1.0", "name": "Revenue concentration in a single category", "module": "concentration"},
    "DSC-001": {"version": "1.0", "name": "Unusually heavy discounting period", "module": "revenue"},
    "INV-001": {"version": "1.0", "name": "Inventory roll-forward variance", "module": "inventory"},
    "INV-002": {"version": "1.0", "name": "Negative stock recorded", "module": "inventory"},
    "INV-003": {"version": "1.0", "name": "Supplier invoice cost vs recorded unit cost", "module": "inventory"},
    "SEA-001": {"version": "1.0", "name": "Sales spike vs rolling baseline (seasonality check)", "module": "seasonality"},
    "DQ-001": {"version": "1.0", "name": "Data coverage gaps", "module": "data_quality"},
}


def rule_versions() -> dict[str, str]:
    return {k: v["version"] for k, v in RULES.items()}
