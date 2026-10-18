"""Deterministic generator for the fictional demo business "Saffron & Sage".

Every record is produced from a seeded RNG, so repeated runs are byte-for-byte
identical. The generator builds orders first and derives every downstream
dataset (COGS, refunds, inventory, seller statements) from them, then applies
the documented, deliberately planted diligence scenarios. The planted scenarios
are described in data/demo/ground_truth.json and in docs/demo_dataset.md.

Reconciliation conventions used by this dataset:
  gross_amount   = sum(quantity * unit_price) per order            (GMS)
  net_amount     = gross_amount - discount_amount                   (gross sales, ex shipping, ex VAT)
  net sales(t)   = gross sales of completed orders placed in t - refunds POSTED in t
  COGS           = sum(quantity * unit_cost recorded on the order line)
"""

from __future__ import annotations

import calendar
import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from tell.db.connection import transaction

DEMO_SLUG = "saffron-and-sage"
DEMO_SEED = 20250101
YEAR = 2025
PERIODS = [f"{YEAR}-{m:02d}" for m in range(1, 13)]


@dataclass(frozen=True)
class ProductSpec:
    sku: str
    name: str
    category: str
    price: float
    cost: float
    weight: float            # relative demand weight
    refund_rate: float = 0.045


# sku, name, category, list price (AED), base unit cost (AED), demand weight, refund rate
PRODUCTS: list[ProductSpec] = [
    ProductSpec("CAN-001", "Signature Saffron Candle 320g", "Candles", 145, 48, 56),
    ProductSpec("CAN-002", "Sage & Cedar Candle 320g", "Candles", 145, 50, 8),
    ProductSpec("CAN-003", "Travel Candle Trio", "Candles", 185, 70, 4),
    ProductSpec("CAN-004", "Reed Diffuser - Oud & Fig", "Candles", 165, 55, 7),
    ProductSpec("CER-001", "Stoneware Dinner Plate Set (4)", "Ceramics", 420, 190, 3),
    ProductSpec("CER-002", "Hand-glazed Serving Bowl", "Ceramics", 260, 110, 5),
    ProductSpec("CER-003", "Espresso Cup Pair", "Ceramics", 150, 62, 4),
    ProductSpec("TEX-001", "Linen Table Runner", "Textiles", 220, 85, 4),
    ProductSpec("TEX-002", "Cushion Cover - Terracotta", "Textiles", 165, 60, 6),
    ProductSpec("TEX-003", "Linen Throw - Sage", "Textiles", 390, 160, 4, refund_rate=0.18),
    ProductSpec("TEX-004", "Waffle Bath Towel Set", "Textiles", 295, 125, 4),
    ProductSpec("TEX-005", "Linen Napkin Set (4)", "Textiles", 140, 52, 4),
    ProductSpec("KIT-001", "Olive Wood Serving Board", "Kitchen", 240, 95, 5),
    ProductSpec("KIT-002", "Brass Measuring Spoons", "Kitchen", 120, 42, 5),
    ProductSpec("KIT-003", "Spice Jar Set (6)", "Kitchen", 210, 80, 4),
    ProductSpec("KIT-004", "Marble Salt Cellar", "Kitchen", 130, 50, 3),
    ProductSpec("DEC-001", "Rattan Wall Mirror", "Decor", 450, 180, 3),
    ProductSpec("DEC-002", "Ceramic Vase - Dune", "Decor", 230, 92, 4),
    ProductSpec("DEC-003", "Brass Candle Snuffer", "Decor", 95, 30, 3),
    ProductSpec("DEC-004", "Woven Storage Basket", "Decor", 175, 68, 4),
]

# Monthly demand multipliers (index 1..12). November is a legitimate peak
# (regional "White Friday" sales event); summer months are softer.
SEASONAL = {1: 1.0, 2: 0.95, 3: 1.0, 4: 1.0, 5: 1.05, 6: 0.95, 7: 0.88, 8: 0.9,
            9: 1.0, 10: 1.05, 11: 1.9, 12: 1.3}
BASE_ORDERS = 130
MONTHLY_GROWTH = 1.025

