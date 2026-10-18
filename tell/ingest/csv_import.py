"""CSV import pipeline: parse -> detect columns -> map -> validate -> preview -> import.

Design rules:
  * Nothing is written until validation has run; the import is a single transaction.
  * Invalid rows are reported (row number, field, message) and never silently dropped.
  * Duplicate detection at file level (sha256 per brand+dataset) and row level (natural keys).
  * All SQL is parameterised. Uploaded values are stored verbatim (no formula evaluation).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from tell.db.connection import transaction

MAX_ROWS = 250_000


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str                      # str | date | period | number | int | bool
    required: bool = False
    synonyms: tuple[str, ...] = ()
    description: str = ""
    min_value: float | None = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    table: str
    natural_key: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    description: str

    @property
    def required(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.required]


DATASETS: dict[str, DatasetSpec] = {
    "products": DatasetSpec("products", "Products & costs", "products", ("sku",), (
        FieldSpec("sku", "str", True, ("sku", "product_code", "item_code", "variant_sku"), "Unique product code"),
        FieldSpec("name", "str", True, ("name", "product_name", "title", "product"), "Product name"),
        FieldSpec("category", "str", False, ("category", "product_type", "collection")),
        FieldSpec("list_price", "number", True, ("list_price", "price", "unit_price", "rrp", "selling_price"), "List price", 0),
        FieldSpec("standard_cost", "number", False, ("standard_cost", "cost", "unit_cost", "cogs_unit", "landed_cost"), "Unit cost", 0),
    ), "One row per SKU."),
    "orders": DatasetSpec("orders", "Orders (one row per line item)", "orders", ("order_ref",), (
        FieldSpec("order_ref", "str", True, ("order_ref", "order_id", "order_number", "order", "name"), "Order reference"),
        FieldSpec("order_date", "date", True, ("order_date", "date", "created_at", "placed_at", "order_created")),
        FieldSpec("channel", "str", False, ("channel", "sales_channel", "source", "store")),
        FieldSpec("status", "str", False, ("status", "order_status", "financial_status", "fulfillment_status"), "completed or cancelled", choices=("completed", "cancelled")),
        FieldSpec("customer_ref", "str", False, ("customer_ref", "customer_id", "customer", "email_hash")),
        FieldSpec("sku", "str", True, ("sku", "lineitem_sku", "product_code", "variant_sku")),
        FieldSpec("quantity", "int", True, ("quantity", "qty", "lineitem_quantity", "units"), min_value=1),
        FieldSpec("unit_price", "number", True, ("unit_price", "price", "lineitem_price", "item_price"), min_value=0),
        FieldSpec("line_discount", "number", False, ("line_discount", "discount", "discount_amount", "lineitem_discount"), min_value=0),
        FieldSpec("unit_cost", "number", False, ("unit_cost", "cost", "cogs_unit", "lineitem_cost"), min_value=0),
        FieldSpec("shipping_amount", "number", False, ("shipping_amount", "shipping", "shipping_charged", "shipping_price"), min_value=0),
    ), "Order lines; rows with the same order_ref are grouped into one order. Status defaults to completed."),
    "refunds": DatasetSpec("refunds", "Refunds & returns", "refunds", ("refund_ref",), (
        FieldSpec("refund_ref", "str", True, ("refund_ref", "refund_id", "return_id", "credit_note")),
        FieldSpec("order_ref", "str", True, ("order_ref", "order_id", "order_number", "order")),
        FieldSpec("refund_date", "date", True, ("refund_date", "date", "processed_at", "created_at", "posted")),
        FieldSpec("amount", "number", True, ("amount", "refund_amount", "total", "value"), min_value=0),
        FieldSpec("reason", "str", False, ("reason", "return_reason", "note")),
        FieldSpec("sku", "str", False, ("sku", "product_code", "lineitem_sku")),
        FieldSpec("quantity", "int", False, ("quantity", "qty", "units"), min_value=1),
        FieldSpec("restocked", "bool", False, ("restocked", "restock", "returned_to_stock")),
    ), "One row per refund (optionally one row per refunded line with sku/quantity). order_ref must exist."),
    "ad_spend": DatasetSpec("ad_spend", "Advertising spend", "ad_spend", ("period", "channel"), (
        FieldSpec("period", "period", True, ("period", "month", "date", "reporting_month")),
        FieldSpec("channel", "str", True, ("channel", "platform", "source", "network")),
        FieldSpec("spend", "number", True, ("spend", "cost", "amount_spent", "amount"), min_value=0),
        FieldSpec("impressions", "int", False, ("impressions", "imps"), min_value=0),
        FieldSpec("clicks", "int", False, ("clicks", "link_clicks"), min_value=0),
        FieldSpec("attributed_revenue", "number", False, ("attributed_revenue", "conversion_value", "purchase_value", "revenue", "sales"), min_value=0),
    ), "Monthly spend per channel. Leave attributed_revenue blank when the platform does not report it."),
    "statements": DatasetSpec("statements", "Seller financial statements", "seller_statements", ("period",), (
        FieldSpec("period", "period", True, ("period", "month", "date")),
        FieldSpec("reported_revenue", "number", True, ("reported_revenue", "revenue", "net_revenue", "sales", "turnover")),
        FieldSpec("reported_cogs", "number", False, ("reported_cogs", "cogs", "cost_of_sales", "cost_of_goods_sold")),
        FieldSpec("reported_ad_spend", "number", False, ("reported_ad_spend", "advertising", "marketing", "ad_spend", "marketing_spend")),
        FieldSpec("reported_other_opex", "number", False, ("reported_other_opex", "other_opex", "opex", "operating_expenses")),
        FieldSpec("reported_gross_profit", "number", False, ("reported_gross_profit", "gross_profit")),
        FieldSpec("reported_units", "int", False, ("reported_units", "units", "units_sold")),
        FieldSpec("source_document", "str", False, ("source_document", "source", "file", "document")),
    ), "Monthly management accounts as provided by the seller."),
    "inventory": DatasetSpec("inventory", "Inventory snapshots", "inventory_snapshots", ("sku", "snapshot_date", "source"), (
        FieldSpec("sku", "str", True, ("sku", "product_code", "variant_sku")),
        FieldSpec("snapshot_date", "date", True, ("snapshot_date", "date", "count_date", "as_of")),
        FieldSpec("quantity_on_hand", "int", True, ("quantity_on_hand", "quantity", "qty", "on_hand", "stock", "available")),
        FieldSpec("source", "str", False, ("source", "location", "warehouse", "system")),
    ), "Month-end stock counts per SKU."),
    "supplier_receipts": DatasetSpec("supplier_receipts", "Supplier receipts / purchase costs", "supplier_receipts", ("receipt_ref",), (
        FieldSpec("receipt_ref", "str", True, ("receipt_ref", "grn", "po_number", "invoice", "receipt_id")),
        FieldSpec("sku", "str", True, ("sku", "product_code")),
        FieldSpec("received_date", "date", True, ("received_date", "date", "delivery_date", "invoice_date")),
        FieldSpec("quantity", "int", True, ("quantity", "qty", "units"), min_value=1),
        FieldSpec("unit_cost", "number", True, ("unit_cost", "cost", "price", "unit_price"), min_value=0),
        FieldSpec("supplier", "str", False, ("supplier", "vendor")),
    ), "Goods received with the invoiced unit cost."),
}


# ----------------------------------------------------------------- parsing

def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_csv(data: bytes, filename: str, max_mb: int = 25) -> pd.DataFrame:
    """Parse raw bytes into a DataFrame of strings. Raises ValueError with a user-facing message."""
    if len(data) == 0:
        raise ValueError("The file is empty.")
    if len(data) > max_mb * 1024 * 1024:
        raise ValueError(f"File is larger than the {max_mb} MB limit.")
    if not filename.lower().endswith(".csv"):
        raise ValueError("Only .csv files are supported.")
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode the file as text (UTF-8 or Windows-1252 expected).")
    if "\x00" in text:
        raise ValueError("The file contains binary data and is not a CSV.")
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ","
    header = next(csv.reader(io.StringIO(text), delimiter=sep), [])
    header = [h.strip() for h in header]
    if len(header) != len(set(header)):
        raise ValueError("Duplicate column headers found.")
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False, engine="python", on_bad_lines="error")
    except Exception as exc:  # pandas raises several error types
        raise ValueError(f"The CSV could not be parsed: {exc}") from exc
    if df.empty or len(df.columns) < 2:
        raise ValueError("No data rows or fewer than two columns found.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"The file has {len(df):,} rows; the limit is {MAX_ROWS:,}.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def detect_mapping(columns: list[str], spec: DatasetSpec) -> dict[str, str | None]:
    """Suggest a field -> column mapping using normalised synonyms. Unmatched fields map to None."""
    normalised = {_norm(c): c for c in columns}
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for f in spec.fields:
        found = None
        for syn in (f.name, *f.synonyms):
            col = normalised.get(_norm(syn))
            if col and col not in used:
                found = col
                break
        mapping[f.name] = found
        if found:
            used.add(found)
    return mapping


# ----------------------------------------------------------------- validation

@dataclass
class RowError:
    row: int
    field: str
    message: str


@dataclass
class ValidationResult:
    dataset: str
    rows_total: int
    valid: list[dict[str, Any]] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_rows_in_file: int = 0
    existing_in_db: int = 0
    file_already_imported: bool = False

    @property
    def error_rows(self) -> int:
        return len({e.row for e in self.errors})

    def errors_df(self) -> pd.DataFrame:
        return pd.DataFrame([e.__dict__ for e in self.errors])

    def preview_df(self, n: int = 10) -> pd.DataFrame:
        return pd.DataFrame(self.valid[:n])


_NUM_CLEAN = re.compile(r"[^0-9+\-.]")
_SCI = re.compile(r"[-+]?\d*\.?\d+e[-+]?\d+", re.I)


def _parse_number(raw: str) -> float:
    s = raw.strip()
    if _SCI.fullmatch(s):
        return float(s)
    neg = s.startswith("(") and s.endswith(")")
    s = _NUM_CLEAN.sub("", s)      # drops currency symbols/codes and thousands separators
    if s in ("", "-", ".", "+"):
        raise ValueError("not a number")
    try:
        v = float(s)
    except ValueError as exc:
        raise ValueError("not a number") from exc
    return -v if neg else v


def _parse_date(raw: str, dayfirst: bool) -> date:
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    ts = pd.to_datetime(s, dayfirst=dayfirst, errors="coerce")
    if pd.isna(ts):
        raise ValueError("unrecognised date")
    return ts.date()


def _parse_period(raw: str, dayfirst: bool) -> str:
    s = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = int(s[:4]), int(s[5:])
        if not 1 <= m <= 12:
            raise ValueError("month out of range")
        return s
    if re.fullmatch(r"\d{4}/\d{2}", s) or re.fullmatch(r"\d{4}\d{2}", s):
        return f"{s[:4]}-{s[-2:]}"
    for fmt in ("%b %Y", "%B %Y", "%b-%Y", "%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return f"{d.year:04d}-{d.month:02d}"
        except ValueError:
            pass
    d = _parse_date(s, dayfirst)
    return f"{d.year:04d}-{d.month:02d}"


def _coerce(f: FieldSpec, raw: str, dayfirst: bool) -> Any:
    raw = "" if raw is None else str(raw)
    if raw.strip() == "":
        if f.required:
            raise ValueError("required value is missing")
        return None
    if f.kind == "str":
        v = raw.strip()
        if len(v) > 500:
            raise ValueError("text longer than 500 characters")
        if f.choices:
            low = v.lower()
            alias = {"complete": "completed", "paid": "completed", "fulfilled": "completed", "delivered": "completed", "shipped": "completed",
                     "canceled": "cancelled", "voided": "cancelled", "refunded": "completed"}
            low = alias.get(low, low)
            if low not in f.choices:
                raise ValueError(f"must be one of {', '.join(f.choices)}")
            return low
        return v
    if f.kind == "number":
        v = _parse_number(raw)
        if f.min_value is not None and v < f.min_value:
            raise ValueError(f"must be >= {f.min_value:g}")
        return round(v, 4)
    if f.kind == "int":
        v = _parse_number(raw)
        if abs(v - round(v)) > 1e-9:
            raise ValueError("must be a whole number")
        v = int(round(v))
        if f.min_value is not None and v < f.min_value:
            raise ValueError(f"must be >= {f.min_value:g}")
        return v
    if f.kind == "date":
        d = _parse_date(raw, dayfirst)
        if d > date.today().replace(year=date.today().year + 1):
            raise ValueError("date is more than a year in the future")
        return d.isoformat()
    if f.kind == "period":
        return _parse_period(raw, dayfirst)
    if f.kind == "bool":
        low = raw.strip().lower()
        if low in ("1", "true", "yes", "y", "t"):
            return 1
        if low in ("0", "false", "no", "n", "f"):
            return 0
        raise ValueError("must be yes/no or true/false")
    raise ValueError("unknown field type")


def validate(df: pd.DataFrame, mapping: dict[str, str | None], spec: DatasetSpec, conn: sqlite3.Connection, brand_id: int,
             sha256: str | None = None, dayfirst: bool = False) -> ValidationResult:
    """Type-check every row, apply dataset rules, and detect duplicates in the file and the database."""
    res = ValidationResult(dataset=spec.key, rows_total=int(len(df)))
    missing = [f.name for f in spec.required if not mapping.get(f.name)]
    if missing:
        res.errors.append(RowError(0, ",".join(missing), "Required fields are not mapped to any column: " + ", ".join(missing)))
        return res
    for name, col in mapping.items():
        if col and col not in df.columns:
            res.errors.append(RowError(0, name, f"Mapped column '{col}' does not exist in the file."))
            return res
    if sha256 and conn.execute("SELECT 1 FROM import_files WHERE brand_id = ? AND dataset = ? AND sha256 = ?", (brand_id, spec.key, sha256)).fetchone():
        res.file_already_imported = True
        res.warnings.append("This exact file has already been imported for this brand and dataset.")

    seen_keys: set[tuple] = set()
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(df.to_dict("records"), start=2):   # row 1 is the header
        row: dict[str, Any] = {}
        ok = True
        for f in spec.fields:
            col = mapping.get(f.name)
            try:
                row[f.name] = _coerce(f, raw.get(col, "") if col else "", dayfirst)
            except ValueError as exc:
                res.errors.append(RowError(i, f.name, f"{exc} (value: '{str(raw.get(col, ''))[:40]}')"))
                ok = False
        if not ok:
            continue
        row["_row"] = i
        rows.append(row)

    # dataset-specific checks and duplicate detection
    if spec.key == "orders":
        _validate_orders(rows, res, conn, brand_id)
    else:
        existing = _existing_keys(conn, brand_id, spec)
        for row in rows:
            key = tuple(row.get(k) if row.get(k) is not None else ("warehouse_report" if k == "source" else None) for k in spec.natural_key)
            if key in seen_keys:
                res.duplicate_rows_in_file += 1
                res.errors.append(RowError(row["_row"], "/".join(spec.natural_key), f"duplicate key {key} within the file"))
                continue
            seen_keys.add(key)
            if key in existing:
                res.existing_in_db += 1
                continue
            res.valid.append(row)
        if spec.key in ("refunds", "inventory", "supplier_receipts"):
            _check_references(res, conn, brand_id, spec)
    if res.existing_in_db:
        res.warnings.append(f"{res.existing_in_db} row(s) already exist in the database (same key) and will be skipped.")
    return res


def _existing_keys(conn: sqlite3.Connection, brand_id: int, spec: DatasetSpec) -> set[tuple]:
    table_cols = {"products": "sku", "refunds": "refund_ref", "ad_spend": "period, channel", "seller_statements": "period",
                  "inventory_snapshots": "(SELECT sku FROM products p WHERE p.id = product_id), snapshot_date, source",
                  "supplier_receipts": "receipt_ref"}[spec.table]
    rows = conn.execute(f"SELECT {table_cols} FROM {spec.table} WHERE brand_id = ?", (brand_id,)).fetchall()  # noqa: S608 - fixed identifiers
    return {tuple(r) for r in rows}


def _check_references(res: ValidationResult, conn: sqlite3.Connection, brand_id: int, spec: DatasetSpec) -> None:
    skus = {r[0] for r in conn.execute("SELECT sku FROM products WHERE brand_id = ?", (brand_id,))}
    orders = {r[0] for r in conn.execute("SELECT order_ref FROM orders WHERE brand_id = ?", (brand_id,))} if spec.key == "refunds" else set()
    keep = []
    for row in res.valid:
        if row.get("sku") and row["sku"] not in skus:
            if spec.key == "refunds":
                res.warnings.append(f"Row {row['_row']}: SKU '{row['sku']}' not found; refund will be imported without a line item.")
                row["sku"] = None
            else:
                res.errors.append(RowError(row["_row"], "sku", f"unknown SKU '{row['sku']}' - import products first"))
                continue
        if spec.key == "refunds" and row["order_ref"] not in orders:
            res.errors.append(RowError(row["_row"], "order_ref", f"order '{row['order_ref']}' not found - import orders first"))
            continue
        keep.append(row)
    res.valid = keep


def _validate_orders(rows: list[dict[str, Any]], res: ValidationResult, conn: sqlite3.Connection, brand_id: int) -> None:
    existing = {r[0] for r in conn.execute("SELECT order_ref FROM orders WHERE brand_id = ?", (brand_id,))}
    skus = {r[0] for r in conn.execute("SELECT sku FROM products WHERE brand_id = ?", (brand_id,))}
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["order_ref"], []).append(row)
    unknown_skus: set[str] = set()
    for ref, lines in grouped.items():
        if ref in existing:
            res.existing_in_db += 1
            continue
        dates = {l["order_date"] for l in lines}
        if len(dates) > 1:
            res.errors.append(RowError(lines[0]["_row"], "order_date", f"order '{ref}' has conflicting dates across its lines"))
            continue
        line_keys = [(l["sku"],) for l in lines]
        if len(line_keys) != len(set(line_keys)):
            res.duplicate_rows_in_file += 1
            res.errors.append(RowError(lines[0]["_row"], "sku", f"order '{ref}' lists the same SKU more than once"))
            continue
        for l in lines:
            if l["sku"] not in skus:
                unknown_skus.add(l["sku"])
        res.valid.extend(lines)
    if unknown_skus:
        res.warnings.append(f"{len(unknown_skus)} SKU(s) not in the product list will be created with the line price as list price and no cost: "
                            + ", ".join(sorted(unknown_skus)[:8]) + (" ..." if len(unknown_skus) > 8 else ""))


# ----------------------------------------------------------------- import

@dataclass
class ImportSummary:
    import_file_id: int
    dataset: str
    imported: int
    rejected: int
    skipped: int
    warnings: list[str]


def import_validated(conn: sqlite3.Connection, brand_id: int, spec: DatasetSpec, filename: str, sha256: str,
                     mapping: dict[str, str | None], result: ValidationResult, allow_reimport: bool = False) -> ImportSummary:
    """Write validated rows in one transaction and record the import. Raises on duplicate file unless allowed."""
    if result.file_already_imported and not allow_reimport:
        raise ValueError("This file was already imported. Tick 'allow re-import' to import the remaining new rows.")
    if not result.valid:
        raise ValueError("No valid rows to import.")
    import json

    with transaction(conn):
        cur = conn.execute(
            """INSERT INTO import_files(brand_id, dataset, filename, sha256, row_count, imported_rows, rejected_rows, skipped_rows, column_mapping, notes, status)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'running')
               ON CONFLICT(brand_id, dataset, sha256) DO UPDATE SET imported_at = datetime('now'), status = 'running'""",
            (brand_id, spec.key, filename[:200], sha256, result.rows_total, 0, result.error_rows, result.existing_in_db, json.dumps(mapping), "; ".join(result.warnings)[:2000]),
        )
        import_id = int(conn.execute("SELECT id FROM import_files WHERE brand_id = ? AND dataset = ? AND sha256 = ?", (brand_id, spec.key, sha256)).fetchone()[0])
        imported = _write_rows(conn, brand_id, spec, result.valid, import_id)
        conn.execute("UPDATE import_files SET imported_rows = ?, status = 'completed' WHERE id = ?", (imported, import_id))
    return ImportSummary(import_id, spec.key, imported, result.error_rows, result.existing_in_db, result.warnings)


def _product_ids(conn: sqlite3.Connection, brand_id: int) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute("SELECT sku, id FROM products WHERE brand_id = ?", (brand_id,))}


def _write_rows(conn: sqlite3.Connection, brand_id: int, spec: DatasetSpec, rows: list[dict[str, Any]], import_id: int) -> int:
    k = spec.key
    if k == "products":
        conn.executemany("INSERT INTO products(brand_id, sku, name, category, list_price, standard_cost, import_file_id) VALUES (?,?,?,?,?,?,?)",
                         [(brand_id, r["sku"], r["name"], r.get("category"), r["list_price"], r.get("standard_cost"), import_id) for r in rows])
        return len(rows)
    if k == "orders":
        pids = _product_ids(conn, brand_id)
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["order_ref"], []).append(r)
        for ref, lines in grouped.items():
            for l in lines:
                if l["sku"] not in pids:
                    c = conn.execute("INSERT INTO products(brand_id, sku, name, list_price, import_file_id) VALUES (?,?,?,?,?)",
                                     (brand_id, l["sku"], l["sku"], l["unit_price"], import_id))
                    pids[l["sku"]] = int(c.lastrowid)
            gross = round(sum(l["quantity"] * l["unit_price"] for l in lines), 2)
            disc = round(sum(l.get("line_discount") or 0 for l in lines), 2)
            ship = max((l.get("shipping_amount") or 0) for l in lines)
            first = lines[0]
            c = conn.execute(
                """INSERT INTO orders(brand_id, order_ref, order_date, customer_ref, channel, status, gross_amount, discount_amount, shipping_amount, net_amount, import_file_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (brand_id, ref, first["order_date"], first.get("customer_ref"), first.get("channel") or "Unspecified", first.get("status") or "completed",
                 gross, disc, ship, round(gross - disc, 2), import_id))
            conn.executemany("INSERT INTO order_items(order_id, product_id, quantity, unit_price, unit_cost, line_discount) VALUES (?,?,?,?,?,?)",
                             [(c.lastrowid, pids[l["sku"]], l["quantity"], l["unit_price"], l.get("unit_cost"), l.get("line_discount") or 0) for l in lines])
        return len(grouped)
    if k == "refunds":
        pids = _product_ids(conn, brand_id)
        oids = {r[0]: r[1] for r in conn.execute("SELECT order_ref, id FROM orders WHERE brand_id = ?", (brand_id,))}
        for r in rows:
            c = conn.execute("INSERT INTO refunds(brand_id, refund_ref, order_id, refund_date, amount, reason, import_file_id) VALUES (?,?,?,?,?,?,?)",
                             (brand_id, r["refund_ref"], oids[r["order_ref"]], r["refund_date"], r["amount"], r.get("reason"), import_id))
            if r.get("sku"):
                conn.execute("INSERT INTO refund_items(refund_id, product_id, quantity, amount, restocked) VALUES (?,?,?,?,?)",
                             (c.lastrowid, pids[r["sku"]], r.get("quantity") or 1, r["amount"], r.get("restocked") or 0))
        return len(rows)
    if k == "ad_spend":
        conn.executemany("INSERT INTO ad_spend(brand_id, period, channel, spend, impressions, clicks, attributed_revenue, import_file_id) VALUES (?,?,?,?,?,?,?,?)",
                         [(brand_id, r["period"], r["channel"], r["spend"], r.get("impressions"), r.get("clicks"), r.get("attributed_revenue"), import_id) for r in rows])
        return len(rows)
    if k == "statements":
        conn.executemany(
            """INSERT INTO seller_statements(brand_id, period, reported_revenue, reported_cogs, reported_ad_spend, reported_other_opex, reported_gross_profit, reported_units, source_document, import_file_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [(brand_id, r["period"], r["reported_revenue"], r.get("reported_cogs"), r.get("reported_ad_spend"), r.get("reported_other_opex"),
              r.get("reported_gross_profit"), r.get("reported_units"), r.get("source_document"), import_id) for r in rows])
        return len(rows)
    if k == "inventory":
        pids = _product_ids(conn, brand_id)
        conn.executemany("INSERT INTO inventory_snapshots(brand_id, product_id, snapshot_date, quantity_on_hand, source, import_file_id) VALUES (?,?,?,?,?,?)",
                         [(brand_id, pids[r["sku"]], r["snapshot_date"], r["quantity_on_hand"], r.get("source") or "warehouse_report", import_id) for r in rows])
        return len(rows)
    if k == "supplier_receipts":
        pids = _product_ids(conn, brand_id)
        conn.executemany("INSERT INTO supplier_receipts(brand_id, receipt_ref, product_id, received_date, quantity, unit_cost, supplier, import_file_id) VALUES (?,?,?,?,?,?,?,?)",
                         [(brand_id, r["receipt_ref"], pids[r["sku"]], r["received_date"], r["quantity"], r["unit_cost"], r.get("supplier"), import_id) for r in rows])
        return len(rows)
    raise ValueError(f"Unknown dataset {k}")


def template_csv(spec: DatasetSpec) -> str:
    """Header-only CSV template with an example row, for download."""
    example = {"str": "ABC-001", "date": "2025-01-31", "period": "2025-01", "number": "100.00", "int": "1", "bool": "yes"}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([f.name for f in spec.fields])
    w.writerow([example[f.kind] if f.kind != "str" or f.name not in ("status",) else "completed" for f in spec.fields])
    return buf.getvalue()
