from __future__ import annotations

import streamlit as st

from analysis import conclusions
from components.layout import business_block, channel_matrix, money, percent


def render(data: dict, filters: dict, context: dict) -> None:
    st.title("Executive")
    st.caption("所选范围的业务健康度；Sales 由冻结引擎汇总，CM 仅显示权威工作簿支持的粒度。")
    if context["availability"] != "AVAILABLE":
        st.warning("YTD 当前没有完整可比的权威 Sales/BP 抽取；未跨快照累加。")
        return
    left, right = st.columns(2)
    with left:
        business_block("SALES PERFORMANCE", [("Actual", money(context["actual_sales"], True)), ("BP", money(context["bp_sales"], True)), ("Gap", money(context["sales_gap"], True)), ("Attainment", percent(context["attainment"]))], f"WoW {context.get('wow', {}).get('attainment_delta_pp', 0):+.1f}pp" if context.get("wow", {}).get("availability") == "AVAILABLE" else "WoW N/A")
    with right:
        business_block("PROFITABILITY", [("Actual CM", percent(context["actual_cm"])), ("BP CM", percent(context["bp_cm"])), ("CM Gap", percent(context["cm_gap"])), ("CM Status", "AVAILABLE" if context["actual_cm"] is not None else "N/A")], "CM 仅按权威来源可支持粒度展示")
    if context["channels"].empty:
        st.info("当前权威 YTD 数据仅支持 Overall Sales/BP；未显示不可比的 Channel Matrix。")
    else:
        st.subheader("Channel Matrix")
        channel_matrix(context["channels"])
    st.subheader("本周经营结论")
    scope = " / ".join(v for v in filters.values() if v and v != "All") or "Overall"
    st.caption(f"范围：{scope}。结论仅引用当前 Snapshot 已存在的指标。")
    for item in conclusions(context):
        st.markdown(f'<div class="conclusion"><b>{item["type"]}</b><span>{item["text"]}</span></div>', unsafe_allow_html=True)
