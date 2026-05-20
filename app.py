"""Landing page — RPA dashboard briefing for bank IT-manager stakeholders.

Three sections: stack + security posture mapped to KSA/Gulf governance,
how Robocorp orchestrates work (entities + run lifecycle), and what each
of the two bots does today.
"""

import streamlit as st

st.set_page_config(
    page_title="RPA Dashboard",
    page_icon="bank",
    layout="wide",
)

st.title("RPA for Banking Operations")
st.caption(
    "A briefing for IT and risk teams: the stack we run, how Robocorp "
    "orchestrates work, and what each bot does today."
)

# =====================================================================
# Section 1 — Stack & Security
# =====================================================================
st.markdown("## 1. Stack & security posture")

st.markdown(
    """
The stack is open-source where it matters and pluggable everywhere your
security team gets to choose the provider. Nothing here is opinionated
about cloud vendor — both bots run on-prem inside your VPC if that's the
deployment model you need.
"""
)

st.markdown("#### Stack")
st.markdown(
    """
| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.12 | Pinned in `conda.yaml`, reproducible per-run |
| RPA platform | Robocorp / Sema4.ai | Open-source robot framework + Control Room orchestrator |
| Environment | `rcc` + `conda.yaml` | Hermetic env materialized per run, no system Python |
| OCR | Tesseract 5.x (offline) / Claude vision (optional) | Engine selected via `OCR_ENGINE` env var |
| Email intake | IMAP (Gmail App Password today; Microsoft Graph in production) | Scoped App Passwords, never shared-mailbox credentials |
| Storage | Local filesystem in the demo; pluggable to S3 / Azure Blob / on-prem object store | Defined per-task in `robot.yaml` |
| Secrets | Robocorp Vault | Encrypted at rest, rotatable, RBAC-controlled |
| Dashboard (this UI) | Streamlit + httpx | Read-only view over the Control Room REST API |
"""
)

st.markdown("#### Posture mapped to KSA / Gulf governance")
st.markdown(
    """
| Regulatory concern | How the stack addresses it |
|---|---|
| **Data residency** (SAMA CSF, PDPL) | Robocorp Worker runs inside the bank's network. Customer PII, ID images, OCR text never leave the bank's perimeter. |
| **Secrets handling** (SAMA CSF, NCA ECC) | All credentials in Robocorp Vault — never in repo, never in env files. Rotatable from the Vault UI without redeploy. |
| **Audit trail** (SAMA CSF, NCA ECC) | Per-run append-only `audit_log.json` with UTC timestamps for every stage transition. Immutable after `finish()`. Drops directly into SIEM (Splunk / QRadar / Sentinel). |
| **Access control** (NCA ECC) | Control Room enforces role-based access — who can trigger runs, who can view artifacts, who can rotate secrets. |
| **Change control** (SAMA CSF) | Bot versions are git-tagged + pinned in `conda.yaml`. The same version produces deterministic output. |
| **Transport security** | All Control Room ↔ Worker traffic is mTLS. Worker calls out only to bank-allowlisted endpoints (Exchange, CBS, screening provider). |
| **Data classification** (PDPL, NCA ECC) | The DLP Discovery bot itself is a compliance control — surfaces sensitive data at rest for risk teams. |
| **Vendor lock-in** | Robot framework is open-source. Control Room is self-hostable. Bot code is plain Python — portable to any orchestrator if Robocorp is dropped. |
"""
)

st.divider()

# =====================================================================
# Section 2 — Robocorp architecture
# =====================================================================
st.markdown("## 2. Robocorp — what it is and how it orchestrates work")

st.markdown(
    """
Robocorp (recently Sema4.ai) is an open-source RPA platform with two
distinct planes:

- **`rcc`** — a command-line tool that builds a hermetic Python
  environment from `conda.yaml` and runs the bot. Same env on every
  machine, same env every time.
- **Control Room** — the orchestration plane. Schedules runs, holds
  secrets, dispatches work to workers, stores artifacts, exposes a REST
  API and a web UI. Available as SaaS or self-hosted on your infra.
"""
)

