from __future__ import annotations

import os
import sqlite3

import pytest

from tell.analysis.engine import run_analysis
from tell.data.demo_generator import generate_demo
from tell.db.connection import open_db

# Guarantee no API keys are present during tests: the app must not need them.
for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TELL_LLM_ENDPOINT"):
    os.environ.pop(var, None)


@pytest.fixture(scope="session")
def demo_conn() -> sqlite3.Connection:
    conn = open_db(":memory:")
    generate_demo(conn)
    return conn


@pytest.fixture(scope="session")
def brand_id(demo_conn) -> int:
    return int(demo_conn.execute("SELECT id FROM brands WHERE is_demo = 1").fetchone()[0])


@pytest.fixture(scope="session")
def run_id(demo_conn, brand_id) -> int:
    return run_analysis(demo_conn, brand_id, label="test baseline")


@pytest.fixture()
def fresh_conn() -> sqlite3.Connection:
    """Empty database with schema only."""
    return open_db(":memory:")
