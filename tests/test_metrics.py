"""Financial calculation conventions: gross/net sales, refunds, margins, denominators."""

from __future__ import annotations

import pandas as pd

from tell.analysis import metrics
from tell.analysis.rules.advertising import channel_table
from tell.analysis.rules.revenue import attribute_variance
from tell.db import repository as repo


def test_gross_sales_equals_gms_minus_discounts(demo_conn, brand_id):
    fin = metrics.monthly_financials(demo_conn, brand_id)
    assert ((fin["gms"] - fin["discounts"] - fin["gross_sales"]).abs() < 0.01).all()


def test_net_sales_subtracts_refunds_once(demo_conn, brand_id):
    fin = metrics.monthly_financials(demo_conn, brand_id)
    assert ((fin["gross_sales"] - fin["refunds_posted"] - fin["net_sales"]).abs() < 0.01).all()
    # total refunds posted inside the window equals the refunds table for those months
    posted = repo.monthly_refunds_by_posting(demo_conn, brand_id).set_index("period")["refunds"]
    for _, r in fin.iterrows():
        assert abs(r["refunds_posted"] - posted.get(r["period"], 0)) < 0.01


def test_cancelled_orders_excluded_from_sales(demo_conn, brand_id):
    fin = metrics.monthly_financials(demo_conn, brand_id)
    completed = repo.scalar(demo_conn, "SELECT SUM(net_amount) FROM orders WHERE brand_id=? AND status='completed'", (brand_id,))
    assert abs(fin["gross_sales"].sum() - completed) < 0.01
    assert fin["cancelled_value"].sum() > 0


def test_gross_margin_definition(demo_conn, brand_id):
    fin = metrics.monthly_financials(demo_conn, brand_id)
    expected = (fin["gross_sales"] - fin["cogs"]) / fin["gross_sales"] * 100
    assert ((fin["gross_margin_pct"] - expected).abs() < 1e-9).all()
    assert 40 < fin["gross_margin_pct"].mean() < 75


def test_contribution_proxy_is_gp_minus_ads(demo_conn, brand_id):
    fin = metrics.monthly_financials(demo_conn, brand_id)
    assert ((fin["gross_profit"] - fin["ad_spend"] - fin["contribution_proxy"]).abs() < 0.01).all()


def test_return_rate_denominator_is_units_sold(demo_conn, brand_id):
    prod = metrics.product_table(demo_conn, brand_id)
    row = prod[prod["sku"] == "TEX-003"].iloc[0]
    assert abs(row["return_rate_pct"] - row["refunded_units"] / row["units"] * 100) < 1e-9
    assert prod["revenue_share_pct"].sum() == pytest_approx(100)


def pytest_approx(v):
    import pytest
    return pytest.approx(v, abs=1e-6)


def test_roas_only_where_attribution_exists(demo_conn, brand_id):
    ch = channel_table(repo.monthly_ad_spend(demo_conn, brand_id))
    with_roas = ch[ch["roas"].notna()]["channel"].tolist()
    assert with_roas == ["Marketplace Ads"]
    assert ch[ch["channel"] == "Meta"]["roas"].isna().all()


def test_period_totals_consistency(demo_conn, brand_id):
    fin = metrics.monthly_financials(demo_conn, brand_id)
    t = metrics.period_totals(fin)
    assert t["months"] == 12
    assert abs(t["net_sales"] - fin["net_sales"].sum()) < 0.01
    assert abs(t["gross_margin_pct"] - (t["gross_profit"] / t["gross_sales"] * 100)) < 1e-9


def test_variance_attribution_matches_refunds_plus_cancellations():
    row = pd.Series({"revenue_variance": 1500.0, "refunds_posted": 1000.0, "cancelled_value": 500.0, "shipping": 300.0, "discounts": 2000.0})
    label, residual = attribute_variance(row)
    assert "refunds" in label and "cancelled" in label
    assert abs(residual) < 1e-9


def test_variance_attribution_returns_none_when_unexplained():
    row = pd.Series({"revenue_variance": 9999.0, "refunds_posted": 10.0, "cancelled_value": 20.0, "shipping": 30.0, "discounts": 40.0})
    label, residual = attribute_variance(row)
    assert label is None and residual == 9999.0


def test_robust_z_handles_zero_mad():
    assert metrics.robust_z(pd.Series([5, 5, 5, 5]), 9) is None
    assert metrics.robust_z(pd.Series([1, 2, 3, 4, 5]), 50) > 3


def test_missing_costs_are_not_imputed(fresh_conn):
    """Order lines without any cost must not contribute invented COGS."""
    from tell.data.demo_generator import generate_demo
    b = generate_demo(fresh_conn)
    fresh_conn.execute("UPDATE order_items SET unit_cost = NULL WHERE product_id IN (SELECT id FROM products WHERE sku = 'CAN-001')")
    fresh_conn.execute("UPDATE products SET standard_cost = NULL WHERE sku = 'CAN-001'")
    fin = metrics.monthly_financials(fresh_conn, b)
    assert fin["units_without_cost"].sum() > 0
    full = metrics.monthly_financials(fresh_conn, b)["cogs"].sum()
    assert full < repo.scalar(fresh_conn, "SELECT SUM(reported_cogs) FROM seller_statements WHERE brand_id=?", (b,))
