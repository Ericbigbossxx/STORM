from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from data import snapshot_options


def render(data: dict, filters: dict, context: dict) -> None:
    st.title("Weekly Snapshot History")
    st.caption("每个 Snapshot 不可变；顶部选择会切换完整 Cockpit 数据集。")
    rows = []
    for item in snapshot_options():
        control = item.get("reconciliation", {})
        rows.append({"Week": item["week_key"], "Snapshot": item["snapshot_id"], "Revision": item["revision"], "Status": item["status"], "Actual": control.get("actual_sales"), "Attainment": control.get("attainment"), "Gap": control.get("sales_gap"), "CM%": None, "Sales Cutoff": item["sales_cutoff"], "DFC Cutoff": item["dfc_cutoff"]})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    trend = pd.DataFrame([row for row in rows if row["Status"] == "PUBLISHED"])
    if len(trend) >= 2:
        st.subheader("Attainment by Snapshot")
        st.plotly_chart(px.line(trend.sort_values(["Week", "Revision"]), x="Snapshot", y="Attainment", markers=True), use_container_width=True, config={"displayModeBar": False})
    st.subheader("Selected snapshot controls")
    reconciliation = data["manifest"]["reconciliation"]
    st.json({"snapshot_id": data["manifest"]["snapshot_id"], "engine_version": data["manifest"]["engine_version"], "reconciliation_status": reconciliation["status"], "sku_bp_control": reconciliation["sku_bp_control"]})
