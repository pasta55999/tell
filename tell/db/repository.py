"""Read-side query helpers. All queries are parameterised; results are pandas DataFrames
or sqlite3.Row objects. This module contains no business logic beyond aggregation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Sequence

import pandas as pd

SOURCE_TABLES = [
    "products",
    "orders",
    "order_items",
    "refunds",
    "refund_items",
    "ad_spend",
    "inventory_snapshots",
    "supplier_receipts",
    "seller_statements",
]


def fetch_df(conn: sqlite3.Connection, sql: str, params: Sequence[Any] | dict = ()) -> pd.DataFrame:
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description] if cur.description else []
    return pd.DataFrame(cur.fetchall(), columns=cols)


def fetch_one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] | dict = ()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def scalar(conn: sqlite3.Connection, sql: str, params: Sequence[Any] | dict = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


# ----------------------------------------------------------------- brands

def list_brands(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM brands ORDER BY id").fetchall()


def get_brand(conn: sqlite3.Connection, brand_id: int) -> sqlite3.Row | None:
    return fetch_one(conn, "SELECT * FROM brands WHERE id = ?", (brand_id,))


def get_brand_by_slug(conn: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    return fetch_one(conn, "SELECT * FROM brands WHERE slug = ?", (slug,))


def brand_period(conn: sqlite3.Connection, brand_id: int) -> tuple[str | None, str | None]:
    row = fetch_one(
        conn,
        "SELECT MIN(order_date) AS start, MAX(order_date) AS end FROM orders WHERE brand_id = ?",
        (brand_id,),
    )
    return (row["start"], row["end"]) if row else (None, None)


def table_counts(conn: sqlite3.Connection, brand_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in SOURCE_TABLES:
        if table == "order_items":
            sql = "SELECT COUNT(*) FROM order_items oi JOIN orders o ON o.id = oi.order_id WHERE o.brand_id = ?"
        elif table == "refund_items":
            sql = "SELECT COUNT(*) FROM refund_items ri JOIN refunds r ON r.id = ri.refund_id WHERE r.brand_id = ?"
        else:
            sql = f"SELECT COUNT(*) FROM {table} WHERE brand_id = ?"  # noqa: S608 - table from fixed list
        counts[table] = int(scalar(conn, sql, (brand_id,)) or 0)
    return counts


def data_snapshot(conn: sqlite3.Connection, brand_id: int) -> tuple[dict[str, Any], str]:
    """Row counts plus a content hash of the brand's source data.

    The hash is computed from a deterministic ordering of the key numeric columns,
    so an unchanged dataset always yields the same hash.
    """
    counts = table_counts(conn, brand_id)
    h = hashlib.sha256()
    queries = {
        "orders": "SELECT order_ref, order_date, status, gross_amount, discount_amount, net_amount FROM orders WHERE brand_id = ? ORDER BY order_ref",
        "refunds": "SELECT refund_ref, refund_date, amount FROM refunds WHERE brand_id = ? ORDER BY refund_ref",
        "ad_spend": "SELECT period, channel, spend, attributed_revenue FROM ad_spend WHERE brand_id = ? ORDER BY period, channel",
        "seller_statements": "SELECT period, reported_revenue, reported_cogs, reported_ad_spend FROM seller_statements WHERE brand_id = ? ORDER BY period",
        "inventory_snapshots": "SELECT product_id, snapshot_date, quantity_on_hand FROM inventory_snapshots WHERE brand_id = ? ORDER BY product_id, snapshot_date",
        "supplier_receipts": "SELECT receipt_ref, product_id, quantity, unit_cost FROM supplier_receipts WHERE brand_id = ? ORDER BY receipt_ref",
        "products": "SELECT sku, list_price, standard_cost FROM products WHERE brand_id = ? ORDER BY sku",
    }
    for name, sql in queries.items():
        h.update(name.encode())
        for row in conn.execute(sql, (brand_id,)):
            h.update(json.dumps(list(row), default=str).encode())
    digest = h.hexdigest()[:16]
    return {"counts": counts, "hash": digest}, digest


# ----------------------------------------------------------------- monthly aggregates

def monthly_orders(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    """Per-period order aggregates (period = order month)."""
    sql = """
        SELECT substr(order_date, 1, 7) AS period,
               COUNT(*)                                             AS orders_total,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS orders_completed,
               SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS orders_cancelled,
               SUM(CASE WHEN status = 'completed' THEN gross_amount ELSE 0 END)    AS gms,
               SUM(CASE WHEN status = 'completed' THEN discount_amount ELSE 0 END) AS discounts,
               SUM(CASE WHEN status = 'completed' THEN net_amount ELSE 0 END)      AS gross_sales,
               SUM(CASE WHEN status = 'completed' THEN shipping_amount ELSE 0 END) AS shipping,
               SUM(CASE WHEN status = 'cancelled' THEN net_amount ELSE 0 END)      AS cancelled_value
        FROM orders WHERE brand_id = ?
        GROUP BY period ORDER BY period
    """
    return fetch_df(conn, sql, (brand_id,))


def monthly_units_and_cogs(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(o.order_date, 1, 7) AS period,
               SUM(oi.quantity) AS units,
               SUM(oi.quantity * COALESCE(oi.unit_cost, p.standard_cost, 0)) AS cogs,
               SUM(CASE WHEN oi.unit_cost IS NULL AND p.standard_cost IS NULL THEN oi.quantity ELSE 0 END) AS units_without_cost
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.brand_id = ? AND o.status = 'completed'
        GROUP BY period ORDER BY period
    """
    return fetch_df(conn, sql, (brand_id,))


