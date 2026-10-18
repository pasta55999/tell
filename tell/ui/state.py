"""Session-scoped application state: DB connection, active brand and run."""

from __future__ import annotations

import sqlite3

import streamlit as st

from tell import config
from tell.data.demo_generator import generate_demo
from tell.db import repository as repo
from tell.db.connection import open_db


@st.cache_resource(show_spinner=False)
def _connection(path: str) -> sqlite3.Connection:
    conn = open_db(path)
    brand_id = generate_demo(conn)      # idempotent: only seeds if the demo brand is absent
    if repo.latest_run(conn, brand_id) is None:
        from tell.analysis.engine import run_analysis

        run_analysis(conn, brand_id, label="initial demo analysis")   # first launch only; later runs are explicit
    return conn


def conn() -> sqlite3.Connection:
    return _connection(str(config.db_path()))


def ensure_state() -> None:
    c = conn()
    brands = repo.list_brands(c)
    if "brand_id" not in st.session_state or st.session_state.brand_id not in {b["id"] for b in brands}:
        st.session_state.brand_id = brands[0]["id"] if brands else None
    if "run_id" not in st.session_state:
        st.session_state.run_id = None
    if st.session_state.brand_id is not None:
        runs = repo.list_runs(c, st.session_state.brand_id)
        completed = [r["id"] for r in runs if r["status"] == "completed"]
        if st.session_state.run_id not in completed:
            st.session_state.run_id = completed[0] if completed else None


def brand() -> sqlite3.Row | None:
    return repo.get_brand(conn(), st.session_state.brand_id) if st.session_state.get("brand_id") else None


def run() -> sqlite3.Row | None:
    return repo.get_run(conn(), st.session_state.run_id) if st.session_state.get("run_id") else None


def currency() -> str:
    b = brand()
    return b["reporting_currency"] if b else config.DEFAULT_CURRENCY


def invalidate() -> None:
    """Clear cached dataframes after data changes."""
    st.cache_data.clear()
