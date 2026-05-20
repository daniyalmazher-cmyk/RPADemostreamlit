"""KSA Account Opening Bot — Saudi bank demo dashboard.

Two data sources, auto-selected:

- **Control Room** when `[ksa].process_id` is set in `.streamlit/secrets.toml`.
  Lists runs of that process and downloads `applications.csv` +
  `audit_log.json` for the chosen run.
- **Filesystem** otherwise — reads from `KSA_BOT_OUTPUT_DIR` (env),
  `[ksa].output_dir` (secrets), or the default sibling-repo path.

Self-contained: imports nothing from the DLP modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from app_lib.ksa_data import ControlRoomSource, FilesystemSource, resolve_source
from app_lib.ksa_view import (
    render_architecture,
    render_audit,
    render_detail,
    render_queue,
)

st.set_page_config(
    page_title="KSA Account Opening",
    page_icon="bank",
    layout="wide",
)

st.title("KSA Account Opening Bot")
st.caption(
    "Saudi national-ID / Iqama account opening pipeline: "
    "email intake → OCR → field extraction → KYC + sanctions → decision."
)

source = resolve_source(st.secrets)


def _format_started(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_state(state: str | None) -> str:
    badges = {
        "completed": ":green[Completed]",
        "unresolved": ":red[Failed]",
        "in_progress": ":orange[Running]",
        "new": ":blue[New]",
        "stopping": ":orange[Stopping]",
    }
    if not state:
        return "—"
    return badges.get(state, f"`{state}`")


with st.sidebar:
    st.markdown("### Data source")
    if source.is_available():
        st.success(source.mode.replace("_", " ").title())
    else:
        st.warning(f"Source not available ({source.mode})")
    st.caption(source.description)
    if isinstance(source, ControlRoomSource):
        if st.button("Refresh runs", width="stretch"):
            st.cache_data.clear()
            st.rerun()


run_id: str | None = None
df = None
audit: dict[str, Any] = {}

if isinstance(source, ControlRoomSource):
    try:
        runs = source.list_runs(limit=25)
    except Exception as exc:  # noqa: BLE001 — surface any API error in the UI
        st.error(f"Failed to list Control Room runs: {exc}")
        st.stop()

    if not runs:
        st.info("No runs found for the KSA process yet.")
        st.stop()

    options = [r["id"] for r in runs]
    labels = {
        r["id"]: (
            f"{r['id'][:8]}…  ·  "
            f"{_format_started(r.get('start_time') or r.get('started_at'))}  ·  "
            f"{_format_state(r.get('state'))}"
        )
        for r in runs
    }
    run_id = st.selectbox(
        "Run",
        options=options,
        format_func=lambda rid: labels.get(rid, rid),
        key="ksa_run_selector",
    )

    selected_run = next(r for r in runs if r["id"] == run_id)
    meta = st.columns(3)
    meta[0].markdown(f"**State**\n\n{_format_state(selected_run.get('state'))}")
    meta[1].markdown(
        f"**Started**\n\n{_format_started(selected_run.get('start_time') or selected_run.get('started_at'))}"
    )
    duration = selected_run.get("duration")
    meta[2].markdown(f"**Duration**\n\n{duration if duration is not None else '—'} s")

    with st.spinner("Downloading run artifacts…"):
        df = source.load_applications(run_id)
        audit = source.load_audit(run_id)

elif isinstance(source, FilesystemSource):
    if not source.is_available():
        st.warning(
            f"`applications.csv` not found at `{source.applications_csv}`. "
            "Set `KSA_BOT_OUTPUT_DIR`, add `[ksa].output_dir` to "
            "`.streamlit/secrets.toml`, configure `[ksa].process_id`, or run "
            "the bot to populate it."
        )
        st.stop()
    df = source.load_applications()
    audit = source.load_audit()


queue_tab, detail_tab, audit_tab, arch_tab = st.tabs(
    ["Application Queue", "Application Detail", "Audit Log", "Architecture"]
)

with queue_tab:
    render_queue(df)

with detail_tab:
    render_detail(source, df, run_id=run_id)

with audit_tab:
    render_audit(audit)

with arch_tab:
    render_architecture()
