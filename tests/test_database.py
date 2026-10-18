from __future__ import annotations

import sqlite3

from tell.data.demo_generator import DEMO_SLUG, generate_demo
from tell.db import repository as repo
from tell.db.connection import init_db, open_db


def test_schema_is_idempotent(fresh_conn):
    init_db(fresh_conn)
    init_db(fresh_conn)
    tables = {r[0] for r in fresh_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"brands", "orders", "order_items", "refunds", "ad_spend", "inventory_snapshots", "seller_statements",
            "analysis_runs", "findings", "finding_evidence", "diligence_questions", "reports", "import_files"} <= tables


def test_demo_seed_is_idempotent(fresh_conn):
    a = generate_demo(fresh_conn)
    b = generate_demo(fresh_conn)
    assert a == b
    assert fresh_conn.execute("SELECT COUNT(*) FROM brands WHERE slug = ?", (DEMO_SLUG,)).fetchone()[0] == 1


def test_demo_is_deterministic():
    c1, c2 = open_db(":memory:"), open_db(":memory:")
    b1, b2 = generate_demo(c1), generate_demo(c2)
    assert repo.data_snapshot(c1, b1)[1] == repo.data_snapshot(c2, b2)[1]


def test_demo_reset_regenerates_identical_data(fresh_conn):
    b = generate_demo(fresh_conn)
    h1 = repo.data_snapshot(fresh_conn, b)[1]
    fresh_conn.execute("INSERT INTO analysis_runs(brand_id, data_snapshot, data_hash, rule_versions, engine_version) VALUES (?,?,?,?,?)", (b, "{}", "x", "{}", "t"))
    b2 = generate_demo(fresh_conn, force=True)
    assert repo.data_snapshot(fresh_conn, b2)[1] == h1
    assert fresh_conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 0   # cascaded


def test_persistence_across_connections(tmp_path):
    path = tmp_path / "persist.db"
    c = open_db(path)
    b = generate_demo(c)
    n = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    c.close()
    c2 = open_db(path)
    assert c2.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == n
    assert generate_demo(c2) == b    # second start-up does not duplicate the demo


def test_foreign_keys_enforced(fresh_conn):
    generate_demo(fresh_conn)
    try:
        fresh_conn.execute("INSERT INTO order_items(order_id, product_id, quantity, unit_price) VALUES (999999, 1, 1, 1)")
        assert False, "expected FK violation"
    except sqlite3.IntegrityError:
        pass


def test_demo_volume(demo_conn, brand_id):
    counts = repo.table_counts(demo_conn, brand_id)
    assert counts["orders"] >= 1000
    assert counts["products"] == 20
    assert counts["seller_statements"] == 12
    assert counts["inventory_snapshots"] == 20 * 13
    start, end = repo.brand_period(demo_conn, brand_id)
    assert start.startswith("2025-01") and end.startswith("2025-12")
