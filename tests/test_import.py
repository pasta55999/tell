"""CSV import: parsing, mapping, validation, duplicates, transactional writes, safety."""

from __future__ import annotations

import pytest

from tell.data.demo_generator import generate_demo
from tell.db import repository as repo
from tell.ingest import DATASETS, detect_mapping, file_sha256, import_validated, parse_csv, template_csv, validate
from tell.reports.exports import df_to_csv, safe_cell

import pandas as pd


@pytest.fixture()
def db(fresh_conn):
    b = generate_demo(fresh_conn)
    return fresh_conn, b


def _run(conn, b, key, csv_text, dayfirst=False, allow=False):
    raw = csv_text.encode()
    spec = DATASETS[key]
    df = parse_csv(raw, f"{key}.csv")
    mapping = detect_mapping(list(df.columns), spec)
    res = validate(df, mapping, spec, conn, b, file_sha256(raw), dayfirst)
    return spec, mapping, res, raw


def test_detect_mapping_uses_synonyms():
    m = detect_mapping(["Order ID", "Created at", "Lineitem sku", "Qty", "Lineitem price", "Financial Status"], DATASETS["orders"])
    assert m["order_ref"] == "Order ID" and m["order_date"] == "Created at" and m["sku"] == "Lineitem sku"
    assert m["quantity"] == "Qty" and m["unit_price"] == "Lineitem price" and m["status"] == "Financial Status"


def test_orders_import_groups_lines_and_rejects_bad_rows(db):
    conn, b = db
    csv_text = ("order_ref,order_date,sku,quantity,unit_price,line_discount,status\n"
                "N-1,2026-01-05,CAN-001,2,145,0,paid\nN-1,2026-01-05,TEX-003,1,390,39,paid\n"
                "N-2,2026-01-06,KIT-001,1,240,,cancelled\nN-3,bad-date,KIT-001,1,240,,paid\nN-4,2026-01-07,KIT-001,0,240,,paid\n")
    spec, mapping, res, raw = _run(conn, b, "orders", csv_text)
    assert len(res.valid) == 3 and res.error_rows == 2
    assert {e.field for e in res.errors} == {"order_date", "quantity"}
    summary = import_validated(conn, b, spec, "orders.csv", file_sha256(raw), mapping, res)
    assert summary.imported == 2 and summary.rejected == 2
    o = repo.fetch_one(conn, "SELECT * FROM orders WHERE order_ref='N-1'")
    assert o["gross_amount"] == 680 and o["discount_amount"] == 39 and o["net_amount"] == 641 and o["status"] == "completed"
    assert repo.scalar(conn, "SELECT COUNT(*) FROM order_items WHERE order_id=?", (o["id"],)) == 2


def test_duplicate_file_and_duplicate_rows(db):
    conn, b = db
    csv_text = "period,channel,spend\n2026-01,Meta,100\n2026-01,Meta,120\n2025-03,Meta,1\n"
    spec, mapping, res, raw = _run(conn, b, "ad_spend", csv_text)
    assert res.duplicate_rows_in_file == 1 and res.existing_in_db == 1 and len(res.valid) == 1
    import_validated(conn, b, spec, "ads.csv", file_sha256(raw), mapping, res)
    spec, mapping, res2, raw = _run(conn, b, "ad_spend", csv_text)
    assert res2.file_already_imported and len(res2.valid) == 0
    with pytest.raises(ValueError):
        import_validated(conn, b, spec, "ads.csv", file_sha256(raw), mapping, res2)
    assert repo.scalar(conn, "SELECT spend FROM ad_spend WHERE brand_id=? AND period='2025-03' AND channel='Meta'", (b,)) != 1   # original untouched


def test_refund_requires_existing_order(db):
    conn, b = db
    csv_text = "refund_ref,order_ref,refund_date,amount\nR-X,NOPE,2025-05-01,10\nR-Y,SS-2025-00001,2025-05-01,10\n"
    spec, mapping, res, raw = _run(conn, b, "refunds", csv_text)
    assert len(res.valid) == 1 and res.errors[0].field == "order_ref"


