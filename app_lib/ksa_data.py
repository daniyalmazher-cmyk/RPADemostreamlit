"""Load KSA Account Opening bot artifacts from Robocorp Control Room.

The bot's robot.yaml uploads `applications.csv` and `audit_log.json` per run.
Per-app detail JSONs and document images are NOT uploaded — the detail tab
reconstructs rule results from the CSV's `failed_rules` column plus a static
catalog (see `ksa_view._synthesize_rule_results`).
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .robocorp_client import ControlRoom, RobocorpConfig

STATUS_ORDER = ["auto_approve", "needs_review", "auto_reject"]


@dataclass(frozen=True)
class ControlRoomSource:
    robocorp: RobocorpConfig
    process_id: str

    mode: str = "control_room"

    @property
    def description(self) -> str:
        return f"Control Room · process `{self.process_id[:8]}…`"

    def is_available(self) -> bool:
        return bool(self.robocorp.api_key and self.process_id)

    def list_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        return _cr_list_runs(self.robocorp, self.process_id, limit)

    def _artifact_bytes(self, run_id: str, name: str) -> bytes | None:
        arts = _cr_list_artifacts(self.robocorp, run_id)
        match = next((a for a in arts if a.get("name") == name), None)
        if not match:
            return None
        return _cr_download(self.robocorp, match["step_run_id"], match["id"])

    def load_applications(self, run_id: str | None = None) -> pd.DataFrame:
        if not run_id:
            return pd.DataFrame()
        raw = self._artifact_bytes(run_id, "applications.csv")
        if raw is None:
            return pd.DataFrame()
        return _parse_csv_bytes(raw)

    def load_audit(self, run_id: str | None = None) -> dict[str, Any]:
        if not run_id:
            return {}
        raw = self._artifact_bytes(run_id, "audit_log.json")
        if raw is None:
            return {}
        return json.loads(raw)

    def load_detail(self, run_id: str | None, app_id: str) -> dict[str, Any]:
        """Per-app JSONs aren't uploaded to Control Room."""
        return {}

    def resolve_document(self, run_id: str | None, document_path: str | None) -> Path | None:
        """Document images aren't uploaded as artifacts either."""
        if not document_path:
            return None
        p = Path(document_path)
        if p.is_absolute() and p.exists():
            return p
        return None


# ---- Cached helpers ----------------------------------------------------

def _parse_csv_bytes(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(
        io.BytesIO(raw), encoding="utf-8-sig", dtype=str, keep_default_na=False
    )
    if "status" in df.columns:
        df["status"] = pd.Categorical(
            df["status"], categories=STATUS_ORDER, ordered=True
        )
    return df


@st.cache_data(ttl=30, show_spinner=False)
def _cr_list_runs(cfg: RobocorpConfig, process_id: str, limit: int) -> list[dict[str, Any]]:
    with ControlRoom(cfg) as cr:
        return cr.list_process_runs(process_id, limit=limit)


@st.cache_data(ttl=300, show_spinner=False)
def _cr_list_artifacts(cfg: RobocorpConfig, run_id: str) -> list[dict[str, Any]]:
    with ControlRoom(cfg) as cr:
        return cr.list_run_artifacts(run_id)


@st.cache_data(ttl=3600, show_spinner=False)
def _cr_download(cfg: RobocorpConfig, step_run_id: str, artifact_id: str) -> bytes:
    with ControlRoom(cfg) as cr:
        return cr.download_artifact(step_run_id, artifact_id)
