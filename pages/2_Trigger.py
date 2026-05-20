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

import io
import json

import pandas as pd

from app_lib.ksa_data import parse_csv_bytes as parse_ksa_csv
from app_lib.ksa_view import render_queue as render_ksa_queue
from app_lib.parsing import load_report
from app_lib.report_view import render_full_report
from app_lib.robocorp_client import ControlRoom, RobocorpConfig

st.set_page_config(page_title="Trigger Scan", page_icon="play", layout="wide")
st.logo("logo.png", size="large")
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


_KSA_MARKER_COLUMNS = {"id_number", "name_ar", "failed_rules", "app_id"}


def _is_ksa_report_bytes(raw: bytes, name_hint: str | None = None) -> bool:
    looks_json = raw.lstrip().startswith(b"{") or (
        name_hint and name_hint.lower().endswith(".json")
    )
    if looks_json:
        try:
            payload = json.loads(raw)
        except ValueError:
            return False
        records = payload.get("records") if isinstance(payload, dict) else None
        if isinstance(records, list) and records:
            return bool(_KSA_MARKER_COLUMNS & set(records[0].keys()))
        return False
    try:
        header = pd.read_csv(
            io.BytesIO(raw), encoding="utf-8-sig", dtype=str, nrows=0
        )
    except Exception:  # noqa: BLE001
        return False
    return bool(_KSA_MARKER_COLUMNS & set(header.columns))


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
    report = by_name.get("report.json") or by_name.get("report.csv")

    if not report:
        st.warning(
            "Run completed but no `report.csv` (or `report.json`) was produced. "
            "Check the bot's log."
        )
        return

    try:
        raw_report = client.download_artifact(report["step_run_id"], report["id"])
    except httpx.HTTPError as exc:
        st.error(f"Failed to download report: {exc}")
        return

    if _is_ksa_report_bytes(raw_report, report.get("name")):
        try:
            ksa_df = parse_ksa_csv(raw_report)
        except ValueError as exc:
            st.error(f"Failed to parse report: {exc}")
            return
        render_ksa_queue(ksa_df)
        return

    try:
        df = load_report(raw_report, name_hint=report.get("name"))
    except ValueError as exc:
        st.error(f"Failed to parse report: {exc}")
        return

    render_full_report(df)


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
