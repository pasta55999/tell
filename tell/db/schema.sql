-- Tell database schema (SQLite). Applied idempotently by tell.db.connection.init_db.
-- Raw imported data lives in the source tables; derived analysis lives in
-- analysis_runs / findings / finding_evidence / diligence_questions / reports.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version      INTEGER PRIMARY KEY,
    applied_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspaces (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS brands (
    id                 INTEGER PRIMARY KEY,
    workspace_id       INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    slug               TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    category           TEXT,
    description        TEXT,
    reporting_currency TEXT NOT NULL DEFAULT 'AED',
    fiscal_year_start_month INTEGER NOT NULL DEFAULT 1 CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
    date_convention    TEXT NOT NULL DEFAULT 'posting_date',  -- how refunds are assigned to periods
    is_demo            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_files (
    id             INTEGER PRIMARY KEY,
    brand_id       INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    dataset        TEXT NOT NULL,             -- orders | refunds | ad_spend | products | statements | inventory | demo
    filename       TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    row_count      INTEGER NOT NULL DEFAULT 0,
    imported_rows  INTEGER NOT NULL DEFAULT 0,
    rejected_rows  INTEGER NOT NULL DEFAULT 0,
    skipped_rows   INTEGER NOT NULL DEFAULT 0,
    column_mapping TEXT,                      -- JSON
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'completed',
    imported_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (brand_id, dataset, sha256)
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY,
    brand_id        INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    sku             TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT,
    list_price      REAL NOT NULL CHECK (list_price >= 0),
    standard_cost   REAL CHECK (standard_cost IS NULL OR standard_cost >= 0),
    is_active       INTEGER NOT NULL DEFAULT 1,
    import_file_id  INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, sku)
);

CREATE TABLE IF NOT EXISTS orders (
    id               INTEGER PRIMARY KEY,
    brand_id         INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    order_ref        TEXT NOT NULL,
    order_date       TEXT NOT NULL,             -- ISO date
    customer_ref     TEXT,
    channel          TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('completed', 'cancelled')),
    currency         TEXT NOT NULL DEFAULT 'AED',
    gross_amount     REAL NOT NULL CHECK (gross_amount >= 0),     -- sum(qty * unit_price)
    discount_amount  REAL NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    shipping_amount  REAL NOT NULL DEFAULT 0 CHECK (shipping_amount >= 0),
    net_amount       REAL NOT NULL,                                -- gross - discount (ex shipping)
    import_file_id   INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, order_ref)
);
CREATE INDEX IF NOT EXISTS idx_orders_brand_date ON orders(brand_id, order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(brand_id, status);

CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  REAL NOT NULL CHECK (unit_price >= 0),
    unit_cost   REAL CHECK (unit_cost IS NULL OR unit_cost >= 0),  -- cost recorded at time of sale
    line_discount REAL NOT NULL DEFAULT 0 CHECK (line_discount >= 0)
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);

CREATE TABLE IF NOT EXISTS refunds (
    id             INTEGER PRIMARY KEY,
    brand_id       INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    refund_ref     TEXT NOT NULL,
    order_id       INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    refund_date    TEXT NOT NULL,
    amount         REAL NOT NULL CHECK (amount >= 0),
    reason         TEXT,
    import_file_id INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, refund_ref)
);
CREATE INDEX IF NOT EXISTS idx_refunds_brand_date ON refunds(brand_id, refund_date);
CREATE INDEX IF NOT EXISTS idx_refunds_order ON refunds(order_id);

CREATE TABLE IF NOT EXISTS refund_items (
    id          INTEGER PRIMARY KEY,
    refund_id   INTEGER NOT NULL REFERENCES refunds(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    amount      REAL NOT NULL CHECK (amount >= 0),
    restocked   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_refund_items_product ON refund_items(product_id);

CREATE TABLE IF NOT EXISTS ad_spend (
    id                 INTEGER PRIMARY KEY,
    brand_id           INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    period             TEXT NOT NULL,          -- YYYY-MM
    channel            TEXT NOT NULL,
    spend              REAL NOT NULL CHECK (spend >= 0),
    impressions        INTEGER,
    clicks             INTEGER,
    attributed_revenue REAL,                   -- platform-reported; NULL when not available
    import_file_id     INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, period, channel)
);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id              INTEGER PRIMARY KEY,
    brand_id        INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    snapshot_date   TEXT NOT NULL,             -- ISO date (month end)
    quantity_on_hand INTEGER NOT NULL,
    source          TEXT NOT NULL DEFAULT 'warehouse_report',
    import_file_id  INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, product_id, snapshot_date, source)
);

