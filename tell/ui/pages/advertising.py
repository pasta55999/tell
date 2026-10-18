from __future__ import annotations

import pandas as pd
import streamlit as st

from tell.ui import charts, components as c, data, state, theme


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    ads = data.ad_spend(bid, h)
    fin = data.financials(bid, h)
    c.page_header("Advertising", "Spend by channel and month, intensity against sales, and ROAS only where the platform reports attributed revenue.", eyebrow=brand["name"])
    if ads.empty:
        c.empty_state("No advertising records", "Import monthly ad spend per channel in Settings & imports.")
        return
    ch = data.channels(bid, h)
    total = float(ads["spend"].sum())
    with_attr = ch[ch["attribution_available"]]
    max_var = fin["ad_variance_pct"].abs().max() if not fin.empty and fin["ad_variance_pct"].notna().any() else None
    c.kpi_row([("Total spend", c.money(total, cur), c.delta_text(f"{ads['period'].nunique()} months · {len(ch)} channels", "neutral"), theme.COBALT),
               ("Spend as % of gross sales", c.pct(total / fin["gross_sales"].sum() * 100 if not fin.empty and fin["gross_sales"].sum() else None), c.delta_text("intensity, not attribution", "neutral"), theme.VIOLET),
               ("Channels with verified ROAS", f"{len(with_attr)} of {len(ch)}", c.delta_text(", ".join(with_attr["channel"]) if not with_attr.empty else "none report attribution", "neutral"), theme.EMERALD),
               ("Statement vs platform", c.pct(max_var) + " max gap" if max_var is not None else "n/a", c.delta_text("largest monthly variance to seller accounts", "risk" if (max_var or 0) >= 10 else "good"), theme.CORAL if (max_var or 0) >= 10 else theme.EMERALD)])
    a, b = st.columns([3, 2], gap="large")
    with a:
        c.section("Spend by channel", cur)
        st.plotly_chart(charts.stacked_months(ads, "period", "spend", "channel", cur), width="stretch", config={"displayModeBar": False})
    with b:
        c.section("Ad intensity", "% of gross sales")
        st.plotly_chart(charts.line(fin, "period", "ad_pct_of_gross_sales", "Ads % of gross sales", "%", height=300, baseline=float(fin["ad_pct_of_gross_sales"].median())), width="stretch", config={"displayModeBar": False})

    c.section("Channel summary", "ROAS = platform-attributed revenue / spend; shown only where every month reports attribution")
    show = ch.copy()
    show["roas"] = show.apply(lambda r: f"{r['roas']:.2f}x (platform-attributed)" if pd.notna(r["roas"]) else "not available — no attribution data", axis=1)
    show["share"] = show["spend"] / total * 100
    show = show[["channel", "spend", "share", "impressions", "clicks", "attributed_revenue", "roas"]].rename(
        columns={"channel": "Channel", "spend": "Spend", "share": "Share %", "impressions": "Impressions", "clicks": "Clicks", "attributed_revenue": "Attributed revenue", "roas": "ROAS"})
    c.table(c.format_table(show, money_cols=["Spend", "Attributed revenue"], pct_cols=["Share %"], int_cols=["Impressions", "Clicks"], cur=cur))
    c.insight("Tell does not infer attribution from aggregate sales, so no blended ROAS or causal uplift is shown. Channel ROAS where present is the platform's own attribution and is not independently verified.", "cobalt")

    if not fin.empty and fin["reported_ad_spend"].notna().any():
        c.section("Seller statements vs platform records", "▲ marks months where the gap is at least 10%")
        rec = fin[fin["reported_ad_spend"].notna()][["period", "reported_ad_spend", "ad_spend", "ad_variance", "ad_variance_pct"]].rename(
            columns={"period": "Month", "reported_ad_spend": "Reported", "ad_spend": "Recorded", "ad_variance": "Variance", "ad_variance_pct": "Var %"})
        rec.insert(0, "", ["▲" if abs(v) >= 10 else "" for v in rec["Var %"]])
        c.table(c.format_table(rec, money_cols=["Reported", "Recorded", "Variance"], pct_cols=["Var %"], cur=cur), height=360, column_config={"": st.column_config.TextColumn("", width="small")})
