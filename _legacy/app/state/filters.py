from __future__ import annotations

import pandas as pd
import streamlit as st


FILTER_LABELS = {
    "platform": "Platform", "channel": "Channel", "brand": "Brand",
    "power_source": "Power Source", "sku": "SKU",
}


def render_period() -> str:
    return st.selectbox("Period", ["MTD", "YTD"], key="period_selector")


def render_filters(sku_metrics: pd.DataFrame) -> dict:
    values: dict[str, str] = {}
    candidates = sku_metrics
    columns = st.columns(5)
    for column, container in zip(FILTER_LABELS, columns):
        options = ["All"] + sorted(candidates[column].dropna().astype(str).unique().tolist())
        selected = container.selectbox(FILTER_LABELS[column], options, key=f"filter_{column}")
        values[column] = selected
        if selected != "All":
            candidates = candidates[candidates[column].astype(str) == selected]
    return values
