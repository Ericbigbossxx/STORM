from __future__ import annotations

import pandas as pd
import streamlit as st

from charts.finance import dfc_line
from components.layout import money


def render(data: dict, filters: dict, context: dict) -> None:
    st.title("THD DFC")
    st.caption("Sell-out 运营视图，独立于 THD DS sell-in，不是 CM 盈利视图。")
    if context["period"] == "YTD":
        st.info("YTD：冻结 DFC 数据仅覆盖 August MTD，未跨快照累加。")
        return
    daily = data["thd_dfc_daily"].copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily = daily[(daily["date"] >= "2026-08-01") & (daily["date"] <= data["manifest"]["dfc_cutoff"])]
    mtd = data["manifest"]["reconciliation"]
    total = float(daily["gmv"].sum())
    latest = float(daily.sort_values("date").iloc[-1]["gmv"]) if not daily.empty else 0.0
    best = float(daily["gmv"].max()) if not daily.empty else 0.0
    days = max(len(daily), 1)
    units = float(daily["units"].sum()) if "units" in daily else 0.0
    traffic = float(daily["traffic"].sum()) if "traffic" in daily and daily["traffic"].notna().any() else None
    cols = st.columns(6)
    cols[0].metric("MTD Sell-out GMV", money(total, compact=True))
    cols[1].metric("Units", f"{units:,.0f}")
    cols[2].metric("Average Daily GMV", money(total / days, compact=True))
    cols[3].metric("Latest Day", money(latest, compact=True))
    cols[4].metric("Best Day", money(best, compact=True))
    cols[5].metric("Traffic", "N/A" if traffic is None else f"{traffic:,.0f}")
    st.subheader("Daily Sell-out GMV")
    st.plotly_chart(dfc_line(daily), use_container_width=True, config={"displayModeBar": False})
    st.subheader("SKU Sell-out ranking")
    ranks = data["thd_dfc_sku"].sort_values("gmv", ascending=False)
    st.bar_chart(ranks.set_index("sku")["gmv"], color="#153A5B")
    ranks["inventory"] = "DATA GAP"
    st.dataframe(ranks[["sku", "gmv", "units", "traffic", "inventory"]], use_container_width=True, hide_index=True, column_config={"gmv": st.column_config.NumberColumn("Sell-out GMV", format="$%,.2f")})
    st.caption("当前 DFC 数据源未包含可验证库存字段。")
