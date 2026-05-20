"""Load and normalize the bot's report artifacts into pandas DataFrames."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pandas as pd

CLASSIFICATION_ORDER = ["Public", "Confidential", "Highly Confidential"]

DETECTION_KEYS = ("cnic", "iban", "credit_card", "email", "phone")


def _as_bytes(file_or_bytes: Any) -> bytes:
    if isinstance(file_or_bytes, (bytes, bytearray)):
        return bytes(file_or_bytes)
    if hasattr(file_or_bytes, "read"):
        return file_or_bytes.read()
    with open(file_or_bytes, "rb") as fh:
        return fh.read()


def load_classification_json(raw: bytes | Any) -> pd.DataFrame:
    """Flatten classification_report.json into one row per file."""
    payload = json.loads(_as_bytes(raw))
    records = payload.get("records", [])
    if not records:
        return pd.DataFrame(
            columns=[
                "file_name", "file_path", "file_type", "classification",
                "risk_score", "cnic_count", "iban_count", "credit_card_count",
                "email_count", "phone_count", "salary_indicator",
            ]
        )

    rows: list[dict[str, Any]] = []
    for rec in records:
        det = rec.get("detections") or {}
        salary = det.get("salary_indicator")
        if isinstance(salary, list):
            salary_flag = "yes" if salary else "no"
        elif isinstance(salary, str):
            salary_flag = salary
        elif isinstance(salary, bool):
            salary_flag = "yes" if salary else "no"
        else:
            salary_flag = "no"

        row = {
            "file_name": rec.get("file_name"),
            "file_path": rec.get("file_path"),
            "file_type": rec.get("file_type"),
            "classification": rec.get("classification"),
            "risk_score": rec.get("risk_score", 0),
            "salary_indicator": salary_flag,
        }
        for key in DETECTION_KEYS:
            values = det.get(key) or []
            row[f"{key}_count"] = len(values) if isinstance(values, list) else 0
            row[f"{key}_values"] = values if isinstance(values, list) else []
        rows.append(row)

    df = pd.DataFrame(rows)
    if "classification" in df.columns:
        df["classification"] = pd.Categorical(
            df["classification"], categories=CLASSIFICATION_ORDER, ordered=True
        )
    return df


def load_classification_csv(raw: bytes | Any) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(_as_bytes(raw)))
    if "classification" in df.columns:
        df["classification"] = pd.Categorical(
            df["classification"], categories=CLASSIFICATION_ORDER, ordered=True
        )
    return df


def load_report(raw: bytes | Any, *, name_hint: str | None = None) -> pd.DataFrame:
    """Detect JSON vs CSV from content/filename and dispatch."""
    blob = _as_bytes(raw)
    looks_json = blob.lstrip().startswith(b"{")
    if name_hint and not looks_json:
        looks_json = name_hint.lower().endswith(".json")
    if looks_json:
        return load_classification_json(blob)
    return load_classification_csv(blob)


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "total_files": 0,
            "public": 0,
            "confidential": 0,
            "highly_confidential": 0,
            "peak_risk": 0,
            "avg_risk": 0.0,
            "total_detections": 0,
        }
    classification = df["classification"].astype(str)
    count_cols = [f"{k}_count" for k in DETECTION_KEYS if f"{k}_count" in df.columns]
    total_detections = int(df[count_cols].sum().sum()) if count_cols else 0
    return {
        "total_files": int(len(df)),
        "public": int((classification == "Public").sum()),
        "confidential": int((classification == "Confidential").sum()),
        "highly_confidential": int((classification == "Highly Confidential").sum()),
        "peak_risk": int(df["risk_score"].max() or 0),
        "avg_risk": float(df["risk_score"].mean() or 0.0),
        "total_detections": total_detections,
    }