st.markdown("#### Core entities")
st.markdown(
    """
| Entity | What it is | Example in this demo |
|---|---|---|
| **Workspace** | Top-level tenancy boundary. All bots, runs, users, secrets, RBAC scoped to one workspace. | `03219a3f-…` (the bank demo workspace) |
| **Process** | A named automation with an entry point, schedule, and work-item queue. The thing a person triggers. | "Onboarding Helper", "Discovery Bot" |
| **Task** | The smallest unit of bot work, defined in `robot.yaml`. A process maps to one or more tasks. | `process_inbox`, `extract_and_classify` |
| **Process Run** | One execution of a process. Has a state (`new` → `in_progress` → `completed` / `unresolved`), timestamps, work items, artifacts. | A single triggered run, e.g. `b3ba9063-…` |
| **Step Run** | A process run is composed of step runs (one per task). **Artifacts hang off step runs, not process runs** — important when you call the API. | The step run that produced `applications.csv` |
| **Worker** | The compute that actually executes the bot. Robocorp Cloud worker, a self-hosted Linux VM in your VPC, or a Windows worker in your data center. Picked by labels. | Linux worker (x86) |
| **Work Item** | A unit of input passed to a run. A process can fan out across N work items in parallel. | One email = one work item |
| **Artifact** | Any file the bot writes — CSV, JSON, logs, images, the full `log.html`. Stored under a retention policy, downloadable via API or the UI. | `applications.csv`, `audit_log.json`, `log.html` |
| **Vault** | Encrypted secret store. Bots fetch credentials at run time, never persisted to disk. | Gmail App Password, sanctions-API key |
| **Schedule** | Cron-like configuration that triggers process runs automatically. | "Every 5 minutes — poll the onboarding inbox" |
"""
)

st.markdown("#### Lifecycle of one run")
st.markdown(
    """
1. **Trigger arrives** — from a schedule, an API call, the Control Room UI button, or a queued work item.
2. **Control Room dispatches** — picks an available worker matching the process's labels and hands off the work items.
3. **Worker provisions** — pulls the robot package, runs `rcc` to materialize the conda env. ~5–10 seconds first time, cached afterwards.
4. **Bot executes** — fetches secrets from Vault, runs the task, produces logs and artifacts. Audit events are appended throughout.
5. **Artifacts upload** — each task's output streams back to Control Room as it's written.
6. **Audit log finalizes** — `audit_log.json` is closed and becomes immutable.
7. **Run terminates** — state set, artifacts persisted under the retention policy.
8. **Downstream consumers wake up** — CBS API call, dashboard refresh, SIEM ingestion, email alert to the ops queue.
"""
)

st.divider()

# =====================================================================
# Section 3 — The two bots
# =====================================================================
st.markdown("## 3. The bots running in this dashboard")

st.markdown(
    """
Both bots follow the same operational shape: **ingest files → process →
classify → write reports**. Different inputs and rule packs; the same
orchestration, the same audit posture, the same dashboard pages.
"""
)

c1, c2 = st.columns(2)

with c1:
    st.markdown("#### Account Opening Bot")
    st.markdown(
        """
**Ingests** — Gmail inbox via IMAP. Watches for unread emails with the
subject `ACCOUNT OPENING` and an attached ID document (Saudi national
ID or Iqama; image or PDF).

**Processes** —

1. Downloads the email attachment
2. Runs OCR (Tesseract or Claude vision) over the image
3. Extracts ID number, name (Arabic + English), DOB, expiry, nationality
4. Runs the KYC rule pack — ID format, checksum, expiry, age ≥ 18, name presence, sanctions
5. Issues a decision: **auto-approve** / **needs review** / **auto-reject**

**Reports** — `applications.csv` (queue, one row per application) plus
`audit_log.json` (event timeline). Visible on **Cloud Runs** under the
*Onboarding Helper* process.
"""
    )

with c2:
    st.markdown("#### DLP Discovery Bot")
    st.markdown(
        """
**Ingests** — Email attachments or a target directory tree (file share,
local mount). Walks recursively and reads every supported file (PDF,
DOCX, XLSX, CSV, plaintext).

**Processes** —

1. Reads each file's text content
2. Runs regex detectors for sensitive data — CNIC, IBAN, credit card, email, phone, salary indicators
3. Counts matches per file
4. Scores risk and classifies: **Public** / **Confidential** / **Highly Confidential**

**Reports** — `classification_report.csv` and `.json` (per-file counts
and matches) plus `audit_log.json`. Visible on **Cloud Runs** under the
discovery process.
"""
    )

st.markdown("#### Where to see them live")
st.markdown(
    """
- **Cloud Runs** — pick either process from the dropdown to browse historical runs. The page auto-detects whether the run is DLP-shaped or Account-Opening-shaped and renders the matching view.
- **Trigger** — kick off a fresh run of any process. Polls until completion, then shows the result inline.
"""
)

c1, c2 = st.columns(2)
with c1:
    st.page_link("pages/1_Cloud_Runs.py", label="Browse Cloud Runs")
with c2:
    st.page_link("pages/2_Trigger.py", label="Trigger a new run")
