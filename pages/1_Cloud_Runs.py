"""Cloud Runs page — list bot runs from Control Room and render the chosen one."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd
import streamlit as st

import io

from app_lib.ksa_data import parse_csv_bytes as parse_ksa_csv
from app_lib.ksa_view import render_queue as render_ksa_queue
from app_lib.parsing import load_report
from app_lib.report_view import render_full_report
from app_lib.robocorp_client import ControlRoom, RobocorpConfig

st.set_page_config(page_title="Cloud Runs", page_icon="cloud", layout="wide")
st.logo("logo.png", size="large")
st.title("Cloud Runs")
st.caption("Browse recent runs of the discovery bot in Robocorp Control Room.")


def _config() -> RobocorpConfig | None:
    if "robocorp" not in st.secrets:
        st.error(
            "No Robocorp credentials configured. Add an `[robocorp]` block to "
            "`.streamlit/secrets.toml`."
        )
        return None
    return RobocorpConfig.from_secrets(st.secrets)


@st.cache_resource(show_spinner=False)
def _client() -> ControlRoom:
    cfg = RobocorpConfig.from_secrets(st.secrets)
    return ControlRoom(cfg)


@st.cache_data(ttl=120, show_spinner=False)
def _list_processes() -> list[dict[str, Any]]:
    return _client().list_processes()


@st.cache_data(ttl=30, show_spinner=False)
def _list_runs(process_id: str, limit: int) -> list[dict[str, Any]]:
    return _client().list_process_runs(process_id, limit=limit)


@st.cache_data(ttl=300, show_spinner=False)
def _list_artifacts(run_id: str) -> list[dict[str, Any]]:
    return _client().list_run_artifacts(run_id)


@st.cache_data(ttl=3600, show_spinner=False)
def _download(step_run_id: str, artifact_id: str) -> bytes:
    return _client().download_artifact(step_run_id, artifact_id)


# Colored-circle emoji renders consistently in both `st.markdown` and
# `st.dataframe` cells, unlike Streamlit's `:color[label]` syntax which
# only works inside markdown. Covers every process-run state the Control
# Room API can return; unknown states fall back to ⚪.
# Any of these columns indicates an onboarding-bot report (vs. the DLP
# report which uses `file_name` / `classification`). `app_id` was dropped
# from the schema in a recent bot release; `id_number` / `status` /
# `failed_rules` are still load-bearing.
_KSA_MARKER_COLUMNS = {"id_number", "name_ar", "failed_rules", "app_id"}


def _is_ksa_report_bytes(raw: bytes, name_hint: str | None = None) -> bool:
    """Decide whether a downloaded report.csv/.json is from the onboarding bot."""
    looks_json = raw.lstrip().startswith(b"{") or (
        name_hint and name_hint.lower().endswith(".json")
    )
    if looks_json:
        try:
            import json
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
    except Exception:  # noqa: BLE001 — CSV parse can fail in many shapes
        return False
    return bool(_KSA_MARKER_COLUMNS & set(header.columns))


STATE_BADGES = {
    "new":          "🔵 New",
    "in_progress":  "🟡 Running",
    "completed":    "🟢 Completed",
    "unresolved":   "🔴 Failed",
    "stopping":     "🟠 Stopping",
    "stopped":      "⚫ Stopped",
}


def _format_state(state: str | None) -> str:
    if not state:
        return "—"
    return STATE_BADGES.get(state, f"⚪ {state}")


def _format_duration(seconds: Any) -> str:
    if seconds is None:
        return "—"
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "—"
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _format_started(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _runs_to_dataframe(runs: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for r in runs:
        rows.append(
            {
                "id": r.get("id"),
                "state": r.get("state"),
                "started_at": r.get("started_at") or r.get("start_time"),
                "ended_at": r.get("ended_at"),
                "duration_s": r.get("duration"),
                "started_by": (r.get("started_by") or {}).get("type")
                or (r.get("started_by") or {}).get("details", {}).get("first_name"),
            }
        )
    return pd.DataFrame(rows)


cfg = _config()
if not cfg:
    st.stop()

with st.sidebar:
    st.markdown("### Filters")
    try:
        processes = _list_processes()
    except httpx.HTTPError as exc:
        st.error(f"Failed to list processes: {exc}")
        st.stop()

    process_labels = {p["id"]: f"{p.get('name') or p['id']}" for p in processes}
    default_pid = cfg.process_id if cfg.process_id in process_labels else next(iter(process_labels), None)
    if not process_labels:
        st.warning("No processes found in this workspace.")
        st.stop()

    process_id = st.selectbox(
        "Process",
        options=list(process_labels.keys()),
        index=list(process_labels.keys()).index(default_pid) if default_pid else 0,
        format_func=lambda pid: process_labels.get(pid, pid),
    )
    limit = st.slider("Show last N runs", min_value=5, max_value=50, value=20, step=5)
    if st.button("Refresh", width="stretch"):
        _list_runs.clear()
        _list_artifacts.clear()
        st.rerun()

try:
    runs = _list_runs(process_id, limit)
except httpx.HTTPError as exc:
    st.error(f"Failed to list runs: {exc}")
    st.stop()

if not runs:
    st.info("No runs found for this process yet.")
    st.stop()

runs_df = _runs_to_dataframe(runs)

st.subheader("Recent runs")
display = runs_df.copy()
display["state"] = display["state"].apply(_format_state)
display["started_at"] = display["started_at"].apply(_format_started)
display["duration"] = display["duration_s"].apply(_format_duration)
display = display[["id", "state", "started_at", "duration", "started_by"]]
st.dataframe(display, width="stretch", hide_index=True)

st.divider()
st.subheader("Inspect a run")

options = runs_df["id"].tolist()
labels = {
    rid: f"{rid[:8]}…  ·  {_format_started(runs_df.loc[runs_df['id'] == rid, 'started_at'].iloc[0])}"
    f"  ·  {_format_state(runs_df.loc[runs_df['id'] == rid, 'state'].iloc[0])}"
    for rid in options
}
selected_run_id = st.selectbox(
    "Pick a run",
    options=options,
    format_func=lambda rid: labels.get(rid, rid),
)
selected_run = next(r for r in runs if r["id"] == selected_run_id)

meta_cols = st.columns(4)
meta_cols[0].markdown(f"**State**\n\n{_format_state(selected_run.get('state'))}")
meta_cols[1].markdown(f"**Started**\n\n{_format_started(selected_run.get('started_at'))}")
meta_cols[2].markdown(f"**Duration**\n\n{_format_duration(selected_run.get('duration'))}")
started_by = selected_run.get("started_by") or {}
who = (started_by.get("details") or {}).get("first_name") or started_by.get("type") or "—"
meta_cols[3].markdown(f"**Started by**\n\n{who}")

with st.spinner("Loading artifacts…"):
    try:
        artifacts = _list_artifacts(selected_run_id)
    except httpx.HTTPError as exc:
        st.error(f"Failed to list artifacts: {exc}")
        st.stop()

by_name = {a.get("name"): a for a in artifacts}
# Both bots now emit `report.csv`; DLP may additionally emit `report.json`
# with richer per-file detection values, which we prefer when available.
report_artifact = by_name.get("report.json") or by_name.get("report.csv")

if not report_artifact:
    st.warning(
        "This run has no `report.csv` (or `report.json`). "
        "Either the run failed before writing a report, or it's still in progress."
    )
    with st.expander("Available artifacts"):
        if artifacts:
            st.dataframe(
                pd.DataFrame(
                    [{"name": a.get("name"), "size": a.get("size")} for a in artifacts]
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No artifacts attached.")
    st.stop()

with st.spinner("Downloading report…"):
    try:
        raw_report = _download(report_artifact["step_run_id"], report_artifact["id"])
    except httpx.HTTPError as exc:
        st.error(f"Failed to download report: {exc}")
        st.stop()

# Sniff: KSA reports have an `app_id` column; DLP reports don't.
is_ksa_run = _is_ksa_report_bytes(raw_report, report_artifact.get("name"))

if is_ksa_run:
    try:
        ksa_df = parse_ksa_csv(raw_report)
    except ValueError as exc:
        st.error(f"Failed to parse report: {exc}")
        st.stop()

    st.success(f"Loaded run with {len(ksa_df)} applications.")
    render_ksa_queue(ksa_df)
else:
    try:
        df = load_report(raw_report, name_hint=report_artifact.get("name"))
    except ValueError as exc:
        st.error(f"Failed to parse report: {exc}")
        st.stop()

    st.success(f"Loaded report from `{report_artifact['name']}` ({len(df)} files).")
    render_full_report(df)
