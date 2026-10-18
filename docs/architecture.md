# Architecture

```
streamlit_app.py            entry point: navigation, sidebar (brand + run selector)
tell/
  config.py                 paths, limits (env overrides optional)
  db/
    schema.sql              SQLite DDL (idempotent)
    connection.py           connect / init_db / transaction()
    repository.py           parameterised read queries -> DataFrames
  data/demo_generator.py    deterministic synthetic business + planted scenarios
  ingest/csv_import.py      parse -> detect mapping -> validate -> transactional import
  analysis/
    conventions.py          definitions, thresholds, rule registry + versions
    metrics.py              monthly financials, product/category tables, robust z
    context.py              lazily computed shared inputs for rules
    models.py               Finding / Evidence / Question (pydantic)
    rules/*.py              one module per analysis area; each exports run(ctx) -> ModuleResult
    engine.py               run_analysis (persist run, findings, evidence, questions), status updates with history, compare_runs
    questions.py            consolidated cross-finding seller questions
    brief.py                investment intelligence brief assembled from stored findings (templated, evidence-linked)
  copilot/
    copilot.py              intent patterns -> handler functions -> templated Answer
    adapters.py             optional LLM adapter protocol + NullAdapter (default)
  reports/
    builder.py              structured report dict from a stored run; versioned save
    exports.py              JSON / CSV (formula-safe) / PDF (ReportLab)
  ui/
    theme.py                design tokens + global CSS (navy sidebar, cobalt/violet/emerald/coral semantics)
    components.py           KPI modules, pills, rows, insights, stat strips, tables
    charts.py               Plotly builders (reconciliation flow, variance, waterfall, roll-forward...)
    data.py, state.py       cached reads keyed by data hash; session state
    pages/                  deals, overview (command centre), financial_story, operations, findings, questions, reports, copilot, data_room
evaluation/run_eval.py      precision / recall / F1 vs ground truth; writes EVALUATION.md
tests/                      pytest suite (unit, integration, UI smoke via AppTest)
data/demo/ground_truth.json labelled planted scenarios (never read by the app)
```

## Data flow

1. **Ingest** - demo generator or CSV import writes raw source tables (`orders`, `order_items`,
   `refunds`, `refund_items`, `ad_spend`, `inventory_snapshots`, `supplier_receipts`,
   `seller_statements`, `products`). Each row references its `import_files` record.
2. **Metrics** - `metrics.monthly_financials` and `product_table` compute every figure used by
   the UI, the rules and the copilot, so the same conventions apply everywhere.
3. **Rules** - each module reads the shared `AnalysisContext` and returns typed `Finding`s with
   evidence (table + record id/ref + value) and seller questions.
4. **Engine** - `run_analysis` snapshots the data (counts + hash), records rule versions, and
   persists findings, evidence and questions in a single transaction.
5. **Consumption** - UI pages, the rule-based copilot and the report builder read the stored run;
   analysts update statuses, which are stored on the finding / question rows.

## Database schema (summary)

| Table | Purpose | Key constraints |
|---|---|---|
| workspaces, brands | Tenancy and brand profile (currency, fiscal year, demo flag) | `brands.slug` unique |
| import_files | Provenance of every import (dataset, filename, sha256, counts, mapping) | unique (brand, dataset, sha256) |
| products | SKU master with list price and standard cost | unique (brand, sku) |
| orders, order_items | Orders (gross/discount/shipping/net) and lines (qty, price, cost at sale) | unique (brand, order_ref); FK product |
| refunds, refund_items | Refund header (posting date) and refunded lines (restocked flag) | unique (brand, refund_ref); FK order |
| ad_spend | Monthly spend per channel; attributed revenue nullable | unique (brand, period, channel) |
| inventory_snapshots | Month-end counts per SKU and source | unique (brand, product, date, source) |
| supplier_receipts | Goods received with invoiced unit cost | unique (brand, receipt_ref) |
| seller_statements | Seller-reported monthly P&L | unique (brand, period) |
| analysis_runs | Run metadata: data snapshot/hash, rule versions, status, skipped | |
| findings | One row per finding per run; `finding_key` stable across runs | unique (run, finding_key); severity/status CHECKs |
| finding_evidence | Source rows backing a finding | FK finding (cascade) |
| diligence_questions | Per-finding and consolidated questions with status | unique (run, question_key) |
| finding_events, question_events | Review history: status changes and notes with timestamps | FK finding / question (cascade) |
| reports | Versioned report JSON per run | unique (run, version) |

Foreign keys are enforced (`PRAGMA foreign_keys = ON`); deleting a brand cascades through all
dependent tables, which is how the demo reset works. Indexes cover the brand/date lookups used
by the monthly aggregations.

## Security notes

- Every query is parameterised; table names in the few dynamic queries come from fixed allow-lists.
- Uploads are size-limited, must be `.csv`, are decoded and sniffed before parsing, and are
  validated row-by-row; nothing is written until the analyst confirms.
- CSV exports neutralise formula-leading cells (`=`, `+`, `-`, `@`, tab, CR).
- No secrets are required or read. `.env.example` lists the two optional settings.