CREATE TABLE IF NOT EXISTS supplier_receipts (
    id             INTEGER PRIMARY KEY,
    brand_id       INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    receipt_ref    TEXT NOT NULL,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    received_date  TEXT NOT NULL,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_cost      REAL NOT NULL CHECK (unit_cost >= 0),
    supplier       TEXT,
    import_file_id INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, receipt_ref)
);
CREATE INDEX IF NOT EXISTS idx_receipts_product_date ON supplier_receipts(product_id, received_date);

CREATE TABLE IF NOT EXISTS seller_statements (
    id                 INTEGER PRIMARY KEY,
    brand_id           INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    period             TEXT NOT NULL,          -- YYYY-MM
    reported_revenue   REAL NOT NULL,
    reported_cogs      REAL,
    reported_ad_spend  REAL,
    reported_other_opex REAL,
    reported_gross_profit REAL,
    reported_units     INTEGER,
    source_document    TEXT,
    import_file_id     INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
    UNIQUE (brand_id, period)
);

-- ---------------------------------------------------------------- analysis

CREATE TABLE IF NOT EXISTS analysis_runs (
    id               INTEGER PRIMARY KEY,
    brand_id         INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    started_at       TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at      TEXT,
    status           TEXT NOT NULL DEFAULT 'running',   -- running | completed | failed
    data_snapshot    TEXT NOT NULL,                     -- JSON: row counts + content hash per source table
    data_hash        TEXT NOT NULL,
    rule_versions    TEXT NOT NULL,                     -- JSON: rule_id -> version
    engine_version   TEXT NOT NULL,
    label            TEXT,
    finding_count    INTEGER NOT NULL DEFAULT 0,
    skipped          TEXT,                              -- JSON list of analyses skipped and why
    error            TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_brand ON analysis_runs(brand_id, started_at);

CREATE TABLE IF NOT EXISTS findings (
    id               INTEGER PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    finding_key      TEXT NOT NULL,            -- stable across runs: rule_id:subject
    rule_id          TEXT NOT NULL,
    rule_version     TEXT NOT NULL,
    subject          TEXT NOT NULL,            -- period, SKU, category... the thing the rule is about
    title            TEXT NOT NULL,
    category         TEXT NOT NULL,
    severity         TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    status           TEXT NOT NULL DEFAULT 'detected' CHECK (status IN ('detected', 'needs_investigation', 'verified', 'dismissed')),
    classification   TEXT NOT NULL DEFAULT 'discrepancy',  -- discrepancy | suspected_risk | observation
    summary          TEXT NOT NULL,
    explanation      TEXT NOT NULL,
    method           TEXT NOT NULL,
    period_start     TEXT,
    period_end       TEXT,
    measured         TEXT NOT NULL,            -- JSON of measured values
    estimated_impact REAL,
    impact_basis     TEXT,
    confidence       TEXT NOT NULL,
    confidence_note  TEXT,
    next_action      TEXT,
    analyst_note     TEXT,
    UNIQUE (run_id, finding_key)
);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);

CREATE TABLE IF NOT EXISTS finding_evidence (
    id            INTEGER PRIMARY KEY,
    finding_id    INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    source_table  TEXT NOT NULL,
    source_id     INTEGER,
    source_ref    TEXT,
    description   TEXT NOT NULL,
    value         REAL,
    extra         TEXT                           -- JSON
);
CREATE INDEX IF NOT EXISTS idx_evidence_finding ON finding_evidence(finding_id);

CREATE TABLE IF NOT EXISTS diligence_questions (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    finding_id    INTEGER REFERENCES findings(id) ON DELETE CASCADE,
    question_key  TEXT NOT NULL,
    question      TEXT NOT NULL,
    rationale     TEXT NOT NULL,
    evidence_note TEXT,
    requested_items TEXT,
    priority      TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'answered', 'resolved')),
    answer_note   TEXT,
    UNIQUE (run_id, question_key)
);

CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    version      INTEGER NOT NULL,
    title        TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, version)
);
