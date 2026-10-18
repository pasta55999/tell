"""Cached data access for the UI. Cache keys include the data hash so edits invalidate."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tell.analysis import metrics
from tell.analysis.context import AnalysisContext
from tell.analysis.rules.advertising import channel_table
from tell.analysis.rules.data_quality import coverage, score
from tell.analysis.rules.inventory import roll_forward
from tell.db import repository as repo
from tell.ui.state import conn


def data_hash(brand_id: int) -> str:
    _, h = repo.data_snapshot(conn(), brand_id)
    return h


@st.cache_data(show_spinner=False)
def financials(brand_id: int, _hash: str) -> pd.DataFrame:
    return metrics.monthly_financials(conn(), brand_id)


@st.cache_data(show_spinner=False)
def products(brand_id: int, _hash: str) -> pd.DataFrame:
    return metrics.product_table(conn(), brand_id)


@st.cache_data(show_spinner=False)
def product_monthly(brand_id: int, _hash: str) -> pd.DataFrame:
    return repo.product_monthly_sales(conn(), brand_id)


@st.cache_data(show_spinner=False)
def ad_spend(brand_id: int, _hash: str) -> pd.DataFrame:
    return repo.monthly_ad_spend(conn(), brand_id)


@st.cache_data(show_spinner=False)
def channels(brand_id: int, _hash: str) -> pd.DataFrame:
    return channel_table(repo.monthly_ad_spend(conn(), brand_id))


@st.cache_data(show_spinner=False)
def inventory_rollforward(brand_id: int, _hash: str) -> pd.DataFrame:
    return roll_forward(AnalysisContext(conn(), brand_id))


@st.cache_data(show_spinner=False)
def coverage_info(brand_id: int, _hash: str) -> tuple[dict, int, str]:
    cov = coverage(AnalysisContext(conn(), brand_id))
    s, label = score(cov)
    return cov, s, label


def findings(run_id: int | None) -> pd.DataFrame:
    return repo.findings_for_run(conn(), run_id) if run_id else pd.DataFrame()