# Promotion calendar: (share of orders discounted, discount rate range)
PROMO = {m: (0.25, (0.10, 0.10)) for m in range(1, 13)}
PROMO[5] = (0.70, (0.20, 0.25))     # S7: heavy discounting period
PROMO[11] = (0.60, (0.15, 0.15))    # part of the legitimate seasonal event (S9)

CHANNELS = [("Online Store", 0.70), ("Marketplace", 0.30)]
AD_CHANNELS = {"Meta": 0.42, "Google": 0.28, "TikTok": 0.12, "Marketplace Ads": 0.18}
CANCEL_RATE = 0.04
SHIPPING_FEE = 15.0
FREE_SHIPPING_THRESHOLD = 200.0

# Scenario parameters
REVENUE_OVERSTATED_PERIODS = ["2025-06", "2025-07", "2025-08"]      # S1
LATE_REFUND_SOURCE_PERIODS = ["2025-07", "2025-08"]                 # S2
LATE_REFUND_POSTING_PERIOD = "2025-10"
LATE_REFUND_COUNT = 45
AD_UNDERSTATED_PERIOD = "2025-09"                                   # S4
AD_UNDERSTATED_FACTOR = 0.55
COST_INCREASE_FROM_MONTH = 7                                        # S6
COST_INCREASE_GENERAL = 1.08
COST_INCREASE_CANDLES = 1.14
SHRINKAGE_SKU = "CER-002"                                           # S8a
SHRINKAGE_FROM_MONTH = 8
SHRINKAGE_PER_MONTH = 30
PHANTOM_SKU = "KIT-001"                                             # S8b
PHANTOM_MONTH = 9
PHANTOM_UNITS = 60
SUPPLIER_COST_SKU = "DEC-001"                                       # S10
SUPPLIER_COST_FROM_MONTH = 9
SUPPLIER_COST_FACTOR = 1.15


def _month_end(period: str) -> date:
    y, m = int(period[:4]), int(period[5:7])
    return date(y, m, calendar.monthrange(y, m)[1])


def unit_cost_for(spec: ProductSpec, month: int) -> float:
    """Cost recorded on order lines. DEC-001's recorded cost is deliberately stale (S10)."""
    if spec.sku == SUPPLIER_COST_SKU:
        return spec.cost
    if month >= COST_INCREASE_FROM_MONTH:
        factor = COST_INCREASE_CANDLES if spec.category == "Candles" else COST_INCREASE_GENERAL
        return round(spec.cost * factor, 2)
    return spec.cost


def supplier_cost_for(spec: ProductSpec, month: int) -> float:
    """Cost on supplier receipts. Matches recorded cost except for the S10 SKU from September."""
    if spec.sku == SUPPLIER_COST_SKU:
        return round(spec.cost * SUPPLIER_COST_FACTOR, 2) if month >= SUPPLIER_COST_FROM_MONTH else spec.cost
    return unit_cost_for(spec, month)


@dataclass
class _Order:
    ref: str
    day: date
    customer: str
    channel: str
    status: str
    lines: list[dict] = field(default_factory=list)
    discount_rate: float = 0.0

    @property
    def gross(self) -> float:
        return round(sum(l["qty"] * l["price"] for l in self.lines), 2)

    @property
    def discount(self) -> float:
        return round(sum(l["line_discount"] for l in self.lines), 2)

    @property
    def net(self) -> float:
        return round(self.gross - self.discount, 2)

    @property
    def shipping(self) -> float:
        return 0.0 if self.gross >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE


def _generate_orders(rng: random.Random) -> list[_Order]:
    orders: list[_Order] = []
    weights = [p.weight for p in PRODUCTS]
    seq = 0
    for month in range(1, 13):
        n = round(BASE_ORDERS * (MONTHLY_GROWTH ** (month - 1)) * SEASONAL[month])
        promo_share, (lo, hi) = PROMO[month]
        days_in_month = calendar.monthrange(YEAR, month)[1]
        for _ in range(n):
            seq += 1
            day = date(YEAR, month, rng.randint(1, days_in_month))
            channel = rng.choices([c for c, _ in CHANNELS], [w for _, w in CHANNELS])[0]
            status = "cancelled" if rng.random() < CANCEL_RATE else "completed"
            order = _Order(ref=f"SS-{YEAR}-{seq:05d}", day=day, customer=f"C{rng.randint(1, 1400):05d}",
                           channel=channel, status=status)
            n_lines = min(4, 1 + sum(1 for _ in range(3) if rng.random() < 0.22))
            chosen = set()
            for _ in range(n_lines):
                spec = rng.choices(PRODUCTS, weights)[0]
                if spec.sku in chosen:
                    continue
                chosen.add(spec.sku)
                qty = 2 if rng.random() < 0.18 else 1
                order.lines.append({"spec": spec, "qty": qty, "price": spec.price,
                                    "cost": unit_cost_for(spec, month), "line_discount": 0.0})
            if rng.random() < promo_share:
                rate = round(rng.uniform(lo, hi), 2)
                order.discount_rate = rate
                for line in order.lines:
                    line["line_discount"] = round(line["qty"] * line["price"] * rate, 2)
            orders.append(order)
    return orders


