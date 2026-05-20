"""Streamlit renderer for the onboarding bot's queue report.

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
    # `white-space:nowrap` is what stops the pill turning into a tall oval
    # when the column is narrow — without it the label wraps and the
    # 999px border-radius bulges each line into an egg shape.
    return (
        f"<span style='background:{color}; color:#fff; padding:4px 12px; "
        "border-radius:999px; font-size:0.8rem; font-weight:600; "
        "display:inline-block; white-space:nowrap;'>"
        f"{label}</span>"
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
    _render_queue_rows(df)
    st.caption(f"{len(df)} applications.")


# Column widths shared by the header and every row so they stay aligned.
# Order: Processed, Source, ID number, Name (EN), Name (AR), Status,
# Failed rules, Send Email button, Add to CRM button.
_QUEUE_COL_WIDTHS = [1.4, 1.5, 1.1, 1.3, 1.3, 1.0, 1.2, 1.1, 1.1]
_QUEUE_HEADERS = [
    "Processed", "Source", "ID number",
    "Name (EN)", "Name (AR)", "Status", "Failed rules",
    "", "",
]


def _render_queue_rows(df: pd.DataFrame) -> None:
    # Header row
    header_cols = st.columns(_QUEUE_COL_WIDTHS)
    for col, label in zip(header_cols, _QUEUE_HEADERS):
        col.markdown(
            f"<div style='font-size:0.8rem; font-weight:600; color:#374151; "
            f"padding-bottom:6px; border-bottom:2px solid #d1d5db;'>{label}&nbsp;</div>",
            unsafe_allow_html=True,
        )

    # Data rows
    for i, (_, row) in enumerate(df.iterrows()):
        _render_queue_row(i, row)


def _render_queue_row(i: int, row: pd.Series) -> None:
    cols = st.columns(_QUEUE_COL_WIDTHS)

    cell_style = (
        "padding:8px 4px; border-bottom:1px solid #e5e7eb; "
        "font-size:0.85rem; line-height:1.3;"
    )

    def cell(text_html: str) -> str:
        return f"<div style='{cell_style}'>{text_html}</div>"

    failed = str(row.get("failed_rules", "") or "")
    failed_html = _escape(failed) if failed else "<span style='color:#9ca3af'>—</span>"

    cols[0].markdown(cell(_escape(row.get("processed_at", ""))), unsafe_allow_html=True)
    cols[1].markdown(cell(_escape(row.get("source_email", ""))), unsafe_allow_html=True)
    cols[2].markdown(cell(_escape(row.get("id_number", ""))), unsafe_allow_html=True)
    cols[3].markdown(cell(_escape(row.get("name_en", ""))), unsafe_allow_html=True)
    cols[4].markdown(cell(render_arabic(row.get("name_ar", ""))), unsafe_allow_html=True)
    cols[5].markdown(cell(status_badge(str(row.get("status", "")))), unsafe_allow_html=True)
    cols[6].markdown(cell(failed_html), unsafe_allow_html=True)

    # Action buttons — demo wiring uses st.toast. Real deployment would
    # call an Exchange/Graph API for email and a CBS/CRM API for the
    # second one.
    name = row.get("name_en") or row.get("name_ar") or row.get("id_number", "this applicant")
    email = row.get("source_email", "")

    with cols[7]:
        if st.button("Send Email", key=f"verify_{i}", width="stretch"):
            st.toast(f"Verification email sent to {email or name}")
    with cols[8]:
        if st.button("Add to CRM", key=f"crm_{i}", width="stretch"):
            st.toast(f"{name} appended to CRM")
