from __future__ import annotations

import streamlit as st

from components.layout import header
from data import load_snapshot, metric_context, snapshot_options
from pages import dfc, drivers, executive, history, sku
from state.filters import render_filters, render_period
from styles.theme import apply_theme


st.set_page_config(page_title="STORM | Weekly Business Cockpit", page_icon="", layout="wide", initial_sidebar_state="collapsed")
apply_theme()
options = snapshot_options()
if not options:
    st.error("NO PRODUCTION DATA / DATA REQUIRED. Place approved local data in data/ and run the weekly production workflow.")
    st.stop()
labels = {item["snapshot_id"]: f"{item['week_key']} · {item['snapshot_date']} · R{item['revision']}" for item in options}
selected = st.selectbox("Selected Snapshot", list(labels), format_func=labels.get, label_visibility="collapsed")
data = load_snapshot(selected)
header(data["manifest"])
filters = render_filters(data["sku_metrics"])
period = render_period()
context = metric_context(data, filters, period)
pages = {"01 Executive": executive, "02 Drivers": drivers, "03 SKU": sku, "04 THD DFC": dfc, "05 History & Data": history}
selected_page = st.radio("Navigation", list(pages), horizontal=True, label_visibility="collapsed")
pages[selected_page].render(data, filters, context)