def _generate_refunds(rng: random.Random, orders: list[_Order]) -> list[dict]:
    """Base refunds (short lag) plus the planted late-refund cluster (S2)."""
    refunds: list[dict] = []
    seq = 0
    reasons = ["changed mind", "damaged in transit", "not as described", "wrong item sent"]
    refunded_orders: set[str] = set()
    for order in orders:
        if order.status != "completed":
            continue
        items = []
        for line in order.lines:
            spec: ProductSpec = line["spec"]
            if rng.random() < spec.refund_rate:
                if spec.sku == "TEX-003" and rng.random() < 0.6:
                    reason = "quality issue - pilling/shedding"
                else:
                    reason = rng.choice(reasons)
                amount = round(line["qty"] * line["price"] - line["line_discount"], 2)
                items.append({"spec": spec, "qty": line["qty"], "amount": amount,
                              "restocked": 0 if reason == "damaged in transit" else 1, "reason": reason})
        if not items:
            continue
        lag = min(35, max(1, int(rng.gammavariate(3.0, 4.0))))
        seq += 1
        refunded_orders.add(order.ref)
        refunds.append({"ref": f"RF-{YEAR}-{seq:04d}", "order": order, "date": order.day + timedelta(days=lag),
                        "items": items, "reason": items[0]["reason"]})

    # S2: refunds posted in October against July/August orders (goodwill refunds, 60-110 day lag)
    candidates = [o for o in orders if o.status == "completed"
                  and o.day.strftime("%Y-%m") in LATE_REFUND_SOURCE_PERIODS and o.ref not in refunded_orders]
    rng.shuffle(candidates)
    post_start = date(YEAR, 10, 5)
    for order in candidates[:LATE_REFUND_COUNT]:
        line = order.lines[0]
        seq += 1
        refund_date = post_start + timedelta(days=rng.randint(0, 23))
        refunds.append({"ref": f"RF-{YEAR}-{seq:04d}", "order": order, "date": refund_date,
                        "items": [{"spec": line["spec"], "qty": line["qty"],
                                   "amount": round(line["qty"] * line["price"] - line["line_discount"], 2),
                                   "restocked": 0, "reason": "goodwill refund"}],
                        "reason": "goodwill refund"})
    refunds.sort(key=lambda r: (r["date"], r["ref"]))
    return refunds


def _insert_brand(conn: sqlite3.Connection) -> int:
    conn.execute("INSERT OR IGNORE INTO workspaces(name) VALUES ('Demo workspace')")
    ws_id = conn.execute("SELECT id FROM workspaces WHERE name = 'Demo workspace'").fetchone()[0]
    conn.execute(
        """INSERT INTO brands(workspace_id, slug, name, category, description, reporting_currency, is_demo)
           VALUES (?, ?, ?, ?, ?, 'AED', 1)""",
        (ws_id, DEMO_SLUG, "Saffron & Sage", "Home & Lifestyle",
         "Direct-to-consumer home fragrance, ceramics and textiles brand based in Dubai. "
         "Fictional demo business generated by Tell; all figures are synthetic."),
    )
    return conn.execute("SELECT id FROM brands WHERE slug = ?", (DEMO_SLUG,)).fetchone()[0]


