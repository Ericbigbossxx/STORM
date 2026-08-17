"""Deterministic, evidence-only weekly conclusions."""
from __future__ import annotations

from typing import Any


def conclusions(context: dict[str, Any]) -> list[dict[str, str]]:
    if context["availability"] != "AVAILABLE":
        return [{"type": "OVERALL", "text": "当前范围没有可比指标。"}]
    if context["channels"].empty:
        return [{"type": "OVERALL", "text": f"{context['period']} 已提供权威 Overall Sales/BP；当前源未提供可比 Channel 粒度。"}]
    channels = context["channels"].copy()
    total_gap = float(channels["sales_gap"].sum())
    risk = channels.sort_values("sales_gap").iloc[0]
    leader = channels.sort_values("attainment", ascending=False).iloc[0]
    cm_rows = channels.dropna(subset=["actual_cm"])
    weakest_cm = cm_rows.sort_values("actual_cm").iloc[0] if not cm_rows.empty else None
    share = risk["sales_gap"] / total_gap if total_gap else None
    result = [
        {"type": "OVERALL", "text": f"当前范围 Actual ${context['actual_sales']:,.0f}，Attainment {context['attainment']:.1%}，Gap ${context['sales_gap']:,.0f}。"},
        {"type": "MAIN RISK", "text": f"{risk['platform']} / {risk['channel']} 是最大 Sales Gap 来源，占总 Gap {share:.1%}，Attainment {risk['attainment']:.1%}。"},
        {"type": "DRIVER", "text": f"{leader['platform']} / {leader['channel']} 的 Attainment 最高，为 {leader['attainment']:.1%}。"},
    ]
    if weakest_cm is not None:
        result.append({"type": "PROFITABILITY", "text": f"{weakest_cm['platform']} / {weakest_cm['channel']} 的 Actual CM% 最低，为 {weakest_cm['actual_cm']:.1%}。"})
    wow = context.get("wow", {})
    if wow.get("availability") == "AVAILABLE":
        result.append({"type": "WATCH", "text": f"相对 {wow['previous_snapshot_id']}，Attainment 变化 {wow['attainment_delta_pp']:+.1f}pp，Gap 变化 ${wow['gap_delta']:,.0f}。"})
    return result
