"""UI smoke tests with Streamlit AppTest: every page renders without exceptions on a fresh database,
both before and after an analysis run, and the primary interactions work."""

from __future__ import annotations

import os

import pytest
from streamlit.testing.v1 import AppTest

PAGES = ["overview", "financials", "reconciliation", "products", "advertising", "inventory", "findings", "questions", "reports", "copilot", "settings"]


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("ui") / "tell-ui.db"
    os.environ["TELL_DB_PATH"] = str(path)
    yield path
    os.environ.pop("TELL_DB_PATH", None)


def _page(name: str) -> AppTest:
    src = f"from tell.ui import state, theme\nfrom tell.ui.pages import {name}\ntheme.inject_css()\nstate.ensure_state()\n{name}.render()\n"
    return AppTest.from_string(src, default_timeout=120)


def test_pages_render_on_fresh_database(db_path):
    for name in PAGES:
        at = _page(name).run()
        assert not at.exception, (name, [e.value for e in at.exception])


def test_first_launch_seeds_demo_and_initial_run(db_path):
    from tell.ui import state
    from tell.db import repository as repo
    conn = state.conn()
    brand = conn.execute("SELECT id FROM brands WHERE is_demo = 1").fetchone()[0]
    assert repo.latest_run(conn, brand) is not None
    assert repo.table_counts(conn, brand)["orders"] >= 1000


def test_settings_run_button_creates_new_run(db_path):
    from tell.ui import state
    from tell.db import repository as repo
    conn = state.conn()
    brand = conn.execute("SELECT id FROM brands WHERE is_demo = 1").fetchone()[0]
    before = len(repo.list_runs(conn, brand))
    at = _page("settings").run()
    btn = [b for b in at.button if b.label == "Run analysis now"]
    assert btn
    btn[0].click().run()
    assert not at.exception
    assert len(repo.list_runs(conn, brand)) == before + 1


def test_pages_render_after_run(db_path):
    for name in PAGES:
        at = _page(name).run()
        assert not at.exception, (name, [e.value for e in at.exception])


def test_findings_detail_and_status_update(db_path):
    at = _page("findings").run()
    assert at.radio and len(at.radio[0].options) >= 10
    at.radio[0].set_value(at.radio[0].options[1]).run()
    assert not at.exception
    sel = [s for s in at.selectbox if s.key and s.key.startswith("st_")]
    assert sel
    sel[0].set_value("needs_investigation").run()
    save = [b for b in at.button if b.label == "Save"]
    save[0].click().run()
    assert not at.exception


def test_copilot_answers_in_ui(db_path):
    at = _page("copilot").run()
    at.chat_input[0].set_value("Which findings should I investigate first?").run()
    assert not at.exception
    assert any("Ranked by severity" in t.value for t in at.text)


def test_main_app_entrypoint(db_path):
    from pathlib import Path
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "streamlit_app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
