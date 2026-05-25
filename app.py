"""Landing page — RPA dashboard briefing for bank IT-manager stakeholders.

Two sections: what each of the two bots does today, and the KYC rule
pack from `kyc_rules.md`.
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
    "A briefing for IT and risk teams: what each bot does today and the "
    "KYC rule pack they apply."
)

# =====================================================================
# Section 1 — The two bots
# =====================================================================
st.markdown("## 1. The bots running in this dashboard")

st.markdown(
    """
Both bots follow the same operational shape: **ingest files → process →
classify → write reports**. Different inputs and rule packs; the same
orchestration, the same audit posture, the same dashboard pages.
"""
)

_ONBOARDING_FLOW = """
digraph {
    rankdir=TB;
    bgcolor="transparent";
    node [fontname="Helvetica", fontsize=10, style="filled,rounded", shape=box];
    edge [fontname="Helvetica", fontsize=9, color="#6b7280"];

    email   [label="Gmail IMAP\\nsubject: ACCOUNT OPENING", fillcolor="#dbeafe"];
    ocr     [label="OCR\\nTesseract / Claude vision", fillcolor="#f3f4f6"];
    extract [label="Field extraction\\nID · Name (AR+EN) · DOB · expiry", fillcolor="#f3f4f6"];
    kyc     [label="KYC rules\\n5 checks", fillcolor="#f3f4f6"];
    sanc    [label="Sanctions screening", fillcolor="#f3f4f6"];
    decide  [label="Decision", fillcolor="#fef3c7", shape=diamond];

    approve [label="auto-approve", fillcolor="#16a34a", fontcolor="white"];
    review  [label="needs review", fillcolor="#d97706", fontcolor="white"];
    reject  [label="auto-reject",  fillcolor="#dc2626", fontcolor="white"];

    report  [label="report.csv\\n+ audit_log.json", fillcolor="#e0e7ff", shape=cylinder];

    email -> ocr -> extract -> kyc -> sanc -> decide;
    decide -> approve;
    decide -> review;
    decide -> reject;
    approve -> report;
    review  -> report;
    reject  -> report;
}
"""

_DLP_FLOW = """
digraph {
    rankdir=TB;
    bgcolor="transparent";
    node [fontname="Helvetica", fontsize=10, style="filled,rounded", shape=box];
    edge [fontname="Helvetica", fontsize=9, color="#6b7280"];

    src    [label="File-share / directory\\nrecursive walk", fillcolor="#dbeafe", shape=folder];
    read   [label="File readers\\nPDF · DOCX · XLSX · CSV · TXT", fillcolor="#f3f4f6"];
    det    [label="Regex detectors\\nSaudi ID · IBAN · card · email · phone · salary", fillcolor="#f3f4f6"];
    score  [label="Risk scoring\\n+ classification", fillcolor="#fef3c7", shape=diamond];

    pub    [label="Public",              fillcolor="#2ca02c", fontcolor="white"];
    conf   [label="Confidential",        fillcolor="#ff7f0e", fontcolor="white"];
    hc     [label="Highly Confidential", fillcolor="#d62728", fontcolor="white"];

    report [label="report.csv\\n+ audit_log.json", fillcolor="#e0e7ff", shape=cylinder];

    src -> read -> det -> score;
    score -> pub;
    score -> conf;
    score -> hc;
    pub  -> report;
    conf -> report;
    hc   -> report;
}
"""

c1, c2 = st.columns(2)

with c1:
    st.markdown("#### Account Opening Bot")
    st.graphviz_chart(_ONBOARDING_FLOW, use_container_width=True)
    st.markdown(
        """
**Ingests** — Gmail inbox via IMAP. Watches for unread emails with the
subject `ACCOUNT OPENING` and an attached ID document (Saudi national
ID or Iqama; image or PDF).

**Processes** —

1. Downloads the email attachment
2. Runs OCR (Tesseract or Claude vision) over the image
3. Extracts ID number, name (Arabic + English), DOB, expiry, nationality
4. Runs the KYC rule pack — ID format, checksum, age ≥ 18, name presence, sanctions
5. Issues a decision: **auto-approve** / **needs review** / **auto-reject**

**Reports** — `report.csv` (queue, one row per application) plus
`audit_log.json` (event timeline). Visible on **Cloud Runs** under the
*Onboarding Helper* process.
"""
    )

with c2:
    st.markdown("#### DLP Discovery Bot")
    st.graphviz_chart(_DLP_FLOW, use_container_width=True)
    st.markdown(
        """
**Ingests** — Email attachments or a target directory tree (file share,
local mount). Walks recursively and reads every supported file (PDF,
DOCX, XLSX, CSV, plaintext).

**Processes** —

1. Reads each file's text content
2. Runs regex detectors for sensitive data — Saudi ID, IBAN, credit card, email, phone, salary indicators
3. Counts matches per file
4. Scores risk and classifies: **Public** / **Confidential** / **Highly Confidential**

**Reports** — `report.csv` and `report.json` (per-file counts and
matches) plus `audit_log.json`. Visible on **Cloud Runs** under the
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
# Section 2 — KYC rules (rendered from kyc_rules.md so the file stays
# the single source of truth)
# =====================================================================
_kyc_doc = Path(__file__).parent / "kyc_rules.md"
if _kyc_doc.exists():
    _content = _kyc_doc.read_text(encoding="utf-8")
    # Demote every heading by one level so the file's top H1 becomes an
    # H2 that lines up with the other section headers on this page.
    _content = re.sub(r"^(#{1,5}) ", r"#\1 ", _content, flags=re.MULTILINE)
    # Add the section number to the (now H2) title.
    _content = _content.replace("## KYC Rules", "## 2. KYC rules", 1)
    st.markdown(_content)
else:
    st.caption("`kyc_rules.md` not found at the project root.")
