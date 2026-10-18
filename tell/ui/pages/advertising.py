from __future__ import annotations

import pandas as pd
import streamlit as st

from tell.ui import charts, components as c, data, state


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    h = data.data_hash(bid)
    ads = data.ad_spend(bid, h)
    fin = data.financials(bid, h)
    c.page_header("Advertising", "Spend by channel and month, intensity against sales, and ROAS only where the platform reports attributed revenue.", eyebrow=brand["name"])
    if ads.empty:
        c.empty_state("No advertising records", "Import monthly ad spend per channel in Settings.")
        return
    ch = data.channels(bid, h)
    total = float(ads["spend"].sum())
    with_attr = ch[ch["attribution_available"]]
    c.kpi_row([("Total spend", c.money(total, cur), f"{ads['period'].nunique()} months · {len(ch)} channels"),
               ("Spend as % of gross sales", c.pct(total / fin["gross_sales"].sum() * 100 if not fin.empty and fin["gross_sales"].sum() else None), None),
               ("Channels with ROAS", f"{len(with_attr)} of {len(ch)}", ", ".join(with_attr["channel"]) if not with_attr.empty else "none report attribution"),
               ("Reported vs recorded", c.pct(fin["ad_variance_pct"].abs().max(), signed=False) + " max variance" if not fin.empty and fin["ad_variance_pct"].notna().any() else "n/a", "largest monthly gap to seller statements")])
    st.write("")
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.markdown("<h3>Spend by channel</h3>", unsafe_allow_html=True)
        st.plotly_chart(charts.stacked_months(ads, "period", "spend", "channel", cur), width="stretch", config={"displayModeBar": False})
    with b:
        st.markdown("<h3>Ad intensity (% of gross sales)</h3>", unsafe_allow_html=True)
        st.plotly_chart(charts.line(fin, "period", "ad_pct_of_gross_sales", "Ads % of gross sales", "%", height=300), width="stretch", config={"displayModeBar": False})

    st.markdown("<h3>Channel summary</h3>", unsafe_allow_html=True)
    show = ch.copy()
    show["roas"] = show.apply(lambda r: f"{r['roas']:.2f}x" if pd.notna(r["roas"]) else "not available", axis=1)
    show["share"] = show["spend"] / total * 100
    show = show[["channel", "spend", "share", "impressions", "clicks", "attributed_revenue", "roas"]].rename(
        columns={"channel": "Channel", "spend": "Spend", "share": "Share %", "impressions": "Impressions", "clicks": "Clicks", "attributed_revenue": "Attributed revenue", "roas": "ROAS"})
    c.table(c.format_table(show, money_cols=["Spend", "Attributed revenue"], pct_cols=["Share %"], int_cols=["Impressions", "Clicks"], cur=cur))
    c.note("ROAS = platform-attributed revenue / spend. Tell does not infer attribution from aggregate sales, so no blended ROAS is shown.")

    if not fin.empty and fin["reported_ad_spend"].notna().any():
        st.markdown("<h3>Seller statements vs channel records</h3>", unsafe_allow_html=True)
        rec = fin[fin["reported_ad_spend"].notna()][["period", "reported_ad_spend", "ad_spend", "ad_variance", "ad_variance_pct"]].rename(
            columns={"period": "Month", "reported_ad_spend": "Reported", "ad_spend": "Recorded", "ad_variance": "Variance", "ad_variance_pct": "Var %"})
        c.table(c.format_table(rec, money_cols=["Reported", "Recorded", "Variance"], pct_cols=["Var %"], cur=cur), height=360)
