"""Financial story: where the numbers diverge (reconciliation), the financial picture
(sales, costs, margin, discounts, refunds), and the monthly ledger with drill-down."""

from __future__ import annotations

import streamlit as st

from tell.analysis import metrics
from tell.analysis.conventions import DEFINITIONS
from tell.analysis.rules.revenue import attribute_variance
from tell.db import repository as repo
from tell.reports.exports import df_to_csv
from tell.ui import charts, components as c, data, state, theme


def render() -> None:
    brand = state.brand()
    bid, cur = int(brand["id"]), brand["reporting_currency"]
    conn = state.conn()
    h = data.data_hash(bid)
    fin = data.financials(bid, h)
    c.page_header("Financial story", eyebrow=brand["name"])
    if fin.empty:
        c.empty_state("No records", "Import orders in the Data room to build the financial picture.")
        return
    t = metrics.period_totals(fin)
    rec = fin[fin["reported_revenue"].notna()]
    breaches = rec[rec["revenue_variance_pct"].abs() >= 2]
    h1, h2 = fin.head(len(fin) // 2), fin.tail(len(fin) // 2)
    gm = lambda d: (d["gross_sales"].sum() - d["cogs"].sum()) / d["gross_sales"].sum() * 100  # noqa: E731

    c.hero([("Gross sales", c.money(t["gross_sales"], cur), f"{t['orders_completed']:,} completed orders · GMS {c.money(t['gms'], cur)} less {c.money(t['discounts'], cur)} discounts"),
            ("Net sales", c.money(t["net_sales"], cur), f"after {c.money(t['refunds_posted'], cur)} refunds posted", theme.EMERALD),
            ("Gross margin", c.pct(t["gross_margin_pct"]), f"H2 vs H1 {gm(h2) - gm(h1):+.1f}pp", theme.AMBER if gm(h2) - gm(h1) <= -1 else theme.INK),
            ("Contribution proxy", c.money(t["contribution_proxy"], cur), "gross profit − advertising · not EBITDA")])

    view = st.segmented_control("View", ["Where the numbers diverge", "The financial picture", "Monthly ledger", "Definitions"], default="Where the numbers diverge", label_visibility="collapsed")

    # ------------------------------------------------------------ reconciliation
    if view == "Where the numbers diverge":
        if rec.empty:
            c.panel("No seller statements", "Import the seller's monthly management accounts to compare reported revenue with the figure the order and refund records support.", "tint")
            return
        reported, net, gross = float(rec["reported_revenue"].sum()), float(rec["net_sales"].sum()), float(rec["gross_sales"].sum())
        a, b = st.columns([3, 2], gap="large")
        with a:
            c.section("From the seller's headline to supported net sales", f"{len(rec)} reported months")
            st.plotly_chart(charts.annual_bridge(fin, cur, attribute_variance), width="stretch", config={"displayModeBar": False})
        with b:
            c.section("Three views of revenue")
            st.plotly_chart(charts.reconciliation_flow({"reported": reported, "gross": gross, "net": net}, cur), width="stretch", config={"displayModeBar": False})
            if breaches.empty:
                c.insight("Every reported month reconciles within the 2% tolerance.", "emerald")
            else:
                labels = [attribute_variance(r)[0] for _, r in breaches.iterrows()]
                common = max(set(l for l in labels if l), key=labels.count) if any(labels) else None
                c.insight(f"{len(breaches)} of {len(rec)} months breach tolerance ({', '.join(breaches['period'])}), {c.signed_money(float(breaches['revenue_variance'].sum()), cur)} combined."
                          + (f" Each gap matches {common.split(' (')[0]} — a definitional difference to confirm with the seller." if common else ""), "coral")
        c.section("Month by month", "Seller-reported against refund-adjusted net sales, and the variance against ±2%")
        a, b = st.columns([3, 2], gap="large")
        with a:
            st.plotly_chart(charts.reconciliation_bars(fin, cur), width="stretch", config={"displayModeBar": False})
        with b:
            st.plotly_chart(charts.variance_bars(fin, cur), width="stretch", config={"displayModeBar": False})

        c.section("Trace a month to its records", "Bridge for one month and the orders, refunds and cancellations behind it")
        default = list(rec["period"]).index(breaches["period"].iloc[0]) if not breaches.empty else len(rec) - 1
        sel, _ = st.columns([2, 5])
        with sel:
            period = st.selectbox("Month", list(rec["period"]), index=default, label_visibility="collapsed")
        row = rec[rec["period"] == period].iloc[0]
        label, residual = attribute_variance(row)
        x, y = st.columns([2, 3], gap="large")
        with x:
            c.ledger([("Seller-reported", c.money(row["reported_revenue"], cur), None), ("Order-ledger gross sales", c.money(row["gross_sales"], cur), f"{int(row['orders_completed'])} completed orders"),
                      ("Refunds posted", "− " + c.money(row["refunds_posted"], cur), f"{int(row['refunds_posted_count'])} refunds"), ("Supported net sales", c.money(row["net_sales"], cur), None),
                      ("Cancelled orders (memo)", c.money(row["cancelled_value"], cur), f"{int(row['orders_cancelled'])} orders")],
                     ("Variance", f"{c.signed_money(row['revenue_variance'], cur)} · {row['revenue_variance_pct']:+.1f}%"))
            st.write("")
            if abs(row["revenue_variance_pct"]) < 2:
                c.insight("Within the 2% tolerance; no finding raised for this month.", "emerald")
            elif label:
                c.insight(f"The variance is approximately {label} (residual {c.money(residual, cur)}).", "coral")
            else:
                c.insight("The variance does not match refunds, cancellations, shipping or discounts in any combination; it needs an explanation from the seller.", "coral")
        with y:
            st.plotly_chart(charts.waterfall(row, cur), width="stretch", config={"displayModeBar": False})
        t1, t2, t3 = st.tabs([f"Completed orders ({int(row['orders_completed'])})", f"Refunds posted ({int(row['refunds_posted_count'])})", f"Cancelled orders ({int(row['orders_cancelled'])})"])
        with t1:
            df = repo.orders_in_period(conn, bid, period, "completed")
            c.table(c.format_table(df.drop(columns=["id"]), money_cols=["gross_amount", "discount_amount", "shipping_amount", "net_amount"], cur=cur), height=320)
            st.download_button("Export orders (CSV)", df_to_csv(df), file_name=f"{brand['slug']}-orders-{period}.csv", mime="text/csv", key="dl_o")
        with t2:
            df = repo.refunds_in_period(conn, bid, period)
            c.table(c.format_table(df.drop(columns=["id"]), money_cols=["amount"], cur=cur), height=320)
            st.download_button("Export refunds (CSV)", df_to_csv(df), file_name=f"{brand['slug']}-refunds-{period}.csv", mime="text/csv", key="dl_r")
        with t3:
            df = repo.orders_in_period(conn, bid, period, "cancelled")
            c.table(c.format_table(df.drop(columns=["id"]), money_cols=["gross_amount", "discount_amount", "shipping_amount", "net_amount"], cur=cur), height=320)

    # ------------------------------------------------------------ the financial picture
    elif view == "The financial picture":
        c.section("Sales, cost of goods and the rates that move margin", f"{cur} · gross margin, discount rate and cohort refund rate on the lower panel")
        st.plotly_chart(charts.margin_story(fin, cur), width="stretch", config={"displayModeBar": False})
        a, b = st.columns([2, 3], gap="large")
        with a:
            st.markdown('<div class="tell-eyebrow muted">First half vs second half</div>', unsafe_allow_html=True)
            u1, u2 = h1["units"].sum(), h2["units"].sum()
            c.ledger([("Gross sales", f"{c.money(h1['gross_sales'].sum(), cur)} → {c.money(h2['gross_sales'].sum(), cur)}", f"{(h2['gross_sales'].sum() / h1['gross_sales'].sum() - 1) * 100:+.0f}%"),
                      ("Gross margin", f"{gm(h1):.1f}% → {gm(h2):.1f}%", f"{gm(h2) - gm(h1):+.1f}pp", gm(h2) - gm(h1) <= -1),
                      ("Avg unit cost", f"{cur} {h1['cogs'].sum() / u1:,.2f} → {cur} {h2['cogs'].sum() / u2:,.2f}", f"{(h2['cogs'].sum() / u2) / (h1['cogs'].sum() / u1) * 100 - 100:+.1f}%"),
                      ("Avg selling price", f"{cur} {h1['gross_sales'].sum() / u1:,.2f} → {cur} {h2['gross_sales'].sum() / u2:,.2f}", f"{(h2['gross_sales'].sum() / u2) / (h1['gross_sales'].sum() / u1) * 100 - 100:+.1f}%"),
                      ("Discount rate", f"{h1['discounts'].sum() / h1['gms'].sum() * 100:.1f}% → {h2['discounts'].sum() / h2['gms'].sum() * 100:.1f}%", None),
                      ("Ads % of gross sales", f"{h1['ad_spend'].sum() / h1['gross_sales'].sum() * 100:.1f}% → {h2['ad_spend'].sum() / h2['gross_sales'].sum() * 100:.1f}%", None)])
        with b:
            prod = data.products(bid, h)
            cats = metrics.category_table(prod)
            st.markdown('<div class="tell-eyebrow muted">Category margins</div>', unsafe_allow_html=True)
            c.table(c.format_table(cats[["category", "skus", "units", "gross_sales", "revenue_share_pct", "gross_margin_pct", "refunded_amount"]].rename(
                columns={"category": "Category", "skus": "SKUs", "units": "Units", "gross_sales": "Gross sales", "revenue_share_pct": "Share %", "gross_margin_pct": "GM %", "refunded_amount": "Refunded"}),
                money_cols=["Gross sales", "Refunded"], pct_cols=["Share %", "GM %"], int_cols=["SKUs", "Units"], cur=cur))
            pm = data.product_monthly(bid, h)
            by_cat = pm.groupby(["period", "category"], as_index=False)["gross_sales"].sum()
            st.plotly_chart(charts.stacked_months(by_cat, "period", "gross_sales", "category", cur), width="stretch", config={"displayModeBar": False})
        c.note("Contribution proxy = gross profit − advertising. Excludes fulfilment, payroll, payment fees, software and rent. It is not EBITDA.")

    # ------------------------------------------------------------ ledger
    elif view == "Monthly ledger":
        c.section("Monthly ledger", f"All figures in {cur} · derived from orders, refunds, order-line costs and ad records")
        cols = ["period", "orders_completed", "gms", "discounts", "gross_sales", "refunds_posted", "net_sales", "reported_revenue", "revenue_variance_pct", "cogs", "gross_profit", "gross_margin_pct", "ad_spend", "ad_pct_of_gross_sales", "contribution_proxy", "aov"]
        show = fin[cols].rename(columns={"period": "Month", "orders_completed": "Orders", "gms": "GMS", "discounts": "Discounts", "gross_sales": "Gross sales", "refunds_posted": "Refunds", "net_sales": "Net sales",
                                         "reported_revenue": "Seller-reported", "revenue_variance_pct": "Var %", "cogs": "COGS", "gross_profit": "Gross profit", "gross_margin_pct": "GM %", "ad_spend": "Ad spend",
                                         "ad_pct_of_gross_sales": "Ads % sales", "contribution_proxy": "Contribution proxy", "aov": "AOV"})
        show.insert(0, "", ["▲" if abs(v) >= 2 else "" for v in fin["revenue_variance_pct"].fillna(0)])
        c.table(c.format_table(show, money_cols=["GMS", "Discounts", "Gross sales", "Refunds", "Net sales", "Seller-reported", "COGS", "Gross profit", "Ad spend", "Contribution proxy", "AOV"],
                               pct_cols=["Var %", "GM %", "Ads % sales"], int_cols=["Orders"], cur=cur), height=480, column_config={"": st.column_config.TextColumn("", width="small", help="▲ month breaches the 2% reconciliation threshold")})
        st.download_button("Export ledger (CSV)", df_to_csv(fin[cols].round(2)), file_name=f"{brand['slug']}-monthly-ledger.csv", mime="text/csv")

    else:
        c.section("Definitions used throughout Tell")
        for k, v in DEFINITIONS.items():
            st.markdown(f"**{k}.** {v}")
