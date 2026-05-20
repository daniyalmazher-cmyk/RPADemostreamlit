"""Parse the second bot's `report.csv` output into a DataFrame.

The second bot emits a single artifact, `report.csv`, with one row per
processed application. The dispatcher in Cloud Runs / Trigger downloads
that file via the shared Control Room cache and calls `parse_csv_bytes`
here to materialise the DataFrame.
"""

from __future__ import annotations

import io

import pandas as pd

STATUS_ORDER = ["auto_approve", "needs_review", "auto_reject"]


def parse_csv_bytes(raw: bytes) -> pd.DataFrame:
    """Parse a UTF-8-BOM CSV (Excel-Arabic-safe) into a DataFrame."""
    df = pd.read_csv(
        io.BytesIO(raw), encoding="utf-8-sig", dtype=str, keep_default_na=False
    )
    if "status" in df.columns:
        df["status"] = pd.Categorical(
            df["status"], categories=STATUS_ORDER, ordered=True
        )
    return df
