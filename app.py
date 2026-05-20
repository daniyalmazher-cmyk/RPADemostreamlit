"""Architecture — landing page for the bank IT-manager demo.

Static briefing covering both RPA bots in the workspace, framed around
automating retail onboarding. Live run inspection lives on the Cloud Runs
and Trigger pages (sidebar).
"""

import streamlit as st

st.set_page_config(
    page_title="Architecture",
    page_icon="bank",
    layout="wide",
)

st.title("RPA for Banking Operations")
st.caption(
    "Automating onboarding, KYC, and compliance for retail banking — "
    "hosted on Robocorp Control Room, deployable inside your VPC, "
    "auditable end-to-end."
)

# --- Overview -----------------------------------------------------------

st.markdown(
    """
### What this dashboard is

A live demo of two production-shaped RPA bots running in Robocorp Control
Room. Both visible in this dashboard, both share the same operational
shell — vault-managed secrets, hermetic Python environments, immutable
per-run audit logs, RBAC, run history — so the marginal cost of adding a
third bot tomorrow is small.
"""
)

c1, c2 = st.columns(2)
with c1:
    st.markdown(
        """
**Account Opening Bot**

Email-driven retail account opening. Customer sends ID document → bot
extracts, validates, screens, decides. Built for KSA / GCC starting
position; the rule engine and document schema are pluggable per market.

*The headline bot for an onboarding automation pitch.*
"""
    )
with c2:
    st.markdown(
        """
**DLP Discovery Bot**

Scans internal document repositories for sensitive customer data
(national IDs, IBANs, card numbers, salary indicators) and classifies
files by risk. Useful for cloud-migration audits, file-share hygiene,
periodic compliance sweeps.

*The complementary compliance/risk story.*
"""
    )

st.divider()

# --- Bot 1: Account Opening --------------------------------------------

st.markdown("## Account Opening Bot")
st.markdown(
    """
**Business problem.** A customer emails their ID document (national ID
or Iqama) to a shared bank inbox. Today a person opens the email,
transcribes the ID number into the CBS, eyeballs the expiry date, and
keys in the name. Manual, slow, error-prone, doesn't scale at volume.

**What the bot does.** Picks up the email automatically, OCRs the
document (Arabic + English), parses the fields, runs the KYC rule pack,
screens against sanctions, and writes a decision: **auto-approve**,
**needs review**, or **auto-reject**. A human only ever sees the
*needs review* queue. Everything else — including OCR-misread rejects —
is handled without intervention.
"""
)

st.markdown("#### Pipeline")
st.markdown(
    """```
   ┌──────────────┐    ┌────────────┐    ┌────────────────┐    ┌──────────────┐    ┌────────────┐
   │ Gmail IMAP   │ →  │ OCR        │ →  │ Field          │ →  │ KYC rules    │ →  │ CSV +      │
   │ (UNSEEN +    │    │ Tesseract  │    │ extraction     │    │ + sanctions  │    │ per-app    │
   │ subject)     │    │ or Claude  │    │ (regex)        │    │ screening    │    │ JSON +     │
   └──────────────┘    └────────────┘    └────────────────┘    └──────────────┘    │ audit log  │
                                                                                    └────────────┘
```"""
)

st.markdown("#### KYC rules applied")
st.markdown(
    """
| Rule | Severity | What it checks |
|---|---|---|
| `id_format` | Blocking | 10 digits, leading 1 (Saudi national) or 2 (resident / Iqama) |
| `id_checksum` | Blocking | Modified-Luhn check digit on the ID number |
| `not_expired` | Blocking | Document expiry date is in the future |
| `age_18plus` | Blocking | Date of birth implies age ≥ 18 |
| `name_present` | Warning | Arabic and English name both extracted from OCR |
| `sanctions` | Blocking | No match against the screening list |
"""
)

st.markdown("#### Integration seams — today vs. production")
st.markdown(
    """
| Stage | Today (demo) | In production |
|---|---|---|
| Email intake | Gmail IMAP, App Password in Robocorp Vault | Your bank's Exchange / shared inbox via IMAP or Graph API |
| OCR | Tesseract (offline, free) or Claude vision (higher Arabic accuracy) | Your preferred OCR — same one-line swap, env-var selected |
| Sanctions screening | Stub hardcoded list | OFAC + UN + SAMA + PEP feed (Refinitiv / Dow Jones / etc.) |
| Decision routing | Writes CSV + per-app JSON to disk | Direct CBS API call to create/route the application |
| Document storage | Local files + image | S3 / object storage with retention policy |
| Identity verification | OCR only | + face-liveness + selfie-match parallel stage |
| Date formats | Gregorian only | Bidirectional Hijri ↔ Gregorian conversion |
"""
)

