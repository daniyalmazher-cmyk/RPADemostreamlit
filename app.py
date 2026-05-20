"""Landing page — RPA dashboard briefing for bank IT-manager stakeholders.

Four sections: stack + security posture mapped to KSA/Gulf governance,
how Robocorp orchestrates work (entities + run lifecycle), what each of
the two bots does today, and the KYC rule pack from `kyc_rules.md`.
"""

import re
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="RPA Dashboard",
    page_icon="bank",
    layout="wide",
)
st.logo("logo.png", size="large")

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
about cloud vendor — both bots can run on-prem inside your VPC if that's
the deployment model you need.
"""
)

# ----- 1A: Stack -----
st.markdown("### The stack — what each layer is and why we picked it")

st.markdown(
    """
##### Python 3.12 (the language)
Python is the world's most-used programming language for automation, data
processing, and AI. Easy to read, huge library ecosystem, widely known
inside bank IT departments. We pin to version 3.12 in a config file so
every run uses the exact same Python — no "works on my laptop but not on
the server" surprises.

##### Robocorp / Sema4.ai (the RPA platform)
**RPA** stands for *Robotic Process Automation* — software bots that do
the repetitive computer work humans used to do (read emails, fill forms,
extract data, copy between systems). **Robocorp** is an open-source RPA
framework — recently rebranded **Sema4.ai**. Two pieces:

- A Python library for writing bots.
- A web console called **Control Room** that schedules and runs them.

"Open-source" matters for a bank: you can read the source, host it
yourself, audit what it does, and there's no vendor lock-in on the
runtime — the bots are just plain Python.

##### `rcc` + `conda.yaml` (environment management)
A "Python environment" is the specific combination of Python version and
libraries a program needs. `conda.yaml` is a config file that lists
exactly what's needed (Python 3.12, Tesseract 5.x, pandas, etc.). `rcc`
is the command-line tool that reads that file and builds a fresh,
isolated environment for each run. We call this **hermetic** — the bot
can't accidentally pick up a different library version from whatever
else is installed on the host. Same code + same `conda.yaml` = the same
behaviour every time. This matters for audit and change control: there's
no ambiguity about what version of what library produced a given output.

##### Tesseract 5.x / Claude vision (OCR engines)
**OCR** = *Optical Character Recognition*: extracting text from images
or scanned documents. We support two engines, swapped by changing one
environment variable:

- **Tesseract 5.x** — the long-running open-source OCR engine (started
  at HP in the 80s, now maintained by Google). Runs entirely offline,
  free, decent on English, weaker on Arabic and stylised fonts.
- **Claude vision** — Anthropic's multimodal AI. Runs in the cloud,
  costs money per page, materially better on Arabic and noisy/skewed
  documents.

You can start with Tesseract (zero per-document cost) and upgrade to
Claude only on the documents where accuracy isn't good enough.

##### IMAP / Gmail App Password / Microsoft Graph (email intake)
**IMAP** = *Internet Message Access Protocol*: the standard way for an
application to read messages in a mailbox (different from SMTP, which is
for sending). **Gmail App Password** is a Google feature: instead of
giving the bot your real Gmail login, you generate a 16-character
single-purpose password that only works for that one app and can be
revoked at any time without changing the user's actual password. In a
bank you'd typically use **Microsoft Graph API** (the modern API in
front of Exchange Online) for the same purpose — scoped to the specific
mailbox, audited centrally.

##### Local filesystem / S3 / Azure Blob (output storage)
Today the bot writes its outputs (CSV reports, per-application JSON,
audit logs) to the local disk on whichever worker ran it. In production
you'd send them to **object storage**: **S3** is Amazon's, **Azure
Blob** is Microsoft's, **MinIO** is a popular on-prem alternative.
Object storage gives you retention policies (automatic deletion after N
days), encryption at rest, immutable buckets for legal hold, and easy
integration into the rest of your data pipeline.

##### Robocorp Vault (secrets management)
A **vault** is an encrypted store for secrets — passwords, API keys,
certificates. The bot never sees a raw credentials file. At run time it
asks the Vault by name ("get me `gmail_app_password`"), the Vault
decrypts the value, hands it over for the duration of that one run, and
it's never persisted to disk. **Encrypted at rest** means even if
someone got hold of the underlying storage, they'd only see ciphertext.
Rotating a password is one click in the Vault UI — no redeploy.

##### Streamlit + httpx (this dashboard)
**Streamlit** is a Python library for building data dashboards quickly
— every chart, table, and button on these pages is a few lines of
Python. **httpx** is a Python library for making HTTPS calls, which is
how this dashboard talks to Control Room's REST API to fetch run
history and download artifact files. This dashboard is **read-only**
against Control Room except for the single "trigger a run" button on
the Trigger page.
"""
)

# ----- 1B: Governance -----
st.markdown("### Governance — what the acronyms mean and what they require")

st.markdown(
    """
##### SAMA CSF — Saudi Central Bank Cyber Security Framework
**SAMA** stands for *Saudi Arabian Monetary Authority* — the kingdom's
central bank (now formally called the Saudi Central Bank, but everyone
still says SAMA). The **CSF** is its mandatory cyber security framework
for every SAMA-regulated entity: banks, insurers, finance companies,
fintechs operating in the kingdom. Covers cyber governance, identity, asset
management, third-party risk, incident response. Audited annually.
Non-compliance carries fines, license restrictions, and in serious
cases license revocation.

