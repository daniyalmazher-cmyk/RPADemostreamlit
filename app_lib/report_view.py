"""Shared Streamlit renderer for a single classification report.

Both the Cloud Runs and Trigger pages display the same charts once they've
downloaded a report, so the rendering lives here.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import charts
from .parsing import DETECTION_KEYS, summarize


def render_summary_metrics(df: pd.DataFrame) -> None:
    s = summarize(df)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Files scanned", s["total_files"])
    c2.metric("Highly Confidential", s["highly_confidential"])
    c3.metric("Confidential", s["confidential"])
    c4.metric("Public", s["public"])
    c5.metric("Peak risk", s["peak_risk"])


def render_charts(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No files in this report.")
        return

    st.subheader("Classification mix")
    left, _ = st.columns([1, 1])
    with left:
        st.plotly_chart(charts.classification_donut(df), width="stretch")


def render_file_table(df: pd.DataFrame) -> None:
    if df.empty:
        return

    st.subheader("Files")
    classifications = [c for c in df["classification"].dropna().astype(str).unique()]
    file_types = sorted(df["file_type"].dropna().astype(str).unique().tolist())

    # Stable keys — do NOT use id(df). The DataFrame is rebuilt on every
    # script rerun (load_report() is not cached), so id(df) shifts each
    # rerun, Streamlit sees the widget as fresh, and the user's selection
    # is wiped on every interaction.
    filt_col1, filt_col2, filt_col3 = st.columns([2, 2, 3])
    with filt_col1:
        selected_classifications = st.multiselect(
            "Classification",
            options=classifications,
            default=classifications,
            key="dlp_filter_classification",
        )
    with filt_col2:
        selected_types = st.multiselect(
            "File type",
            options=file_types,
            default=file_types,
            key="dlp_filter_filetype",
        )
    with filt_col3:
        risk_min, risk_max = st.slider(
            "Risk score range",
            min_value=0,
            max_value=100,
            value=(0, 100),
            key="dlp_filter_risk",
        )

    filtered = df[
        df["classification"].astype(str).isin(selected_classifications)
        & df["file_type"].astype(str).isin(selected_types)
        & df["risk_score"].between(risk_min, risk_max)
    ]

    table_cols = [
        "file_name",
        "classification",
        "risk_score",
        "file_type",
        *[f"{k}_count" for k in DETECTION_KEYS if f"{k}_count" in df.columns],
        "salary_indicator",
        "file_path",
    ]
    table_cols = [c for c in table_cols if c in filtered.columns]
    st.dataframe(filtered[table_cols], width="stretch", hide_index=True)
    st.caption(f"Showing {len(filtered)} of {len(df)} files.")

    if not filtered.empty:
        st.subheader("Detection details")
        # Sort by risk so the most-flagged file is the default selection.
        sorted_filtered = filtered.sort_values("risk_score", ascending=False)
        options = sorted_filtered["file_name"].tolist()
        choice = st.selectbox("Pick a file", options=options, key="dlp_detail_file")
        if choice:
            row = filtered[filtered["file_name"] == choice].iloc[0]
            _render_detection_detail(row)


def _render_detection_detail(row: pd.Series) -> None:
    """Show only the detection types that actually have hits in this file.

    The previous 5-column layout always rendered every category, which
    meant Public files showed five "—" cells and looked broken. Now we
    skip empty categories and tell the user explicitly when there's nothing.
    """
    hits = []
    for key in DETECTION_KEYS:
        values = row.get(f"{key}_values", [])
        if not isinstance(values, list):
            values = []
        count = int(row.get(f"{key}_count", len(values)) or 0)
        if count > 0:
            hits.append((key, count, values))

    if not hits:
        st.info("No sensitive-data matches found in this file.")
        return

    for key, count, values in hits:
        label = key.replace("_", " ").upper()
        suffix = "match" if count == 1 else "matches"
        st.markdown(f"**{label}** — {count} {suffix}")
        for v in values[:25]:
            st.code(str(v), language=None)
        if len(values) > 25:
            st.caption(f"…and {len(values) - 25} more")


def render_full_report(df: pd.DataFrame) -> None:
    render_summary_metrics(df)
    st.divider()
    render_charts(df)
    st.divider()
    render_file_table(df)
