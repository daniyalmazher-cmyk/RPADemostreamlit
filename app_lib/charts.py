"""Plotly chart builders used across pages.

Trimmed to a single chart — the classification donut — per stakeholder
preference. Histograms / bar charts / timelines lived here previously
and can be re-added if needed.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .parsing import CLASSIFICATION_ORDER

CLASSIFICATION_COLORS = {
    "Public": "#2ca02c",
    "Confidential": "#ff7f0e",
    "Highly Confidential": "#d62728",
}


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
