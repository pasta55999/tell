"""Core financial metric tables. Every rule and every UI page reads from these
functions so that the same conventions apply everywhere."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from tell.db import repository as repo


def monthly_financials(conn: sqlite3.Connection, brand_id: int) -> pd.DataFrame:
    """One row per month with GMS, discounts, gross sales, refunds (posted), net sales,
    COGS, gross profit, margin, ad spend, contribution proxy and seller-reported figures."""
    orders = repo.monthly_orders(conn, brand_id)
    if orders.empty:
        return pd.DataFrame()
    cogs = repo.monthly_units_and_cogs(conn, brand_id)
    refunds = repo.monthly_refunds_by_posting(conn, brand_id).rename(columns={"refunds": "refunds_posted", "refund_count": "refunds_posted_count"})
    refunds_cohort = repo.monthly_refunds_by_order_period(conn, brand_id).rename(columns={"refunds": "refunds_by_order_month", "refund_count": "refunds_by_order_month_count"})
    ads = repo.monthly_ad_spend(conn, brand_id)
    ads_total = ads.groupby("period", as_index=False).agg(ad_spend=("spend", "sum")) if not ads.empty else pd.DataFrame(columns=["period", "ad_spend"])
    statements = repo.seller_statements(conn, brand_id)

    df = orders.merge(cogs, on="period", how="left")
    df = df.merge(refunds, on="period", how="left").merge(refunds_cohort, on="period", how="left")
    df = df.merge(ads_total, on="period", how="left")
    if not statements.empty:
        df = df.merge(statements[["period", "reported_revenue", "reported_cogs", "reported_ad_spend", "reported_gross_profit"]], on="period", how="left")
    else:
        for c in ["reported_revenue", "reported_cogs", "reported_ad_spend", "reported_gross_profit"]:
            df[c] = np.nan
    for c in ["refunds_posted", "refunds_posted_count", "refunds_by_order_month", "refunds_by_order_month_count", "ad_spend", "cogs", "units", "units_without_cost"]:
        df[c] = df[c].fillna(0)

    df["net_sales"] = df["gross_sales"] - df["refunds_posted"]
    df["gross_profit"] = df["gross_sales"] - df["cogs"]
    df["gross_margin_pct"] = np.where(df["gross_sales"] > 0, df["gross_profit"] / df["gross_sales"] * 100, np.nan)
    df["discount_rate_pct"] = np.where(df["gms"] > 0, df["discounts"] / df["gms"] * 100, np.nan)
    df["refund_rate_pct"] = np.where(df["gross_sales"] > 0, df["refunds_by_order_month"] / df["gross_sales"] * 100, np.nan)
    df["ad_pct_of_gross_sales"] = np.where(df["gross_sales"] > 0, df["ad_spend"] / df["gross_sales"] * 100, np.nan)
    df["contribution_proxy"] = df["gross_profit"] - df["ad_spend"]
    df["aov"] = np.where(df["orders_completed"] > 0, df["gross_sales"] / df["orders_completed"], np.nan)
    df["revenue_variance"] = df["reported_revenue"] - df["net_sales"]
    df["revenue_variance_pct"] = np.where(df["net_sales"] > 0, df["revenue_variance"] / df["net_sales"] * 100, np.nan)
    df["ad_variance"] = df["reported_ad_spend"] - df["ad_spend"]
    df["ad_variance_pct"] = np.where(df["ad_spend"] > 0, df["ad_variance"] / df["ad_spend"] * 100, np.nan)
    df["cancelled_value"] = df["cancelled_value"].fillna(0)
    return df.sort_values("period").reset_index(drop=True)


def period_totals(fin: pd.DataFrame) -> dict:
    if fin.empty:
        return {}
    gross_sales = float(fin["gross_sales"].sum())
    net_sales = float(fin["net_sales"].sum())
    cogs = float(fin["cogs"].sum())
    ad = float(fin["ad_spend"].sum())
    gp = gross_sales - cogs
    return {
        "period_start": fin["period"].iloc[0],
        "period_end": fin["period"].iloc[-1],
        "months": int(len(fin)),
        "orders_completed": int(fin["orders_completed"].sum()),
        "orders_cancelled": int(fin["orders_cancelled"].sum()),
        "gms": float(fin["gms"].sum()),
        "discounts": float(fin["discounts"].sum()),
        "gross_sales": gross_sales,
        "refunds_posted": float(fin["refunds_posted"].sum()),
        "net_sales": net_sales,
        "cogs": cogs,
        "gross_profit": gp,
        "gross_margin_pct": gp / gross_sales * 100 if gross_sales else None,
        "ad_spend": ad,
        "ad_pct_of_gross_sales": ad / gross_sales * 100 if gross_sales else None,
        "contribution_proxy": gp - ad,
        "reported_revenue": float(fin["reported_revenue"].sum(skipna=True)) if fin["reported_revenue"].notna().any() else None,
        "revenue_variance": float(fin["revenue_variance"].sum(skipna=True)) if fin["revenue_variance"].notna().any() else None,
        "aov": gross_sales / int(fin["orders_completed"].sum()) if fin["orders_completed"].sum() else None,
    }


def product_table(conn: sqlite3.Connection, brand_id: int, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    sales = repo.product_sales(conn, brand_id, start, end)
    if sales.empty:
        return sales
    refunds = repo.product_refunds(conn, brand_id, start, end)
    df = sales.merge(refunds, on="product_id", how="left")
    for c in ["refunded_units", "refunded_amount", "refund_count"]:
        df[c] = df[c].fillna(0)
    total = df["gross_sales"].sum()
    df["revenue_share_pct"] = df["gross_sales"] / total * 100 if total else 0
    df["gross_profit"] = df["gross_sales"] - df["cogs"]
    df["gross_margin_pct"] = np.where(df["gross_sales"] > 0, df["gross_profit"] / df["gross_sales"] * 100, np.nan)
    df["return_rate_pct"] = np.where(df["units"] > 0, df["refunded_units"] / df["units"] * 100, np.nan)
    df["net_sales_after_refunds"] = df["gross_sales"] - df["refunded_amount"]
    return df.sort_values("gross_sales", ascending=False).reset_index(drop=True)


def category_table(products: pd.DataFrame) -> pd.DataFrame:
    if products.empty:
        return products
    cat = products.groupby("category", as_index=False).agg(
        gross_sales=("gross_sales", "sum"), cogs=("cogs", "sum"), units=("units", "sum"),
        refunded_amount=("refunded_amount", "sum"), skus=("sku", "count"))
    total = cat["gross_sales"].sum()
    cat["revenue_share_pct"] = cat["gross_sales"] / total * 100 if total else 0
    cat["gross_margin_pct"] = np.where(cat["gross_sales"] > 0, (cat["gross_sales"] - cat["cogs"]) / cat["gross_sales"] * 100, np.nan)
    return cat.sort_values("gross_sales", ascending=False).reset_index(drop=True)


def robust_z(series: pd.Series, value: float) -> float | None:
    """Robust z-score using median and MAD (scaled). Returns None if MAD is zero."""
    clean = series.dropna()
    if len(clean) < 3:
        return None
    med = float(clean.median())
    mad = float((clean - med).abs().median()) * 1.4826
    if mad == 0:
        return None
    return (value - med) / mad
