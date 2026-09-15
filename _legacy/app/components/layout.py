from __future__ import annotations

import streamlit as st


def money(value: float | None, compact: bool = False) -> str:
    if value is None:
        return "N/A"
    if compact:
        magnitude = abs(value)
        if magnitude >= 1_000_000: return f"${value / 1_000_000:.2f}M"
        if magnitude >= 1_000: return f"${value / 1_000:.1f}K"
    return f"${value:,.2f}"


def percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def header(manifest: dict) -> None:
    st.markdown(f'''<div class="storm-header"><div class="storm-wordmark">STORM</div><div class="storm-meta">Selected Snapshot: <b>{manifest["snapshot_id"]}</b><br>Sales Through {manifest["sales_cutoff"]} · DFC Through {manifest["dfc_cutoff"]} · CM {manifest["cm_period"]}</div></div>''', unsafe_allow_html=True)


def kpis(metrics: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Actual Sales", money(metrics["actual_sales"], compact=True))
    cols[1].metric("BP Sales", money(metrics["bp_sales"], compact=True))
    cols[2].metric("Attainment", percent(metrics["attainment"]))
    cols[3].metric("Gap", money(metrics["sales_gap"], compact=True))


def business_block(title: str, metrics: list[tuple[str, str]], note: str = "") -> None:
    values = "".join(f'<div class="metric-pair"><span>{label}</span><strong>{value}</strong></div>' for label, value in metrics)
    st.markdown(f'<section class="business-block"><div class="block-title">{title}</div><div class="metric-pairs">{values}</div><div class="block-note">{note}</div></section>', unsafe_allow_html=True)


def channel_matrix(rows) -> None:
    st.markdown('<div class="matrix-head"><span>Channel</span><span>Actual</span><span>Attainment</span><span>Gap</span><span>CM%</span></div>', unsafe_allow_html=True)
    for row in rows.sort_values("sales_gap").to_dict("records"):
        attainment = percent(row.get("attainment"))
        width = min(max((row.get("attainment") or 0) * 100, 0), 100)
        st.markdown(f'<div class="matrix-row"><b>{row["platform"]} / {row["channel"]}</b><span>{money(row.get("actual_sales"), True)}</span><span><i class="micro"><em style="width:{width:.1f}%"></em></i>{attainment}</span><span>{money(row.get("sales_gap"), True)}</span><span>{percent(row.get("actual_cm"))}</span></div>', unsafe_allow_html=True)


def finding(item: dict) -> None:
    css = {"MAIN RISK": "finding-risk", "WATCH": "finding-watch", "STRENGTH": "finding-strength"}.get(item["type"], "")
    st.markdown(f'<div class="finding {css}"><div class="finding-label">{item["type"]}</div><div class="finding-text">{item["text"]}</div></div>', unsafe_allow_html=True)
