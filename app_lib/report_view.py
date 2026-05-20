"""Shared Streamlit renderer for a single classification report.

Both the Cloud Runs and Trigger pages display the same charts once they've
downloaded a report, so the rendering lives here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import charts
from .parsing import (
    DETECTION_KEYS,
    audit_events_to_df,
    summarize,
)


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

    filt_col1, filt_col2, filt_col3 = st.columns([2, 2, 3])
    with filt_col1:
        selected_classifications = st.multiselect(
            "Classification",
            options=classifications,
            default=classifications,
            key=f"filt_class_{id(df)}",
        )
    with filt_col2:
        selected_types = st.multiselect(
            "File type",
            options=file_types,
            default=file_types,
            key=f"filt_type_{id(df)}",
        )
    with filt_col3:
        risk_min, risk_max = st.slider(
            "Risk score range",
            min_value=0,
            max_value=100,
            value=(0, 100),
            key=f"filt_risk_{id(df)}",
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
        choice = st.selectbox("Pick a file", options=options, key=f"detail_{id(df)}")
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


def render_audit_timeline(audit: dict[str, Any] | None) -> None:
    if not audit:
        return
    st.subheader("Run timeline")
    meta_cols = st.columns(3)
    meta_cols[0].markdown(f"**Run ID**\n\n`{audit.get('run_id', '—')}`")
    meta_cols[1].markdown(f"**Started**\n\n{audit.get('started_at', '—')}")
    meta_cols[2].markdown(f"**Completed**\n\n{audit.get('completed_at', '—')}")

    events = audit_events_to_df(audit)
    if events.empty:
        st.caption("No events recorded.")
        return
    st.dataframe(events, width="stretch", hide_index=True)


def render_full_report(
    df: pd.DataFrame,
    audit: dict[str, Any] | None = None,
) -> None:
    render_summary_metrics(df)
    st.divider()
    render_charts(df)
    st.divider()
    render_file_table(df)
    if audit:
        st.divider()
        render_audit_timeline(audit)