def generate_demo(conn: sqlite3.Connection, seed: int = DEMO_SEED, force: bool = False) -> int:
    """Populate the demo brand. Idempotent: returns the existing brand id unless `force`.

    With `force=True` the existing demo brand (and all dependent rows, including
    analysis runs) is deleted and regenerated.
    """
    existing = conn.execute("SELECT id FROM brands WHERE slug = ?", (DEMO_SLUG,)).fetchone()
    if existing and not force:
        return int(existing[0])

    rng = random.Random(seed)
    orders = _generate_orders(rng)
    refunds = _generate_refunds(rng, orders)

    with transaction(conn):
        if existing:
            conn.execute("DELETE FROM brands WHERE id = ?", (existing[0],))
        brand_id = _insert_brand(conn)
        cur = conn.execute(
            """INSERT INTO import_files(brand_id, dataset, filename, sha256, row_count, imported_rows, notes)
               VALUES (?, 'demo', 'generated:saffron-and-sage', ?, 0, 0, 'Synthetic demo dataset')""",
            (brand_id, f"seed-{seed}"),
        )
        import_id = cur.lastrowid

        product_ids: dict[str, int] = {}
        for p in PRODUCTS:
            cur = conn.execute(
                "INSERT INTO products(brand_id, sku, name, category, list_price, standard_cost, import_file_id) VALUES (?,?,?,?,?,?,?)",
                (brand_id, p.sku, p.name, p.category, p.price, p.cost, import_id),
            )
            product_ids[p.sku] = cur.lastrowid

        order_ids: dict[str, int] = {}
        for o in orders:
            cur = conn.execute(
                """INSERT INTO orders(brand_id, order_ref, order_date, customer_ref, channel, status, currency,
                                      gross_amount, discount_amount, shipping_amount, net_amount, import_file_id)
                   VALUES (?,?,?,?,?,?,'AED',?,?,?,?,?)""",
                (brand_id, o.ref, o.day.isoformat(), o.customer, o.channel, o.status,
                 o.gross, o.discount, o.shipping, o.net, import_id),
            )
            order_ids[o.ref] = cur.lastrowid
            conn.executemany(
                "INSERT INTO order_items(order_id, product_id, quantity, unit_price, unit_cost, line_discount) VALUES (?,?,?,?,?,?)",
                [(cur.lastrowid, product_ids[l["spec"].sku], l["qty"], l["price"], l["cost"], l["line_discount"]) for l in o.lines],
            )

        for r in refunds:
            amount = round(sum(i["amount"] for i in r["items"]), 2)
            cur = conn.execute(
                "INSERT INTO refunds(brand_id, refund_ref, order_id, refund_date, amount, reason, import_file_id) VALUES (?,?,?,?,?,?,?)",
                (brand_id, r["ref"], order_ids[r["order"].ref], r["date"].isoformat(), amount, r["reason"], import_id),
            )
            conn.executemany(
                "INSERT INTO refund_items(refund_id, product_id, quantity, amount, restocked) VALUES (?,?,?,?,?)",
                [(cur.lastrowid, product_ids[i["spec"].sku], i["qty"], i["amount"], i["restocked"]) for i in r["items"]],
            )

        _insert_ad_spend(conn, brand_id, import_id, rng)
        _insert_inventory(conn, brand_id, import_id, product_ids, rng)
        _insert_statements(conn, brand_id, import_id, rng)
        total_rows = conn.execute(
            "SELECT (SELECT COUNT(*) FROM orders WHERE brand_id=?) + (SELECT COUNT(*) FROM refunds WHERE brand_id=?)", (brand_id, brand_id)
        ).fetchone()[0]
        conn.execute("UPDATE import_files SET row_count = ?, imported_rows = ? WHERE id = ?", (total_rows, total_rows, import_id))
    return brand_id


