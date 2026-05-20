"""Streamlit renderers for the KSA Account Opening bot's four tabs.

Conventions:
- Arabic values are wrapped in `direction:rtl; unicode-bidi:embed;` so browsers
  apply contextual joining (otherwise Arabic renders as disconnected glyphs).
- Status colors are defined here as the single source of truth for the KSA
  section. They are intentionally not shared with the DLP modules.
- The detail tab is source-agnostic: when a per-app JSON is available
  (filesystem mode) it shows the rich `decision.results`; when only the CSV
  row is available (Control Room mode) it synthesizes the 6-row rule table
  from `failed_rules` plus a static rule catalog.
"""

from __future__ import annotations

import json
from typing import Any, Union

import pandas as pd
import streamlit as st

from .ksa_data import STATUS_ORDER, ControlRoomSource

KsaSource = Union[ControlRoomSource]

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

# Order matters — this is the canonical order shown in the rule-results table.
RULE_ORDER = [
    "id_format",
    "id_checksum",
    "not_expired",
    "age_18plus",
    "name_present",
    "sanctions",
]

RULE_SEVERITY = {
    "id_format": "blocking",
    "id_checksum": "blocking",
    "not_expired": "blocking",
    "age_18plus": "blocking",
    "name_present": "warning",
    "sanctions": "blocking",
}


# -- HTML helpers --------------------------------------------------------

def render_arabic(text: str | None) -> str:
    """Inline span that forces RTL + contextual joining for Arabic glyphs."""
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


# -- Tab 1: Queue --------------------------------------------------------

def render_queue(df: pd.DataFrame) -> None:
    if df.empty:
        st.info(
            "No applications found in this run yet. Run the KSA bot to "
            "produce `applications.csv`."
        )
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


# -- Tab 2: Detail -------------------------------------------------------

def render_detail(source: KsaSource, df: pd.DataFrame, run_id: str | None = None) -> None:
    if df.empty:
        st.info("No applications to inspect yet.")
        return

    options = df["app_id"].astype(str).tolist()
    labels = {
        aid: _detail_option_label(df[df["app_id"].astype(str) == aid].iloc[0])
        for aid in options
    }
    selected = st.selectbox(
        "Application",
        options=options,
        format_func=lambda aid: labels.get(aid, aid),
        key="ksa_detail_selector",
    )
    if not selected:
        return

    row = df[df["app_id"].astype(str) == selected].iloc[0]
    detail = source.load_detail(run_id, selected)
    fields = (detail.get("fields") if detail else None) or {}
    decision = (detail.get("decision") if detail else None) or {}

    # Prefer richer per-app JSON fields, fall back to CSV row.
    def pick(key: str) -> Any:
        return fields.get(key) if fields.get(key) not in (None, "") else row.get(key, "")

    status = decision.get("status") or row.get("status", "")
    document_path = (detail.get("document_path") if detail else None) or row.get("document_path")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### Source document")
        doc_path = source.resolve_document(run_id, document_path)
        if doc_path is not None:
            try:
                st.image(str(doc_path), use_container_width=True)
            except Exception as exc:  # noqa: BLE001 — image format issues vary
                st.caption(f"Could not render image: {exc}")
                st.code(str(document_path) or "")
        else:
            st.caption(
                "Image not attached to this run "
                "(document images are not uploaded as Control Room artifacts)."
            )
            if document_path:
                st.code(str(document_path))

    with right:
        st.markdown("#### Extracted fields")
        st.markdown(status_badge(str(status)), unsafe_allow_html=True)
        st.markdown("")
        _render_field("OCR engine", pick("ocr_engine") or row.get("ocr_engine"))
        _render_field("ID number", pick("id_number"))
        _render_field("ID type", pick("id_type"))
        _render_field("Name (EN)", pick("name_en"))
        _render_field_html("Name (AR)", render_arabic(pick("name_ar")))
        _render_field("DOB (Gregorian)", pick("dob_gregorian"))
        _render_field("Expiry (Gregorian)", pick("expiry_gregorian"))
        _render_field("Nationality", pick("nationality"))
        _render_field("Gender", pick("gender"))

    st.divider()
    st.markdown("#### Rule results")
    results = (decision.get("results") or []) if decision else []
    if not results:
        results = _synthesize_rule_results(row)
        st.caption(
            "Synthesized from `failed_rules` (per-application JSON is not "
            "attached to Control Room runs)."
        )
    _render_rules_table(results)

    raw_ocr = (detail.get("raw_ocr_text") or fields.get("raw_text")) if detail else ""
    if raw_ocr:
        with st.expander("Raw OCR text"):
            st.code(raw_ocr)


def _detail_option_label(row: pd.Series) -> str:
    app_id = str(row.get("app_id", ""))
    short = app_id[:8] if app_id else "?"
    name = row.get("name_en") or row.get("name_ar") or "(no name)"
    status = STATUS_LABELS.get(str(row.get("status", "")), str(row.get("status", "")))
    return f"{short} — {name}  [{status}]"


