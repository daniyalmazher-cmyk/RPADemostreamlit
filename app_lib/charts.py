"""Plotly chart builders used across pages."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .parsing import CLASSIFICATION_ORDER, DETECTION_KEYS

CLASSIFICATION_COLORS = {
    "Public": "#2ca02c",
    "Confidential": "#ff7f0e",
    "Highly Confidential": "#d62728",
}


def risk_histogram(df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        df,
        x="risk_score",
        nbins=20,
        color="classification",
        category_orders={"classification": CLASSIFICATION_ORDER},
        color_discrete_map=CLASSIFICATION_COLORS,
    )
    fig.update_layout(
        xaxis_title="Risk score",
        yaxis_title="Files",
        bargap=0.05,
        legend_title_text="Classification",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


def classification_donut(df: pd.DataFrame) -> go.Figure:
    counts = (
        df["classification"].astype(str).value_counts().reindex(CLASSIFICATION_ORDER, fill_value=0)
    )
    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts.index.tolist(),
                values=counts.values.tolist(),
                hole=0.55,
                marker=dict(colors=[CLASSIFICATION_COLORS[c] for c in counts.index]),
                sort=False,
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=True,
    )
    return fig


def detection_totals_bar(df: pd.DataFrame) -> go.Figure:
    counts = {
        key: int(df[f"{key}_count"].sum()) if f"{key}_count" in df.columns else 0
        for key in DETECTION_KEYS
    }
    labels = [k.replace("_", " ").upper() for k in counts]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=list(counts.values()),
                marker_color="#1f77b4",
                text=list(counts.values()),
                textposition="auto",
            )
        ]
    )
    fig.update_layout(
        xaxis_title="Detection type",
        yaxis_title="Matches across all files",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


def file_type_breakdown(df: pd.DataFrame) -> go.Figure:
    g = (
        df.groupby(["file_type", "classification"], observed=True)
        .size()
        .reset_index(name="count")
    )
    fig = px.bar(
        g,
        x="file_type",
        y="count",
        color="classification",
        category_orders={"classification": CLASSIFICATION_ORDER},
        color_discrete_map=CLASSIFICATION_COLORS,
        barmode="stack",
    )
    fig.update_layout(
        xaxis_title="File type",
        yaxis_title="Files",
        legend_title_text="Classification",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


def audit_timeline(events: pd.DataFrame) -> go.Figure:
    if events.empty:
        return go.Figure()
    df = events.copy()
    df["y"] = df["event"].astype(str)
    fig = px.scatter(
        df,
        x="timestamp",
        y="y",
        color="event",
        hover_data=["payload"] if "payload" in df.columns else None,
    )
    fig.update_traces(marker=dict(size=11, line=dict(width=1, color="white")))
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="",
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig
