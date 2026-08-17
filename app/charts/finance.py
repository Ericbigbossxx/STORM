from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


NAVY, RED, GREEN, LINE = "#153A5B", "#B42318", "#027A48", "#DFE3E8"


def base_layout(figure: go.Figure, height: int = 340) -> go.Figure:
    figure.update_layout(height=height, margin=dict(l=8, r=8, t=25, b=8), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", font_color="#17202a", showlegend=False)
    figure.update_xaxes(showgrid=True, gridcolor=LINE, zerolinecolor="#98A2B3")
    figure.update_yaxes(showgrid=False)
    return figure


def gap_bar(frame: pd.DataFrame, label: str) -> go.Figure:
    plotted = frame.sort_values("sales_gap").copy()
    plotted["label"] = plotted.apply(lambda row: " / ".join(str(row[key]) for key in label.split(",")), axis=1)
    figure = px.bar(plotted, x="sales_gap", y="label", orientation="h", color_discrete_sequence=[RED])
    figure.update_traces(hovertemplate="%{y}<br>Gap: $%{x:,.0f}<extra></extra>")
    return base_layout(figure)


def sku_bar(frame: pd.DataFrame, title: str, positive: bool = False) -> go.Figure:
    plotted = frame.sort_values("sales_gap", ascending=not positive).head(8).copy()
    plotted["label"] = plotted["platform"] + " / " + plotted["channel"] + " | " + plotted["sku"]
    figure = px.bar(plotted.sort_values("sales_gap"), x="sales_gap", y="label", orientation="h", color_discrete_sequence=[GREEN if positive else RED])
    figure.update_layout(title=title)
    return base_layout(figure)


def dfc_line(frame: pd.DataFrame) -> go.Figure:
    figure = px.line(frame, x="date", y="gmv", markers=True, color_discrete_sequence=[NAVY])
    figure.update_traces(hovertemplate="%{x}<br>GMV: $%{y:,.2f}<extra></extra>")
    return base_layout(figure)
