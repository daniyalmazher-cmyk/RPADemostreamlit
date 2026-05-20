"""Load KSA Account Opening bot artifacts from Control Room or local disk.

Two sources, auto-selected by `resolve_source()`:

- **Control Room** (when `[ksa].process_id` is set in secrets): lists runs of
  the KSA process and downloads `applications.csv` + `audit_log.json` for a
  chosen run. The bot's robot.yaml currently uploads only those two; per-app
  detail JSONs and document images are NOT uploaded, so the detail tab is
  reconstructed from CSV rows plus a static rule catalog.

- **Filesystem** (fallback): reads from `KSA_BOT_OUTPUT_DIR` (env), or
  `[ksa].output_dir` (secrets), or `../account_opening_bot/output` (default).
  Per-app JSONs and source images are loaded when present, giving the
  richer detail view.
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .robocorp_client import ControlRoom, RobocorpConfig

DEFAULT_OUTPUT_DIR = "../account_opening_bot/output"

STATUS_ORDER = ["auto_approve", "needs_review", "auto_reject"]


# ---- Filesystem source -------------------------------------------------

@dataclass(frozen=True)
class FilesystemSource:
    output_dir: Path

    mode: str = "filesystem"

    @property
    def description(self) -> str:
        return f"Local filesystem · `{self.output_dir}`"

    @property
    def applications_csv(self) -> Path:
        return self.output_dir / "applications.csv"

    @property
    def applications_dir(self) -> Path:
        return self.output_dir / "applications"

    @property
    def audit_log_path(self) -> Path:
        return self.output_dir / "audit_log.json"

    def detail_path(self, app_id: str) -> Path:
        return self.applications_dir / f"{app_id}.json"

    def is_available(self) -> bool:
        return self.applications_csv.exists()

    def list_runs(self) -> list[dict[str, Any]] | None:
        """Filesystem has no concept of runs — return None to suppress selector."""
        return None

    def load_applications(self, run_id: str | None = None) -> pd.DataFrame:
        return _load_csv_path(str(self.applications_csv), _mtime(self.applications_csv))

    def load_audit(self, run_id: str | None = None) -> dict[str, Any]:
        return _load_json_path(str(self.audit_log_path), _mtime(self.audit_log_path))

    def load_detail(self, run_id: str | None, app_id: str) -> dict[str, Any]:
        p = self.detail_path(app_id)
        return _load_json_path(str(p), _mtime(p))

    def resolve_document(self, run_id: str | None, document_path: str | None) -> Path | None:
        if not document_path:
            return None
        p = Path(document_path)
        if p.is_absolute():
            return p if p.exists() else None
        for candidate in (
            self.output_dir.parent / p,
            self.output_dir / p,
            Path.cwd() / p,
        ):
            if candidate.exists():
                return candidate
        return None


# ---- Control Room source -----------------------------------------------

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
        """The bot doesn't upload per-app JSONs to Control Room — return empty."""
        return {}

    def resolve_document(self, run_id: str | None, document_path: str | None) -> Path | None:
        """Document images aren't uploaded as artifacts. Try local fallback only."""
        if not document_path:
            return None
        p = Path(document_path)
        if p.is_absolute() and p.exists():
            return p
        for candidate in (
            Path(DEFAULT_OUTPUT_DIR).expanduser().resolve().parent / p,
            Path.cwd() / p,
        ):
            if candidate.exists():
                return candidate
        return None


# ---- Source selection --------------------------------------------------

def resolve_source(secrets: Any) -> FilesystemSource | ControlRoomSource:
    """Prefer Control Room when configured; fall back to filesystem."""
    ksa_cfg = secrets.get("ksa") if hasattr(secrets, "get") else None
    robocorp_cfg = secrets.get("robocorp") if hasattr(secrets, "get") else None

    ksa_process_id = ksa_cfg.get("process_id") if ksa_cfg else None
    if ksa_process_id and robocorp_cfg and robocorp_cfg.get("api_key"):
        return ControlRoomSource(
            robocorp=RobocorpConfig.from_secrets(secrets),
            process_id=ksa_process_id,
        )

    raw = os.environ.get("KSA_BOT_OUTPUT_DIR")
    if not raw and ksa_cfg:
        raw = ksa_cfg.get("output_dir")
    if not raw:
        raw = DEFAULT_OUTPUT_DIR
    return FilesystemSource(output_dir=Path(raw).expanduser().resolve())


# ---- Cached helpers ----------------------------------------------------

def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


@st.cache_data(ttl=30, show_spinner=False)
def _load_csv_path(csv_path: str, sig: float) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame()
    return _parse_csv_bytes(path.read_bytes())


@st.cache_data(ttl=30, show_spinner=False)
def _load_json_path(json_path: str, sig: float) -> dict[str, Any]:
    path = Path(json_path)
    if not path.exists():
        return {}
    return json.loads(path.read_bytes())


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
