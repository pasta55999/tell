"""Rules that the demo dataset does not trigger, exercised with constructed inputs."""

from __future__ import annotations

from tell.analysis.context import AnalysisContext
from tell.analysis.rules import advertising, concentration, inventory, seasonality
from tell.data.demo_generator import generate_demo
from tell.db.connection import open_db


def _ctx():
    conn = open_db(":memory:")
    b = generate_demo(conn)
    return conn, b


def test_adv_001_fires_on_ad_intensity_spike():
    conn, b = _ctx()
    conn.execute("UPDATE ad_spend SET spend = spend * 3 WHERE brand_id=? AND period='2025-03'", (b,))
    res = advertising.run(AnalysisContext(conn, b))
    assert any(f.finding_key == "ADV-001:2025-03" for f in res.findings)
    assert all(f.classification == "observation" for f in res.findings if f.rule_id == "ADV-001")


def test_adv_001_silent_on_demo():
    conn, b = _ctx()
    res = advertising.run(AnalysisContext(conn, b))
    assert not [f for f in res.findings if f.rule_id == "ADV-001"]


def test_con_002_category_concentration():
    conn, b = _ctx()
    conn.execute("UPDATE products SET category = 'Candles' WHERE brand_id=? AND category IN ('Textiles','Decor')", (b,))
    res = concentration.run(AnalysisContext(conn, b))
    assert any(f.rule_id == "CON-002" and f.subject == "Candles" for f in res.findings)


def test_inv_002_negative_stock():
    conn, b = _ctx()
    conn.execute("UPDATE inventory_snapshots SET quantity_on_hand = -3 WHERE brand_id=? AND product_id = (SELECT id FROM products WHERE sku='KIT-002' AND brand_id=?) AND snapshot_date='2025-06-30'", (b, b))
    res = inventory.run(AnalysisContext(conn, b))
    assert any(f.finding_key == "INV-002:KIT-002" for f in res.findings)


def test_inventory_rollforward_clean_sku_has_zero_variance():
    conn, b = _ctx()
    rf = inventory.roll_forward(AnalysisContext(conn, b))
    clean = rf[~rf["sku"].isin(["CER-002", "KIT-001"])]
    assert (clean["variance"] == 0).all()
    cer = rf[rf["sku"] == "CER-002"]
    assert (cer[cer["period"] >= "2025-08"]["variance"] == -30).all()


def test_seasonal_spike_without_volume_is_suspicious():
    """Same revenue uplift but produced by inflating order values, not order counts -> should not be classed seasonal."""
    conn, b = _ctx()
    conn.execute("UPDATE orders SET gross_amount = gross_amount * 4, net_amount = net_amount * 4 WHERE brand_id=? AND order_date LIKE '2025-04-%' AND status='completed'", (b,))
    conn.execute("""UPDATE order_items SET unit_price = unit_price * 4 WHERE order_id IN (SELECT id FROM orders WHERE brand_id=? AND order_date LIKE '2025-04-%')""", (b,))
    res = seasonality.run(AnalysisContext(conn, b))
    apr = next(f for f in res.findings if f.subject == "2025-04")
    assert apr.classification == "suspected_risk" and apr.severity == "medium"
    assert apr.measured["checks"]["volume_driven"] is False


def test_seasonality_needs_minimum_history():
    conn, b = _ctx()
    conn.execute("DELETE FROM orders WHERE brand_id=? AND order_date >= '2025-06-01'", (b,))
    res = seasonality.run(AnalysisContext(conn, b))
    assert res.skipped and not res.findings
