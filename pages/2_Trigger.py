"""Trigger page — start a new bot run in Control Room and view the result.

Bot-agnostic: detects whether the completed run is a DLP-shaped run
(`classification_report.*`) or a KSA-shaped run (`applications.csv`) and
dispatches to the matching renderer.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
import streamlit as st

from app_lib.ksa_data import ControlRoomSource as KsaSource
from app_lib.ksa_view import (
    render_audit as render_ksa_audit,
    render_detail as render_ksa_detail,
    render_queue as render_ksa_queue,
)
from app_lib.parsing import load_audit_log, load_report
from app_lib.report_view import render_full_report
from app_lib.robocorp_client import ControlRoom, RobocorpConfig

st.set_page_config(page_title="Trigger Scan", page_icon="play", layout="wide")
st.title("Trigger a new scan")
st.caption("Kick off a process run in Robocorp Control Room and watch it complete.")


if "robocorp" not in st.secrets:
    st.error(
        "No Robocorp credentials configured. Add an `[robocorp]` block to "
        "`.streamlit/secrets.toml`."
    )
    st.stop()

cfg = RobocorpConfig.from_secrets(st.secrets)


@st.cache_resource(show_spinner=False)
def _client() -> ControlRoom:
    return ControlRoom(RobocorpConfig.from_secrets(st.secrets))


@st.cache_data(ttl=120, show_spinner=False)
def _list_processes() -> list[dict[str, Any]]:
    return _client().list_processes()


try:
    processes = _list_processes()
except httpx.HTTPError as exc:
    st.error(f"Failed to list processes: {exc}")
    st.stop()

process_labels = {p["id"]: f"{p.get('name') or p['id']}" for p in processes}
if not process_labels:
    st.warning("No processes available in this workspace.")
    st.stop()

default_pid = cfg.process_id if cfg.process_id in process_labels else next(iter(process_labels))

col1, col2 = st.columns([2, 1])
with col1:
    process_id = st.selectbox(
        "Process",
        options=list(process_labels.keys()),
        index=list(process_labels.keys()).index(default_pid),
        format_func=lambda pid: process_labels.get(pid, pid),
    )

with col2:
    poll_seconds = st.number_input(
        "Poll every (seconds)",
        min_value=2,
        max_value=30,
        value=4,
        step=1,
    )


TERMINAL_STATES = {"completed", "unresolved"}
POLL_CAP_SECONDS = 600


def _poll_until_done(
    run_id: str, every: float, status: Any
) -> dict[str, Any]:
    """Block-poll a process run until terminal, refreshing the st.status panel."""
    started = time.monotonic()
    client = _client()
    while True:
        run = client.get_process_run(run_id)
        state = run.get("state")
        elapsed = int(time.monotonic() - started)
        status.update(label=f"Run state: {state}  ·  {elapsed}s elapsed")
        if state in TERMINAL_STATES:
            return run
        if elapsed > POLL_CAP_SECONDS:
            status.update(label=f"Stopped polling after {POLL_CAP_SECONDS}s (state={state})", state="error")
            return run
        time.sleep(every)


def _render_completed_run(run: dict[str, Any], process_id: str) -> None:
    run_id = run["id"]
    st.success(f"Run finished. ID: `{run_id}`  ·  state: `{run.get('state')}`")

    client = _client()
    try:
        artifacts = client.list_run_artifacts(run_id)
    except httpx.HTTPError as exc:
        st.error(f"Failed to list artifacts: {exc}")
        return

    by_name = {a.get("name"): a for a in artifacts}
    report = by_name.get("classification_report.json") or by_name.get(
        "classification_report.csv"
    )
    audit_art = by_name.get("audit_log.json")
    is_ksa_run = "applications.csv" in by_name and not report

    if not report and not is_ksa_run:
        st.warning(
            "Run completed but no recognized report artifact was produced "
            "(`classification_report.json/.csv` for the DLP bot, "
            "`applications.csv` for the KSA bot). Check the bot's log."
        )
        return

    if is_ksa_run:
        ksa_source = KsaSource(robocorp=cfg, process_id=process_id)
        try:
            ksa_df = ksa_source.load_applications(run_id)
            ksa_audit = ksa_source.load_audit(run_id)
        except (httpx.HTTPError, ValueError) as exc:
            st.error(f"Failed to load KSA artifacts: {exc}")
            return

        queue_tab, detail_tab, audit_tab = st.tabs(
            ["Application Queue", "Application Detail", "Audit Log"]
        )
        with queue_tab:
            render_ksa_queue(ksa_df)
        with detail_tab:
            render_ksa_detail(ksa_source, ksa_df, run_id=run_id)
        with audit_tab:
            render_ksa_audit(ksa_audit)
        return

    try:
        raw_report = client.download_artifact(report["step_run_id"], report["id"])
        df = load_report(raw_report, name_hint=report.get("name"))
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Failed to load report: {exc}")
        return

    audit = None
    if audit_art:
        try:
            audit = load_audit_log(
                client.download_artifact(audit_art["step_run_id"], audit_art["id"])
            )
        except (httpx.HTTPError, ValueError) as exc:
            st.warning(f"Could not load audit log: {exc}")

    render_full_report(df, audit=audit)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


if "trigger_history" not in st.session_state:
    st.session_state["trigger_history"] = []


go = st.button("Run new scan", type="primary", width="content")

if go:
    try:
        result = _client().start_process_run(process_id)
    except httpx.HTTPError as exc:
        st.error(f"Failed to start run: {exc}")
        st.stop()

    new_run_id = result.get("id") or result.get("process_run_id")
    if not new_run_id:
        st.error(f"Control Room did not return a run id. Response: {result!r}")
        st.stop()

    st.session_state["trigger_history"].insert(
        0, {"run_id": new_run_id, "started": _ts(), "process_id": process_id}
    )

    with st.status(f"Started run `{new_run_id}` — polling…", expanded=True) as status:
        run = _poll_until_done(new_run_id, every=float(poll_seconds), status=status)
        if run.get("state") == "completed":
            status.update(label=f"Run `{new_run_id}` completed.", state="complete")
        elif run.get("state") == "unresolved":
            status.update(label=f"Run `{new_run_id}` failed (unresolved).", state="error")

    _render_completed_run(run, process_id)
elif st.session_state["trigger_history"]:
    st.subheader("Recent triggers this session")
    for entry in st.session_state["trigger_history"][:5]:
        st.markdown(f"- `{entry['run_id']}` — started {entry['started']}")
else:
    st.info("Click **Run new scan** to start a process run.")