def _monthly_gross_sales(conn: sqlite3.Connection, brand_id: int) -> dict[str, float]:
    rows = conn.execute(
        "SELECT substr(order_date,1,7) p, SUM(net_amount) FROM orders WHERE brand_id=? AND status='completed' GROUP BY p",
        (brand_id,),
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _insert_ad_spend(conn: sqlite3.Connection, brand_id: int, import_id: int, rng: random.Random) -> None:
    """Ad spend ~14% of gross sales, split across channels. Only Marketplace Ads reports attributed revenue."""
    gross = _monthly_gross_sales(conn, brand_id)
    for period in PERIODS:
        total = gross.get(period, 0.0) * rng.uniform(0.13, 0.15)
        for channel, share in AD_CHANNELS.items():
            spend = round(total * share * rng.uniform(0.95, 1.05), 2)
            cpm = {"Meta": 18, "Google": 26, "TikTok": 11, "Marketplace Ads": 30}[channel]
            impressions = int(spend / cpm * 1000)
            clicks = int(impressions * rng.uniform(0.009, 0.014))
            attributed = round(spend * rng.uniform(3.4, 4.4), 2) if channel == "Marketplace Ads" else None
            conn.execute(
                "INSERT INTO ad_spend(brand_id, period, channel, spend, impressions, clicks, attributed_revenue, import_file_id) VALUES (?,?,?,?,?,?,?,?)",
                (brand_id, period, channel, spend, impressions, clicks, attributed, import_id),
            )


def _insert_inventory(conn: sqlite3.Connection, brand_id: int, import_id: int, product_ids: dict[str, int], rng: random.Random) -> None:
    """Supplier receipts + month-end warehouse snapshots derived from actual movements,
    then the planted discrepancies (S8a shrinkage, S8b phantom stock)."""
    sold = {(r[0], r[1]): int(r[2]) for r in conn.execute(
        """SELECT substr(o.order_date,1,7), oi.product_id, SUM(oi.quantity) FROM order_items oi
           JOIN orders o ON o.id = oi.order_id WHERE o.brand_id=? AND o.status='completed' GROUP BY 1,2""", (brand_id,))}
    restocked = {(r[0], r[1]): int(r[2]) for r in conn.execute(
        """SELECT substr(r.refund_date,1,7), ri.product_id, SUM(ri.quantity) FROM refund_items ri
           JOIN refunds r ON r.id = ri.refund_id WHERE r.brand_id=? AND ri.restocked=1 GROUP BY 1,2""", (brand_id,))}
    avg_monthly = {}
    for spec in PRODUCTS:
        pid = product_ids[spec.sku]
        avg_monthly[pid] = max(1, sum(sold.get((p, pid), 0) for p in PERIODS) / 12)

    receipt_seq = 0
    for spec in PRODUCTS:
        pid = product_ids[spec.sku]
        on_hand = int(avg_monthly[pid] * 2.0) + 10          # opening stock 31 Dec 2024
        if spec.sku == SHRINKAGE_SKU:
            on_hand += 160                                  # larger buffer so planted shrinkage never produces negative counts
        conn.execute(
            "INSERT INTO inventory_snapshots(brand_id, product_id, snapshot_date, quantity_on_hand, source, import_file_id) VALUES (?,?,?,?,?,?)",
            (brand_id, pid, f"{YEAR - 1}-12-31", on_hand, "warehouse_report", import_id),
        )
        for month in range(1, 13):
            period = f"{YEAR}-{month:02d}"
            demand = sold.get((period, pid), 0)
            # receive stock when cover drops below ~1.5 months of demand (peak months pre-stocked)
            cover_needed = avg_monthly[pid] * (3.0 if month in (10, 11) else 1.5)
            if spec.sku == SHRINKAGE_SKU:
                cover_needed += 200                         # keep true stock high enough that recorded counts stay positive
            if on_hand - demand < cover_needed:
                qty = int(avg_monthly[pid] * (3.5 if month in (10, 11) else 2.5)) + rng.randint(0, 5)
                receipt_seq += 1
                conn.execute(
                    "INSERT INTO supplier_receipts(brand_id, receipt_ref, product_id, received_date, quantity, unit_cost, supplier, import_file_id) VALUES (?,?,?,?,?,?,?,?)",
                    (brand_id, f"GRN-{YEAR}-{receipt_seq:04d}", pid, f"{period}-{rng.randint(2, 9):02d}", qty,
                     supplier_cost_for(spec, month), _supplier_for(spec), import_id),
                )
                on_hand += qty
            on_hand = on_hand - demand + restocked.get((period, pid), 0)
            recorded = on_hand
            if spec.sku == SHRINKAGE_SKU and month >= SHRINKAGE_FROM_MONTH:
                recorded = on_hand - SHRINKAGE_PER_MONTH * (month - SHRINKAGE_FROM_MONTH + 1)
            if spec.sku == PHANTOM_SKU and month >= PHANTOM_MONTH:
                recorded = on_hand + PHANTOM_UNITS
            conn.execute(
                "INSERT INTO inventory_snapshots(brand_id, product_id, snapshot_date, quantity_on_hand, source, import_file_id) VALUES (?,?,?,?,?,?)",
                (brand_id, pid, _month_end(period).isoformat(), recorded, "warehouse_report", import_id),
            )


def _supplier_for(spec: ProductSpec) -> str:
    return {"Candles": "Al Noor Fragrance Works", "Ceramics": "Terra Studio Co.", "Textiles": "Linea Textiles FZE",
            "Kitchen": "Oliveira Crafts", "Decor": "Dune Interiors Trading"}[spec.category]


def _insert_statements(conn: sqlite3.Connection, brand_id: int, import_id: int, rng: random.Random) -> None:
    """Seller-reported monthly P&L derived from the operational data, with planted distortions (S1, S4)."""
    gross = _monthly_gross_sales(conn, brand_id)
    refunds = {r[0]: float(r[1]) for r in conn.execute(
        "SELECT substr(refund_date,1,7) p, SUM(amount) FROM refunds WHERE brand_id=? GROUP BY p", (brand_id,))}
    cancelled = {r[0]: float(r[1]) for r in conn.execute(
        "SELECT substr(order_date,1,7) p, SUM(net_amount) FROM orders WHERE brand_id=? AND status='cancelled' GROUP BY p", (brand_id,))}
    cogs = {r[0]: float(r[1]) for r in conn.execute(
        """SELECT substr(o.order_date,1,7) p, SUM(oi.quantity*oi.unit_cost) FROM order_items oi JOIN orders o ON o.id=oi.order_id
           WHERE o.brand_id=? AND o.status='completed' GROUP BY p""", (brand_id,))}
    units = {r[0]: int(r[1]) for r in conn.execute(
        """SELECT substr(o.order_date,1,7) p, SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id
           WHERE o.brand_id=? AND o.status='completed' GROUP BY p""", (brand_id,))}
    ads = {r[0]: float(r[1]) for r in conn.execute(
        "SELECT period, SUM(spend) FROM ad_spend WHERE brand_id=? GROUP BY period", (brand_id,))}

    for period in PERIODS:
        net_sales = gross.get(period, 0.0) - refunds.get(period, 0.0)
        if period in REVENUE_OVERSTATED_PERIODS:
            # S1: seller's figure is gross of refunds and includes cancelled orders
            reported_revenue = gross.get(period, 0.0) + cancelled.get(period, 0.0)
        else:
            reported_revenue = net_sales * rng.uniform(0.9975, 1.0025)
        reported_cogs = cogs.get(period, 0.0) * rng.uniform(0.995, 1.005)
        reported_ads = ads.get(period, 0.0) * rng.uniform(0.99, 1.01)
        if period == AD_UNDERSTATED_PERIOD:
            reported_ads = ads.get(period, 0.0) * AD_UNDERSTATED_FACTOR     # S4
        other_opex = reported_revenue * rng.uniform(0.11, 0.13)
        conn.execute(
            """INSERT INTO seller_statements(brand_id, period, reported_revenue, reported_cogs, reported_ad_spend,
                                             reported_other_opex, reported_gross_profit, reported_units, source_document, import_file_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (brand_id, period, round(reported_revenue, 2), round(reported_cogs, 2), round(reported_ads, 2),
             round(other_opex, 2), round(reported_revenue - reported_cogs, 2), units.get(period, 0),
             f"Seller management accounts {period}.xlsx", import_id),
        )


def demo_summary(conn: sqlite3.Connection, brand_id: int) -> dict:
    row = conn.execute(
        """SELECT (SELECT COUNT(*) FROM orders WHERE brand_id=:b) AS orders,
                  (SELECT COUNT(*) FROM refunds WHERE brand_id=:b) AS refunds,
                  (SELECT COUNT(*) FROM products WHERE brand_id=:b) AS products,
                  (SELECT COUNT(*) FROM seller_statements WHERE brand_id=:b) AS statements""",
        {"b": brand_id},
    ).fetchone()
    return dict(row)


if __name__ == "__main__":  # pragma: no cover - manual utility
    from tell.db.connection import open_db

    c = open_db()
    bid = generate_demo(c)
    print(json.dumps(demo_summary(c, bid), indent=2))
