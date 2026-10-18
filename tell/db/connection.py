"""SQLite connection management and schema initialisation."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from tell import config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 3   # v3: finding_events / question_events tables (created by schema.sql, no ALTER needed)

# Additive migrations for databases created by earlier versions: (version, table, column, ddl)
MIGRATIONS = [(2, "brands", "location", "ALTER TABLE brands ADD COLUMN location TEXT")]


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled and row access by name."""
    target = Path(path) if path else config.db_path()
    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit mode: single statements commit immediately; multi-statement
    # writes use the explicit `transaction()` context manager below.
    conn = sqlite3.connect(str(target), check_same_thread=False, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(target) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if missing and record the schema version. Safe to call repeatedly."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for version, table, column, ddl in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(ddl)
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,))
    conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))


def open_db(path: Path | str | None = None) -> sqlite3.Connection:
    conn = connect(path)
    init_db(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction; rolls back on any exception."""
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
