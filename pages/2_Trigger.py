"""Trigger page — start a new bot run in Control Room and view the result."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import streamlit as st

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

st.markdown("#### Optional work item payload")
st.caption(
    "JSON object passed to the bot as a work item. Leave empty to trigger with no payload."
)
payload_text = st.text_area(
    "Payload (JSON)",
    value=st.session_state.get(
        "trigger_payload",
        json.dumps(
            {"batch_id": "manual-streamlit", "requested_by": "dashboard"}, indent=2
        ),
    ),
    height=140,
    key="trigger_payload",
)


def _parse_payload(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Payload must be a JSON object.")
    return value


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


def _render_completed_run(run: dict[str, Any]) -> None:
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

    if not report:
        st.warning(
            "Run completed but no classification report artifact was produced. "
            "Check the bot's log."
        )
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
        payload = _parse_payload(payload_text)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    try:
        result = _client().start_process_run(process_id, work_item_payload=payload)
    except httpx.HTTPError as exc:
        st.error(f"Failed to start run: {exc}")
        st.stop()

    new_run_id = result.get("id") or result.get("process_run_id")
    if not new_run_id:
        st.error(f"Control Room did not return a run id. Response: {result!r}")
        st.stop()

    st.session_state["trigger_history"].insert(
        0, {"run_id": new_run_id, "started": _ts(), "payload": payload}
    )

    with st.status(f"Started run `{new_run_id}` — polling…", expanded=True) as status:
        run = _poll_until_done(new_run_id, every=float(poll_seconds), status=status)
        if run.get("state") == "completed":
            status.update(label=f"Run `{new_run_id}` completed.", state="complete")
        elif run.get("state") == "unresolved":
            status.update(label=f"Run `{new_run_id}` failed (unresolved).", state="error")

    _render_completed_run(run)
elif st.session_state["trigger_history"]:
    st.subheader("Recent triggers this session")
    for entry in st.session_state["trigger_history"][:5]:
        st.markdown(
            f"- `{entry['run_id']}` — started {entry['started']}  "
            f"{'· payload sent' if entry.get('payload') else ''}"
        )
else:
    st.info("Click **Run new scan** to start a process run.")