##### NCA ECC — National Cybersecurity Authority Essential Cybersecurity Controls
The **NCA** is the kingdom-wide cybersecurity regulator (broader scope
than SAMA — applies to government entities, critical national
infrastructure, and large private firms). The **ECC** is its baseline
control set: 114 controls across 5 domains (governance, defence,
resilience, third-party, industrial control). Mandatory for anyone
designated critical infrastructure, which banks are.

##### PDPL — Personal Data Protection Law
The kingdom's data protection law, enforced by the Saudi Data & AI Authority
(**SDAIA**). Roughly equivalent in spirit to Europe's GDPR. Defines what
counts as personal data, requires lawful basis for processing, mandates
breach notification, restricts cross-border data transfer. Fully in
force since 2024 with material monetary penalties for violations.

##### Data residency
The principle that customer data — especially Saudi nationals' personal
data — must be physically stored and processed *inside the kingdom*, or
in countries with an adequate-protection agreement. Cross-border
transfer otherwise requires explicit consent or a regulatory exception.
**How we address it:** the Robocorp Worker runs inside your VPC, so
customer PII, ID images, and OCR text never cross the border.

##### SIEM (Splunk / QRadar / Sentinel)
**SIEM** = *Security Information and Event Management*. A central
system that collects log data from across your IT estate (servers,
applications, network gear, bots like this one) and runs correlation
rules on it to detect suspicious activity. The three most common at
large banks: **Splunk** (vendor: Splunk Inc.), **QRadar** (IBM),
**Microsoft Sentinel**. Our audit logs are JSON — they drop into any of
them without transformation.

##### RBAC — Role-Based Access Control
Instead of giving each individual user direct permissions on each
resource, you define **roles** ("operator", "approver", "auditor") and
assign users to roles. Less to manage, easier to audit, and matches how
banks already think about segregation of duties. Control Room enforces
RBAC natively — who can trigger a process, who can view a run, who can
read or rotate secrets, all configurable.

##### mTLS — Mutual TLS
**TLS** is what makes a URL begin with `https://` — the network
connection is encrypted, and the server proves its identity with a
certificate. **Mutual TLS** means the client *also* proves its identity
with its own certificate. So when a Robocorp Worker calls Control Room
(or vice versa), both sides verify each other before any data flows.
Prevents impersonation attacks.

##### Change control
A formal process for tracking changes to production systems — who
changed what, when, with what approval. Required by every banking
regulator. **How we address it:** every bot version lives in git with a
signed tag, the environment is pinned in `conda.yaml`, and every run is
reproducible from that combination. You can always answer "what version
of what produced this output."

##### CBS — Core Banking System
The system of record for customer accounts, balances, transactions.
Major vendors: **Finacle** (Infosys), **Flexcube** (Oracle), **T24**
(Temenos). When the Account Opening bot decides "approve" in
production, it would call your CBS API to create the customer record —
that's the main integration seam left open in this demo.

##### VPC — Virtual Private Cloud
A logically isolated network inside a cloud provider (AWS, Azure, GCP)
that only your organisation can reach — equivalent to having your own
datacenter on someone else's hardware. Running the Robocorp Worker
inside your VPC means it's network-reachable only from inside the
bank's perimeter, with no public ingress.

##### PII — Personally Identifiable Information
Any data that identifies an individual: national ID number, name,
address, date of birth, account number. PDPL and SAMA both regulate how
PII is collected, stored, transmitted, and disposed of. The OCR output
from an ID card is, by definition, PII — which is why it never leaves
the worker's local filesystem and why the audit log doesn't contain
full text dumps.
"""
)

# ----- 1C: Summary mapping (quick reference) -----
st.markdown("### Quick mapping — concern ↔ control (summary)")
st.markdown(
    """
| Regulatory concern | How the stack addresses it |
|---|---|
| **Data residency** (SAMA CSF, PDPL) | Worker runs inside the bank's network. PII never leaves the perimeter. |
| **Secrets handling** (SAMA CSF, NCA ECC) | All credentials in Robocorp Vault. Rotatable without redeploy. |
| **Audit trail** (SAMA CSF, NCA ECC) | Per-run append-only `audit_log.json` (immutable after `finish()`). SIEM-ready JSON. |
| **Access control** (NCA ECC) | Control Room RBAC: who can trigger, view, rotate. |
| **Change control** (SAMA CSF) | Git-tagged versions + pinned `conda.yaml`. Reproducible runs. |
| **Transport security** | mTLS between Control Room and Worker. Allowlisted egress to Exchange / CBS / screening. |
| **Data classification** (PDPL, NCA ECC) | The DLP bot itself is a compliance control — finds sensitive data at rest. |
| **Vendor lock-in** | Open-source framework. Self-hostable Control Room. Plain-Python bot code. |
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

st.divider()

# =====================================================================
# Section 4 — KYC rules (rendered from kyc_rules.md so the file stays
# the single source of truth)
# =====================================================================
_kyc_doc = Path(__file__).parent / "kyc_rules.md"
if _kyc_doc.exists():
    _content = _kyc_doc.read_text(encoding="utf-8")
    # Demote every heading by one level so the file's top H1 becomes an
    # H2 that lines up with the other section headers on this page.
    _content = re.sub(r"^(#{1,5}) ", r"#\1 ", _content, flags=re.MULTILINE)
    # Add the section number to the (now H2) title.
    _content = _content.replace("## KYC Rules", "## 4. KYC rules", 1)
    st.markdown(_content)
else:
    st.caption("`kyc_rules.md` not found at the project root.")
