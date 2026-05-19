"""Entry point for the DLP Discovery Dashboard."""

import streamlit as st

st.set_page_config(
    page_title="DLP Discovery Dashboard",
    page_icon="shield",
    layout="wide",
)

st.title("Sensitive Data Discovery & Classification")
st.write(
    "Browse Control Room runs of the discovery bot or trigger a new scan. "
    "Pick a page from the sidebar to get started."
)

robocorp_ok = "robocorp" in st.secrets and st.secrets["robocorp"].get("api_key")

with st.sidebar:
    st.markdown("### Control Room")
    if robocorp_ok:
        st.success("API key configured")
        st.caption(f"Base: `{st.secrets['robocorp']['api_base']}`")
        st.caption(f"Workspace: `{st.secrets['robocorp']['workspace_id']}`")
        if st.secrets["robocorp"].get("process_id"):
            st.caption(f"Default process: `{st.secrets['robocorp']['process_id']}`")
    else:
        st.warning(
            "No Robocorp credentials configured. Add them to "
            "`.streamlit/secrets.toml` under `[robocorp]`."
        )

st.markdown("### What you can do")
st.markdown(
    """
- **Cloud Runs** — list recent runs of the discovery process, download artifacts,
  and render the same charts as the desktop bot.
- **Trigger** — kick off a new scan in Control Room, watch it run, and view the
  fresh report inline once it finishes.
"""
)

st.markdown("### About the bot")
st.markdown(
    """
The bot runs in Robocorp Control Room and scans files for sensitive fintech
data (CNIC, IBAN, credit card, email, phone, salary). Each run writes three
artifacts:

- `classification_report.csv` — one row per scanned file (counts only)
- `classification_report.json` — same content plus the matched values
- `audit_log.json` — run-level event timeline

This dashboard consumes those artifacts via the Control Room API.
"""
)
