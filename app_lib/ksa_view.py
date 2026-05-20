"""Streamlit renderer for the second bot's queue report.

Arabic name values are wrapped in `direction:rtl; unicode-bidi:embed;` so
browsers apply contextual joining (otherwise Arabic renders as
disconnected glyphs).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from .ksa_data import STATUS_ORDER

STATUS_COLORS = {
    "auto_approve": "#16a34a",
    "needs_review": "#d97706",
    "auto_reject": "#dc2626",
}

STATUS_LABELS = {
    "auto_approve": "Auto-approve",
    "needs_review": "Needs review",
    "auto_reject": "Auto-reject",
}


def render_arabic(text: str | None) -> str:
    if not text:
        return "<span style='color:#9ca3af'>—</span>"
    safe = _escape(text)
    return (
        "<span style='direction:rtl; unicode-bidi:embed; "
        "font-family:\"Noto Naskh Arabic\",\"Amiri\",serif; font-size:1.05rem;'>"
        f"{safe}</span>"
    )


def status_badge(status: str | None) -> str:
    key = str(status) if status else ""
    color = STATUS_COLORS.get(key, "#6b7280")
    label = STATUS_LABELS.get(key, key or "—")
    return (
        f"<span style='background:{color}; color:#fff; padding:2px 10px; "
        "border-radius:999px; font-size:0.85rem; font-weight:600; "
        f"display:inline-block;'>{label}</span>"
    )


def _escape(text: Any) -> str:
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_queue(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No applications found in this run yet. Run the bot to produce a report.")
        return

    counts = {s: int((df["status"].astype(str) == s).sum()) for s in STATUS_ORDER}
    total = int(len(df))

    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Total", total)
    for col, key in zip((c1, c2, c3), STATUS_ORDER):
        col.markdown(
            f"<div style='font-size:0.85rem; color:#6b7280;'>{STATUS_LABELS[key]}</div>"
            f"<div style='font-size:1.8rem; font-weight:700; color:{STATUS_COLORS[key]};'>"
            f"{counts[key]}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("")
    present_statuses = [s for s in STATUS_ORDER if counts.get(s, 0) > 0]
    selected = st.multiselect(
        "Status",
        options=STATUS_ORDER,
        default=present_statuses or STATUS_ORDER,
        format_func=lambda s: STATUS_LABELS.get(s, s),
        key="ksa_queue_status_filter",
    )

    filtered = df[df["status"].astype(str).isin(selected)].copy()
    if filtered.empty:
        st.caption("No applications match the selected status filter.")
        return

    st.markdown(_queue_table_html(filtered), unsafe_allow_html=True)
    st.caption(f"Showing {len(filtered)} of {len(df)} applications.")


def _queue_table_html(df: pd.DataFrame) -> str:
    headers = [
        "App", "Processed", "Source", "ID number",
        "Name (EN)", "Name (AR)", "Status", "Failed rules",
    ]
    rows_html = []
    for _, row in df.iterrows():
        app_id = str(row.get("app_id", ""))
        short = app_id[:8] if app_id else "—"
        cells = [
            f"<code>{_escape(short)}</code>",
            _escape(row.get("processed_at", "")),
            _escape(row.get("source_email", "")),
            _escape(row.get("id_number", "")),
            _escape(row.get("name_en", "")),
            render_arabic(row.get("name_ar", "")),
            status_badge(str(row.get("status", ""))),
            _escape(row.get("failed_rules", "")) or "<span style='color:#9ca3af'>—</span>",
        ]
        rows_html.append(
            "<tr>" + "".join(
                f"<td style='padding:6px 10px; border-bottom:1px solid #e5e7eb; vertical-align:top;'>{c}</td>"
                for c in cells
            ) + "</tr>"
        )
    head = "".join(
        f"<th style='text-align:left; padding:8px 10px; border-bottom:2px solid #d1d5db; "
        f"font-size:0.85rem; color:#374151;'>{h}</th>" for h in headers
    )
    return (
        "<table style='width:100%; border-collapse:collapse; font-size:0.9rem;'>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
    )
