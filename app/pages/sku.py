from __future__ import annotations

import streamlit as st

from charts.finance import sku_bar
def render(data: dict, filters: dict, context: dict) -> None:
    st.title("SKU")
    rows = context["sku_rows"]
    st.caption("固定 Top 8。正 Actual 且 BP=0 归为 Unplanned Sales，不属于超额完成。")
    if context["availability"] != "AVAILABLE":
        st.info("YTD：当前没有可比的权威 SKU Sales/BP 抽取。")
        return
    if rows.empty:
        st.info("当前权威 YTD 未提供可比 SKU 粒度；Overall 指标见 Executive。")
        return
    detractors = rows[rows["bp_sales"].notna() & (rows["sales_gap"] < 0)]
    overperformers = rows[rows["bp_sales"].notna() & (rows["bp_sales"] > 0) & (rows["actual_sales"] > rows["bp_sales"])]
    left, right = st.columns(2)
    with left:
        st.subheader("Top 8 Detractors")
        if detractors.empty:
            st.info("所选范围没有低于 BP 的 SKU。")
        else:
            st.plotly_chart(sku_bar(detractors, "Largest shortfalls"), use_container_width=True)
    with right:
        st.subheader("Top 8 Overperformers")
        if overperformers.empty:
            st.info("No planned SKU outperformed BP in this selected scope.")
        else:
            st.plotly_chart(sku_bar(overperformers, "Above plan", positive=True), use_container_width=True)
    unplanned = rows[rows["bp_sales"].fillna(0).eq(0) & rows["actual_sales"].gt(0)]
    if not unplanned.empty:
        st.warning(f"{len(unplanned)} 个 SKU 标记为 Unplanned Sales（BP 为零）。")
    if st.button("View All SKU"):
        st.session_state["show_all_sku"] = True
    if st.session_state.get("show_all_sku"):
        fields = ["sku", "platform", "channel", "brand", "power_source", "actual_sales", "bp_sales", "sales_gap", "attainment"]
        table = rows[fields].sort_values("sales_gap").copy()
        table["attainment"] = table["attainment"].map(lambda value: "N/A" if value is None else f"{value:.2%}")
        st.dataframe(table, use_container_width=True, hide_index=True, column_config={"actual_sales": st.column_config.NumberColumn("Actual", format="$%,.2f"), "bp_sales": st.column_config.NumberColumn("BP", format="$%,.2f"), "sales_gap": st.column_config.NumberColumn("Gap", format="$%,.2f"), "attainment": "Attainment"})
