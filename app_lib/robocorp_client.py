"""Thin httpx client over the Robocorp / Sema4.ai Control Room REST API.

Authentication: every workspace-scoped request carries
`Authorization: RC-WSKEY <api_key>`. Artifact downloads use presigned URLs
returned by the API and therefore must NOT carry the auth header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RobocorpConfig:
    api_base: str
    api_key: str
    workspace_id: str
    process_id: str | None = None

    @classmethod
    def from_secrets(cls, secrets: Any) -> "RobocorpConfig":
        cfg = secrets["robocorp"]
        return cls(
            api_base=cfg["api_base"].rstrip("/"),
            api_key=cfg["api_key"],
            workspace_id=cfg["workspace_id"],
            process_id=cfg.get("process_id"),
        )


class ControlRoom:
    def __init__(self, config: RobocorpConfig, timeout: float = 30.0) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.api_base,
            headers={
                "Authorization": f"RC-WSKEY {config.api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ControlRoom":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- internal ----------------------------------------------------

    @property
    def _ws_path(self) -> str:
        return f"/v1/workspaces/{self.config.workspace_id}"

    def _get(self, path: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        r = self._client.get(path, params=params or None)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: Any = None) -> Any:
        r = self._client.post(path, json=json)
        r.raise_for_status()
        if not r.content:
            return {}
        return r.json()

    @staticmethod
    def _items(payload: Any) -> list[dict[str, Any]]:
        """Unwrap a paginated response into a plain list of records.

        Control Room returns either `{"data": [...], "next": ...}` or, on
        older endpoints, a bare list. Tolerate both.
        """
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "items", "results"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        return []

    # ---- processes ---------------------------------------------------

    def list_processes(self) -> list[dict[str, Any]]:
        return self._items(self._get(f"{self._ws_path}/processes"))

    def get_process(self, process_id: str) -> dict[str, Any]:
        return self._get(f"{self._ws_path}/processes/{process_id}")

    # ---- process runs ------------------------------------------------

    def list_process_runs(
        self,
        process_id: str | None = None,
        limit: int = 25,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._get(
            f"{self._ws_path}/process-runs",
            process_id=process_id,
            limit=limit,
            state=state,
        )
        return self._items(payload)

    def get_process_run(self, run_id: str) -> dict[str, Any]:
        return self._get(f"{self._ws_path}/process-runs/{run_id}")

    def start_process_run(
        self,
        process_id: str,
        work_item_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if work_item_payload is not None:
            body["workItems"] = [{"payload": work_item_payload}]
        return self._post(
            f"{self._ws_path}/processes/{process_id}/process-runs",
            json=body,
        )

    # ---- step runs + artifacts --------------------------------------

    def list_step_runs(self, process_run_id: str) -> list[dict[str, Any]]:
        """Step runs are the per-step children of a process run.

        Artifacts hang off step runs, not the process run itself.
        """
        payload = self._get(
            f"{self._ws_path}/step-runs",
            process_run_id=process_run_id,
        )
        return self._items(payload)

    def list_step_artifacts(self, step_run_id: str) -> list[dict[str, Any]]:
        return self._items(
            self._get(f"{self._ws_path}/step-runs/{step_run_id}/artifacts")
        )

    def get_step_artifact(self, step_run_id: str, artifact_id: str) -> dict[str, Any]:
        """Returns artifact metadata, usually including a presigned `url`."""
        return self._get(
            f"{self._ws_path}/step-runs/{step_run_id}/artifacts/{artifact_id}"
        )

    def list_run_artifacts(self, process_run_id: str) -> list[dict[str, Any]]:
        """Flatten artifacts across every step run for a process run.

        Each item is enriched with `step_run_id` and `step_name` so the caller
        can show provenance without a second lookup.
        """
        out: list[dict[str, Any]] = []
        for step in self.list_step_runs(process_run_id):
            sid = step.get("id") or step.get("step_run_id")
            if not sid:
                continue
            step_name = (step.get("step") or {}).get("name") or step.get("name")
            for art in self.list_step_artifacts(sid):
                art = dict(art)
                art.setdefault("step_run_id", sid)
                art.setdefault("step_name", step_name)
                out.append(art)
        return out

    def download_artifact(self, step_run_id: str, artifact_id: str) -> bytes:
        """Fetch an artifact's bytes.

        The API returns metadata with a presigned `url`. We then download
        that URL *without* the workspace auth header (presigned URLs reject
        extra auth headers).
        """
        meta = self.get_step_artifact(step_run_id, artifact_id)
        url = meta.get("url") or meta.get("download_url")
        if not url:
            raise RuntimeError(
                f"Artifact {artifact_id} has no downloadable url in response: {meta!r}"
            )
        with httpx.Client(timeout=60.0, follow_redirects=True) as fresh:
            r = fresh.get(url)
            r.raise_for_status()
            return r.content


if __name__ == "__main__":
    # Smoke test: list recent runs of the configured process.
    import tomllib
    from pathlib import Path

    secrets_path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    with secrets_path.open("rb") as fh:
        secrets = tomllib.load(fh)

    cfg = RobocorpConfig.from_secrets(secrets)
    with ControlRoom(cfg) as cr:
        print(f"Base URL: {cfg.api_base}")
        print(f"Workspace: {cfg.workspace_id}")
        print()
        print("== Processes ==")
        processes = cr.list_processes()
        for p in processes[:5]:
            print(f"  {p.get('id')}  {p.get('name')}")
        print()
        if cfg.process_id:
            print(f"== Recent runs of {cfg.process_id} ==")
            runs = cr.list_process_runs(cfg.process_id, limit=5)
            for r in runs:
                print(
                    f"  {r.get('id')}  state={r.get('state')}  "
                    f"started={r.get('start_time') or r.get('started_at')}"
                )
            if runs:
                rid = runs[0]["id"]
                print()
                print(f"== Step runs of {rid} ==")
                for s in cr.list_step_runs(rid):
                    print(f"  {s.get('id')}  {s.get('name') or s.get('step_name')}")
                print()
                print(f"== Artifacts of run {rid} ==")
                for a in cr.list_run_artifacts(rid):
                    print(f"  {a.get('id')}  {a.get('name') or a.get('file_name')}")