def test_missing_required_mapping_blocks_import(db):
    conn, b = db
    spec = DATASETS["statements"]
    df = parse_csv(b"month,something\n2025-01,5\n", "s.csv")
    res = validate(df, {"period": "month", "reported_revenue": None}, spec, conn, b)
    assert res.errors and "reported_revenue" in res.errors[0].field and not res.valid


def test_date_and_number_parsing(db):
    conn, b = db
    csv_text = "sku,snapshot_date,quantity_on_hand\nCAN-001,31/01/2026,\"1,250\"\nCAN-002,2026-01-31,AED 40\nCAN-003,2026-01-31,12.5\n"
    spec, mapping, res, raw = _run(conn, b, "inventory", csv_text, dayfirst=True)
    assert len(res.valid) == 2 and res.valid[0]["snapshot_date"] == "2026-01-31" and res.valid[0]["quantity_on_hand"] == 1250
    assert res.errors[0].field == "quantity_on_hand"


def test_period_formats():
    from tell.ingest.csv_import import _parse_period
    assert _parse_period("2025-03", False) == "2025-03"
    assert _parse_period("Mar 2025", False) == "2025-03"
    assert _parse_period("03/2025", False) == "2025-03"
    assert _parse_period("2025-03-15", False) == "2025-03"
    with pytest.raises(ValueError):
        _parse_period("2025-13", False)


def test_parse_csv_rejects_bad_inputs():
    with pytest.raises(ValueError):
        parse_csv(b"", "x.csv")
    with pytest.raises(ValueError):
        parse_csv(b"a,b\n1,2\n", "x.xlsx")
    with pytest.raises(ValueError):
        parse_csv(b"\x00\x01binary", "x.csv")
    with pytest.raises(ValueError):
        parse_csv(b"a,b\n1,2\n", "x.csv", max_mb=0)
    with pytest.raises(ValueError):
        parse_csv(b"a,a\n1,2\n", "x.csv")


def test_import_is_transactional(db, monkeypatch):
    conn, b = db
    csv_text = "sku,name,list_price\nZ-1,One,10\nZ-2,Two,20\n"
    spec, mapping, res, raw = _run(conn, b, "products", csv_text)
    import tell.ingest.csv_import as mod
    orig = mod._write_rows

    def boom(*a, **k):
        orig(*a, **k)
        raise RuntimeError("disk full")

    monkeypatch.setattr(mod, "_write_rows", boom)
    with pytest.raises(RuntimeError):
        import_validated(conn, b, spec, "p.csv", file_sha256(raw), mapping, res)
    assert repo.scalar(conn, "SELECT COUNT(*) FROM products WHERE sku LIKE 'Z-%'") == 0
    assert repo.scalar(conn, "SELECT COUNT(*) FROM import_files WHERE dataset='products'") == 0


def test_sql_injection_in_values_is_inert(db):
    conn, b = db
    csv_text = "sku,name,list_price\n\"X'); DROP TABLE orders; --\",Evil,10\n"
    spec, mapping, res, raw = _run(conn, b, "products", csv_text)
    import_validated(conn, b, spec, "p.csv", file_sha256(raw), mapping, res)
    assert repo.scalar(conn, "SELECT COUNT(*) FROM orders") > 1000
    assert repo.scalar(conn, "SELECT name FROM products WHERE sku = ?", ("X'); DROP TABLE orders; --",)) == "Evil"


def test_csv_export_neutralises_formulas():
    assert safe_cell("=SUM(A1)") == "'=SUM(A1)"
    assert safe_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert safe_cell("-12.5") == "-12.5"
    assert safe_cell(3) == 3
    out = df_to_csv(pd.DataFrame({"a": ["=1+1", "ok"]}))
    assert "'=1+1" in out


def test_templates_exist_for_all_datasets():
    for key, spec in DATASETS.items():
        t = template_csv(spec)
        assert t.splitlines()[0].split(",") == [f.name for f in spec.fields]