st.markdown(
    """
**Demo data path.** During this demo the bot runs against a test inbox
with five known applications: two clean approvals, one expired document,
one with an OCR-misread checksum (the bot correctly flags this as
*auto-reject* with a "likely OCR misread" explanation), and one
multi-failure stress case.
"""
)

st.divider()

# --- Bot 2: DLP --------------------------------------------------------

st.markdown("## DLP Discovery Bot")
st.markdown(
    """
**Business problem.** Banks accumulate sensitive customer data in
internal file shares — old loan applications, scanned KYC packs, HR
salary records. Before migrating to the cloud (or annually as part of
your DLP policy) you need to know **what is where**, classified by risk.

**What the bot does.** Walks a directory tree, opens every supported
file (PDF, DOCX, XLSX, CSV, plaintext), runs regex detectors for
fintech-sensitive data (CNIC / IBAN / credit card / email / phone /
salary indicators), and emits a per-file classification:
**Public** / **Confidential** / **Highly Confidential**.
"""
)

st.markdown("#### Pipeline")
st.markdown(
    """```
   ┌──────────────┐    ┌────────────┐    ┌────────────────┐    ┌──────────────┐    ┌────────────┐
   │ Directory    │ →  │ File       │ →  │ Detectors      │ →  │ Risk scoring │ →  │ CSV +      │
   │ walk         │    │ readers    │    │ (regex per     │    │ + classifi-  │    │ JSON +     │
   │ (recursive)  │    │ per type   │    │ data type)     │    │ cation       │    │ audit log  │
   └──────────────┘    └────────────┘    └────────────────┘    └──────────────┘    └────────────┘
```"""
)

st.markdown("#### Detectors")
st.markdown(
    """
Out of the box: CNIC, IBAN, credit card (Luhn-validated), email, phone,
salary indicators. Each detector is one regex + one validator function —
trivial to add bank-specific patterns (account number formats, internal
employee IDs, customer reference codes).
"""
)

st.divider()

# --- Operational posture ------------------------------------------------

st.markdown("## Operational posture")
st.markdown(
    """
This is the IT-managerial story. Both bots share the same
production-readiness shell:

- **Hermetic environments.** Every run starts in a fresh Python 3.12
  environment provisioned by `rcc` from a pinned `conda.yaml`. No system
  Python, no pip-on-prod, no "works on my machine."
- **Secrets in Robocorp Vault.** Email App Passwords, API tokens,
  screening-service credentials — never in the repo, never in env files.
  Bots fetch them at run time. Rotatable from the Vault UI without a
  redeploy.
- **Append-only audit logs.** Every run writes `audit_log.json` with the
  full event sequence: timestamps, stage transitions, per-application
  decisions. Immutable after `finish()`. Drops straight into a SIEM if
  you want.
- **Control Room hosting.** Either Robocorp Cloud (SaaS) or self-hosted
  Worker on a VM inside your VPC. Same artifact / RBAC / audit story
  either way — your security team picks the deployment model.
- **One-command run.** `rcc run` reproduces the environment and executes
  the bot. No build server, no Docker, no orchestrator setup needed.
"""
)

st.divider()

# --- How to use the dashboard ------------------------------------------

st.markdown("## How this dashboard is organized")
st.markdown(
    """
| Page | Use case |
|---|---|
| **Architecture** (this page) | Stakeholder briefing — what the bots do, how they integrate |
| **Cloud Runs** | Browse historical runs of either bot. Pick the process from the dropdown; the page auto-detects whether it's a DLP run or a KSA run and renders the matching view. |
| **Trigger** | Kick off a fresh run on demand, poll until completion, see the result inline. Also bot-agnostic. |

The Cloud Runs and Trigger pages dispatch based on the run's artifact
shape (`classification_report.*` → DLP view, `applications.csv` → KSA
view), so adding a third bot later only needs a new dispatch branch, not
a new page.
"""
)
