"""Shared, lazily computed inputs for analysis modules."""

from __future__ import annotations

import sqlite3
from functools import cached_property

import pandas as pd

from tell.analysis import metrics
from tell.db import repository as repo


class AnalysisContext:
    def __init__(self, conn: sqlite3.Connection, brand_id: int):
        self.conn = conn
        self.brand_id = brand_id
        brand = repo.get_brand(conn, brand_id)
        self.currency = brand["reporting_currency"] if brand else "AED"
        self.brand_name = brand["name"] if brand else "Brand"

    @cached_property
    def fin(self) -> pd.DataFrame:
        return metrics.monthly_financials(self.conn, self.brand_id)

    @cached_property
    def products(self) -> pd.DataFrame:
        return metrics.product_table(self.conn, self.brand_id)

    @cached_property
    def categories(self) -> pd.DataFrame:
        return metrics.category_table(self.products)

    @cached_property
    def refund_lags(self) -> pd.DataFrame:
        return repo.refund_lags(self.conn, self.brand_id)

    @cached_property
    def ad_spend(self) -> pd.DataFrame:
        return repo.monthly_ad_spend(self.conn, self.brand_id)

    @cached_property
    def statements(self) -> pd.DataFrame:
        return repo.seller_statements(self.conn, self.brand_id)

    @cached_property
    def inventory(self) -> pd.DataFrame:
        return repo.inventory_snapshots(self.conn, self.brand_id)

    @cached_property
    def receipts(self) -> pd.DataFrame:
        return repo.supplier_receipts(self.conn, self.brand_id)

    @cached_property
    def product_monthly(self) -> pd.DataFrame:
        return repo.product_monthly_sales(self.conn, self.brand_id)

    @property
    def period_start(self) -> str | None:
        return None if self.fin.empty else str(self.fin["period"].iloc[0])

    @property
    def period_end(self) -> str | None:
        return None if self.fin.empty else str(self.fin["period"].iloc[-1])

    def money(self, value: float | None) -> str:
        if value is None or pd.isna(value):
            return "n/a"
        return f"{self.currency} {value:,.0f}"