def _synthesize_rule_results(row: pd.Series) -> list[dict[str, Any]]:
    failed_raw = str(row.get("failed_rules", "") or "")
    failed = {r.strip() for r in failed_raw.split(";") if r.strip()}

    expiry = str(row.get("expiry_gregorian", "") or "")
    id_number = str(row.get("id_number", "") or "")

    def detail_for(rule: str, did_fail: bool) -> str:
        if rule == "id_format":
            return ("Format invalid (expected 10 digits, leading 1 or 2)" if did_fail
                    else "10-digit, leading 1 or 2")
        if rule == "id_checksum":
            if did_fail and id_number and id_number.isdigit() and len(id_number) == 10:
                return (
                    f"Checksum mismatch — last digit {id_number[-1]} doesn't match "
                    "the computed check digit (likely OCR misread)"
                )
            return "Checksum mismatch — likely OCR misread" if did_fail else "Checksum valid"
        if rule == "not_expired":
            return (f"Document expired on {expiry}" if did_fail and expiry
                    else f"Valid until {expiry}" if expiry
                    else "Document not expired")
        if rule == "age_18plus":
            return "Applicant under 18" if did_fail else "Applicant is 18 or older"
        if rule == "name_present":
            return ("Name missing or not extracted" if did_fail
                    else "Arabic and English names both extracted")
        if rule == "sanctions":
            return ("Match against sanctions stub list" if did_fail
                    else "No match against stub sanctions list")
        return ""

    return [
        {
            "rule": r,
            "passed": r not in failed,
            "severity": RULE_SEVERITY.get(r, "warning"),
            "detail": detail_for(r, r in failed),
        }
        for r in RULE_ORDER
    ]


def _render_field(label: str, value: Any) -> None:
    val = "—" if value in (None, "") else _escape(value)
    st.markdown(
        f"<div style='display:flex; gap:12px; padding:4px 0; "
        f"border-bottom:1px solid #f3f4f6;'>"
        f"<div style='width:140px; color:#6b7280; font-size:0.9rem;'>{label}</div>"
        f"<div style='font-size:0.95rem;'>{val}</div></div>",
        unsafe_allow_html=True,
    )


def _render_field_html(label: str, value_html: str) -> None:
    st.markdown(
        f"<div style='display:flex; gap:12px; padding:4px 0; "
        f"border-bottom:1px solid #f3f4f6;'>"
        f"<div style='width:140px; color:#6b7280; font-size:0.9rem;'>{label}</div>"
        f"<div style='font-size:0.95rem;'>{value_html}</div></div>",
        unsafe_allow_html=True,
    )


def _render_rules_table(results: list[dict[str, Any]]) -> None:
    if not results:
        st.caption("No rule results recorded.")
        return

    headers = ["Rule", "Passed", "Severity", "Detail"]
    rows_html = []
    for r in results:
        passed = bool(r.get("passed"))
        rule = str(r.get("rule", ""))
        severity = str(r.get("severity", ""))
        detail = r.get("detail", "")
        is_checksum_fail = (rule == "id_checksum" and not passed)

        row_bg = "#fef2f2" if not passed else "#ffffff"
        passed_html = (
            "<span style='color:#16a34a; font-weight:600;'>✓</span>"
            if passed
            else "<span style='color:#dc2626; font-weight:600;'>✗</span>"
        )
        detail_html = _escape(detail)
        if is_checksum_fail:
            detail_html = f"<strong style='color:#b91c1c;'>{detail_html}</strong>"
        rows_html.append(
            f"<tr style='background:{row_bg};'>"
            f"<td style='padding:6px 10px; border-bottom:1px solid #e5e7eb;'><code>{_escape(rule)}</code></td>"
            f"<td style='padding:6px 10px; border-bottom:1px solid #e5e7eb; text-align:center;'>{passed_html}</td>"
            f"<td style='padding:6px 10px; border-bottom:1px solid #e5e7eb;'>{_escape(severity)}</td>"
            f"<td style='padding:6px 10px; border-bottom:1px solid #e5e7eb;'>{detail_html}</td>"
            f"</tr>"
        )
    head = "".join(
        f"<th style='text-align:left; padding:8px 10px; border-bottom:2px solid #d1d5db; "
        f"font-size:0.85rem; color:#374151;'>{h}</th>" for h in headers
    )
    st.markdown(
        "<table style='width:100%; border-collapse:collapse; font-size:0.9rem;'>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>",
        unsafe_allow_html=True,
    )


# -- Tab 3: Audit Log ----------------------------------------------------

def render_audit(audit: dict[str, Any]) -> None:
    if not audit:
        st.info("No audit log available for this run.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Run ID**\n\n`{audit.get('run_id', '—')}`")
    c2.markdown(f"**Started**\n\n{audit.get('started_at', '—')}")
    c3.markdown(f"**Completed**\n\n{audit.get('completed_at', '—')}")
    c4.markdown(f"**Events**\n\n{audit.get('event_count', '—')}")

    events = audit.get("events") or []
    if not events:
        st.caption("No events recorded.")
        return

    all_event_names = sorted({str(e.get("event", "")) for e in events if e.get("event")})
    selected = st.multiselect(
        "Event types",
        options=all_event_names,
        default=all_event_names,
        key="ksa_audit_event_filter",
    )

    filtered = [e for e in events if str(e.get("event", "")) in selected]

    rows = [
        {
            "timestamp": e.get("timestamp", ""),
            "event": e.get("event", ""),
            "payload": json.dumps(e.get("payload", {}), ensure_ascii=False),
        }
        for e in filtered
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(f"Showing {len(filtered)} of {len(events)} events.")

    with st.expander("Raw JSONL"):
        lines = [json.dumps(e, ensure_ascii=False) for e in filtered]
        st.code("\n".join(lines), language="json")


