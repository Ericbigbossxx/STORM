from __future__ import annotations

import streamlit as st

from charts.finance import gap_bar
def render(data: dict, filters: dict, context: dict) -> None:
    st.title("Performance Decomposition")
    st.caption("销售缺口的来源。主视图使用标准化 Attainment 与 Gap Contribution；金额 Gap 为辅助信息。")
    if context["availability"] != "AVAILABLE":
        st.info("YTD：当前没有可比的权威 Sales/BP Driver 抽取。")
        return
    channel_rows = context["channels"]
    if channel_rows.empty:
        st.info("当前权威 YTD 已提供 Overall Sales/BP；未提供可比 Channel Driver 粒度。")
        return
    if len(channel_rows) > 1:
        st.subheader("Channel Attainment / Gap Contribution")
        rows = channel_rows.copy()
        total_gap = rows["sales_gap"].sum()
        rows["gap_contribution"] = rows["sales_gap"] / total_gap if total_gap else None
        table = rows[["platform", "channel", "attainment", "gap_contribution", "sales_gap", "actual_cm"]].copy()
        table["attainment"] = table["attainment"].map(lambda value: "N/A" if value is None else f"{value:.1%}")
        table["gap_contribution"] = table["gap_contribution"].map(lambda value: "N/A" if value is None else f"{value:.1%}")
        table["actual_cm"] = table["actual_cm"].map(lambda value: "N/A" if value is None else f"{value:.1%}")
        st.dataframe(table, use_container_width=True, hide_index=True, column_config={"sales_gap": st.column_config.NumberColumn("Gap ($)", format="$%,.0f"), "attainment": "Attainment", "gap_contribution": "Gap Contribution", "actual_cm": "CM%"})
    drivers = context["drivers"]
    st.subheader("Brand / Power Source drilldown")
    st.plotly_chart(gap_bar(drivers, "platform,channel,brand,power_source"), use_container_width=True, config={"displayModeBar": False})
    columns = ["platform", "channel", "brand", "power_source", "actual_sales", "bp_sales", "sales_gap", "attainment", "gap_contribution"]
    table = drivers[columns].sort_values("sales_gap").copy()
    table["attainment"] = table["attainment"].map(lambda value: "N/A" if value is None else f"{value:.2%}")
    table["gap_contribution"] = table["gap_contribution"].map(lambda value: "N/A" if value is None else f"{value:.2%}")
    st.dataframe(table, use_container_width=True, hide_index=True, column_config={"actual_sales": st.column_config.NumberColumn("Actual", format="$%,.2f"), "bp_sales": st.column_config.NumberColumn("BP", format="$%,.2f"), "sales_gap": st.column_config.NumberColumn("Gap ($)", format="$%,.2f"), "attainment": "Attainment", "gap_contribution": "Gap Contribution"})
    st.caption("百分比以小数存储、界面按百分比显示（例如 2.7865 显示为 278.65%）。Driver 粒度没有 CM 分摊，故不展示 CM。")