def monthly_refunds_by_posting(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(refund_date, 1, 7) AS period, COUNT(*) AS refund_count, SUM(amount) AS refunds
        FROM refunds WHERE brand_id = ? GROUP BY period ORDER BY period
    """
    return fetch_df(conn, sql, (brand_id,))


def monthly_refunds_by_order_period(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(o.order_date, 1, 7) AS period, COUNT(*) AS refund_count, SUM(r.amount) AS refunds
        FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.brand_id = ? GROUP BY period ORDER BY period
    """
    return fetch_df(conn, sql, (brand_id,))


def monthly_ad_spend(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT period, channel, spend, impressions, clicks, attributed_revenue
        FROM ad_spend WHERE brand_id = ? ORDER BY period, channel
    """
    return fetch_df(conn, sql, (brand_id,))


def seller_statements(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    return fetch_df(conn, "SELECT * FROM seller_statements WHERE brand_id = ? ORDER BY period", (brand_id,))


# ----------------------------------------------------------------- products

def product_sales(conn: sqlite3.Connection, brand_id: int, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Per-product completed sales. `start`/`end` are inclusive YYYY-MM periods."""
    sql = """
        SELECT p.id AS product_id, p.sku, p.name, p.category, p.list_price, p.standard_cost,
               SUM(oi.quantity) AS units,
               SUM(oi.quantity * oi.unit_price) AS gms,
               SUM(oi.line_discount) AS discounts,
               SUM(oi.quantity * oi.unit_price - oi.line_discount) AS gross_sales,
               SUM(oi.quantity * COALESCE(oi.unit_cost, p.standard_cost, 0)) AS cogs,
               COUNT(DISTINCT o.id) AS order_count
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.brand_id = ? AND o.status = 'completed'
          AND (? IS NULL OR substr(o.order_date,1,7) >= ?)
          AND (? IS NULL OR substr(o.order_date,1,7) <= ?)
        GROUP BY p.id ORDER BY gross_sales DESC
    """
    return fetch_df(conn, sql, (brand_id, start, start, end, end))


def product_refunds(conn: sqlite3.Connection, brand_id: int, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Per-product refunded units/amounts, keyed by the ORIGINAL order period."""
    sql = """
        SELECT ri.product_id,
               SUM(ri.quantity) AS refunded_units,
               SUM(ri.amount) AS refunded_amount,
               COUNT(DISTINCT r.id) AS refund_count
        FROM refund_items ri
        JOIN refunds r ON r.id = ri.refund_id
        JOIN orders o ON o.id = r.order_id
        WHERE r.brand_id = ?
          AND (? IS NULL OR substr(o.order_date,1,7) >= ?)
          AND (? IS NULL OR substr(o.order_date,1,7) <= ?)
        GROUP BY ri.product_id
    """
    return fetch_df(conn, sql, (brand_id, start, start, end, end))


def product_monthly_sales(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(o.order_date,1,7) AS period, p.id AS product_id, p.sku, p.name, p.category,
               SUM(oi.quantity) AS units,
               SUM(oi.quantity * oi.unit_price - oi.line_discount) AS gross_sales,
               SUM(oi.quantity * COALESCE(oi.unit_cost, p.standard_cost, 0)) AS cogs
        FROM order_items oi JOIN orders o ON o.id = oi.order_id JOIN products p ON p.id = oi.product_id
        WHERE o.brand_id = ? AND o.status = 'completed'
        GROUP BY period, p.id ORDER BY period, p.id
    """
    return fetch_df(conn, sql, (brand_id,))


def products(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    return fetch_df(conn, "SELECT * FROM products WHERE brand_id = ? ORDER BY sku", (brand_id,))


# ----------------------------------------------------------------- refunds detail

def refund_lags(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT r.id AS refund_id, r.refund_ref, r.refund_date, r.amount, r.reason,
               o.id AS order_id, o.order_ref, o.order_date,
               CAST(julianday(r.refund_date) - julianday(o.order_date) AS INTEGER) AS lag_days,
               substr(o.order_date,1,7) AS order_period, substr(r.refund_date,1,7) AS refund_period
        FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.brand_id = ? ORDER BY r.refund_date
    """
    return fetch_df(conn, sql, (brand_id,))


# ----------------------------------------------------------------- inventory

def inventory_snapshots(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT s.id, s.product_id, p.sku, p.name, s.snapshot_date, s.quantity_on_hand, s.source
        FROM inventory_snapshots s JOIN products p ON p.id = s.product_id
        WHERE s.brand_id = ? ORDER BY s.product_id, s.snapshot_date
    """
    return fetch_df(conn, sql, (brand_id,))


def supplier_receipts(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT r.id, r.receipt_ref, r.product_id, p.sku, r.received_date, r.quantity, r.unit_cost, r.supplier
        FROM supplier_receipts r JOIN products p ON p.id = r.product_id
        WHERE r.brand_id = ? ORDER BY r.received_date
    """
    return fetch_df(conn, sql, (brand_id,))


def units_sold_by_product_month(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(o.order_date,1,7) AS period, oi.product_id, SUM(oi.quantity) AS units
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.brand_id = ? AND o.status = 'completed'
        GROUP BY period, oi.product_id
    """
    return fetch_df(conn, sql, (brand_id,))


def restocked_units_by_product_month(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(r.refund_date,1,7) AS period, ri.product_id, SUM(ri.quantity) AS units
        FROM refund_items ri JOIN refunds r ON r.id = ri.refund_id
        WHERE r.brand_id = ? AND ri.restocked = 1
        GROUP BY period, ri.product_id
    """
    return fetch_df(conn, sql, (brand_id,))


def product_cost_by_month(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    """Average recorded unit cost on order lines per product per month."""
    sql = """
        SELECT substr(o.order_date,1,7) AS period, oi.product_id,
               SUM(oi.quantity * oi.unit_cost) / SUM(oi.quantity) AS avg_unit_cost,
               SUM(oi.quantity) AS units
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.brand_id = ? AND o.status = 'completed' AND oi.unit_cost IS NOT NULL
        GROUP BY period, oi.product_id
    """
    return fetch_df(conn, sql, (brand_id,))


# ----------------------------------------------------------------- orders drill-down

def orders_in_period(conn: sqlite3.Connection, brand_id: int, period: str, status: str | None = None, limit: int = 500) -> pd.DataFrame:
    sql = """
        SELECT id, order_ref, order_date, channel, status, gross_amount, discount_amount, shipping_amount, net_amount
        FROM orders WHERE brand_id = ? AND substr(order_date,1,7) = ?
          AND (? IS NULL OR status = ?)
        ORDER BY order_date, order_ref LIMIT ?
    """
    return fetch_df(conn, sql, (brand_id, period, status, status, limit))


def refunds_in_period(conn: sqlite3.Connection, brand_id: int, period: str, limit: int = 500) -> pd.DataFrame:
    sql = """
        SELECT r.id, r.refund_ref, r.refund_date, r.amount, r.reason, o.order_ref, o.order_date
        FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.brand_id = ? AND substr(r.refund_date,1,7) = ?
        ORDER BY r.refund_date LIMIT ?
    """
    return fetch_df(conn, sql, (brand_id, period, limit))


def orders_by_channel_month(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    sql = """
        SELECT substr(order_date,1,7) AS period, channel,
               COUNT(*) AS orders, SUM(net_amount) AS gross_sales
        FROM orders WHERE brand_id = ? AND status = 'completed'
        GROUP BY period, channel ORDER BY period, channel
    """
    return fetch_df(conn, sql, (brand_id,))


# ----------------------------------------------------------------- runs / findings

def list_runs(conn: sqlite3.Connection, brand_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM analysis_runs WHERE brand_id = ? ORDER BY id DESC", (brand_id,)
    ).fetchall()


def latest_run(conn: sqlite3.Connection, brand_id: int) -> sqlite3.Row | None:
    return fetch_one(
        conn,
        "SELECT * FROM analysis_runs WHERE brand_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
        (brand_id,),
    )


def get_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return fetch_one(conn, "SELECT * FROM analysis_runs WHERE id = ?", (run_id,))


def findings_for_run(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    df = fetch_df(
        conn,
        """SELECT f.*, (SELECT COUNT(*) FROM finding_evidence e WHERE e.finding_id = f.id) AS evidence_count
           FROM findings f WHERE run_id = ?
           ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                    COALESCE(estimated_impact, 0) DESC, finding_key""",
        (run_id,),
    )
    return df


def get_finding(conn: sqlite3.Connection, finding_id: int) -> sqlite3.Row | None:
    return fetch_one(conn, "SELECT * FROM findings WHERE id = ?", (finding_id,))


def evidence_for_finding(conn: sqlite3.Connection, finding_id: int) -> pd.DataFrame:
    return fetch_df(conn, "SELECT * FROM finding_evidence WHERE finding_id = ? ORDER BY id", (finding_id,))


def questions_for_run(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    return fetch_df(
        conn,
        """SELECT q.*, f.title AS finding_title, f.finding_key, f.severity
           FROM diligence_questions q LEFT JOIN findings f ON f.id = q.finding_id
           WHERE q.run_id = ?
           ORDER BY CASE q.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, q.id""",
        (run_id,),
    )


def questions_for_finding(conn: sqlite3.Connection, finding_id: int) -> pd.DataFrame:
    return fetch_df(conn, "SELECT * FROM diligence_questions WHERE finding_id = ? ORDER BY id", (finding_id,))


def import_history(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT id, dataset, filename, row_count, imported_rows, rejected_rows, skipped_rows, status, imported_at, notes FROM import_files WHERE brand_id = ? ORDER BY id DESC",
        (brand_id,),
    )
