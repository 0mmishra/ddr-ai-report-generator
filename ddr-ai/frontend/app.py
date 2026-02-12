"""Streamlit frontend for uploading reports and viewing DDR output."""

from __future__ import annotations

import os
import json
from typing import Any, Dict

import requests
import streamlit as st


# Backend URL from environment variable (used in deployment)
DEFAULT_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ===========================
# UI REPORT RENDERING
# ===========================

def _render_report(report: Dict[str, Any]) -> None:
    """Render structured DDR JSON in a readable UI layout."""

    st.subheader("Property Issue Summary")
    st.write(report.get("Property_Issue_Summary", "Not Available"))

    # ---------------------------
    # Area Observations
    # ---------------------------
    st.subheader("Area Wise Observations")
    area_data = report.get("Area_Wise_Observations", {})

    if isinstance(area_data, dict) and area_data:
        for area_name, details in area_data.items():
            st.markdown(f"### {area_name}")
            st.json(details)
    else:
        st.write("Not Available")

    # ---------------------------
    # Root Cause
    # ---------------------------
    st.subheader("Probable Root Cause")
    st.write(report.get("Probable_Root_Cause", "Not Available"))

    # ---------------------------
    # Severity
    # ---------------------------
    st.subheader("Severity Assessment")
    severity = report.get("Severity_Assessment", {})
    if isinstance(severity, dict):
        st.json(severity)
    else:
        st.write(severity)

    # ---------------------------
    # Recommended Actions
    # ---------------------------
    st.subheader("Recommended Actions")

    actions = report.get("Recommended_Actions", {})

    if isinstance(actions, dict):
        for category, items in actions.items():
            st.markdown(f"#### {category}")
            if isinstance(items, list):
                for item in items:
                    st.write(f"- {item}")
            else:
                st.write(items)

    elif isinstance(actions, str):
        # Sometimes model returns stringified JSON
        try:
            parsed = json.loads(actions)
            if isinstance(parsed, dict):
                for category, items in parsed.items():
                    st.markdown(f"#### {category}")
                    if isinstance(items, list):
                        for item in items:
                            st.write(f"- {item}")
                    else:
                        st.write(items)
            else:
                st.write(actions)
        except Exception:
            st.write(actions)
    else:
        st.write("Not Available")

    # ---------------------------
    # Risk Implications
    # ---------------------------
    st.subheader("Risk Implications")
    st.write(report.get("Risk_Implications", "Not Available"))

    # ---------------------------
    # Additional Notes
    # ---------------------------
    st.subheader("Additional Notes")
    st.write(report.get("Additional_Notes", "Not Available"))

    # ---------------------------
    # Missing Information
    # ---------------------------
    st.subheader("Missing / Unclear Information")
    missing_items = report.get("Missing_or_Unclear_Information", [])

    if isinstance(missing_items, list) and missing_items:
        for item in missing_items:
            st.write(f"- {item}")
    else:
        st.write("Not Available")


# ===========================
# DOWNLOAD DOCX
# ===========================

def _download_docx(file_name: str) -> tuple[bytes, str]:
    """Download generated DOCX from backend."""
    response = requests.get(
        f"{DEFAULT_BACKEND_URL}/download-report",
        params={"file_name": file_name},
        timeout=120,
    )
    response.raise_for_status()
    return response.content, file_name


# ===========================
# MAIN APP
# ===========================

def main() -> None:

    st.set_page_config(page_title="DDR AI Report Generator", layout="wide")
    st.title("DDR AI Report Generator")
    st.caption("Upload inspection and thermal PDFs to generate a structured DDR report.")

    # ---------------------------
    # Backend Health Check
    # ---------------------------
    try:
        health = requests.get(f"{DEFAULT_BACKEND_URL}/health", timeout=5)
        if health.status_code == 200:
            st.success("Backend Connected")
        else:
            st.warning("Backend reachable but unhealthy")
    except Exception:
        st.error("Backend not reachable. Please check deployment or URL.")

    # ---------------------------
    # File Upload
    # ---------------------------
    inspection_file = st.file_uploader("Upload Inspection Report (PDF)", type=["pdf"])
    thermal_file = st.file_uploader("Upload Thermal Report (PDF)", type=["pdf"])

    if st.button("Generate DDR", type="primary"):

        if inspection_file is None or thermal_file is None:
            st.error("Both PDF files are required.")
            return

        files = {
            "inspection_file": (
                inspection_file.name,
                inspection_file.getvalue(),
                "application/pdf",
            ),
            "thermal_file": (
                thermal_file.name,
                thermal_file.getvalue(),
                "application/pdf",
            ),
        }

        try:
            with st.spinner("Generating DDR Report..."):
                response = requests.post(
                    f"{DEFAULT_BACKEND_URL}/generate-ddr",
                    files=files,
                    timeout=300,
                )

            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                    error_detail = error_payload.get("detail", response.text)
                except ValueError:
                    error_detail = response.text

                if response.status_code == 429:
                    st.warning(
                        "OpenRouter quota or rate limit exceeded.\n\n"
                        f"Details: {error_detail}"
                    )
                else:
                    st.error(f"Server error ({response.status_code}): {error_detail}")
                return

            payload = response.json()

        except requests.RequestException as exc:
            st.error(f"Server error: {exc}")
            return

        except ValueError:
            st.error("Invalid JSON response from backend.")
            return

        # ---------------------------
        # Response Validation
        # ---------------------------
        report_data = payload.get("report_data")
        download_file = payload.get("download_file")

        if not isinstance(report_data, dict) or not isinstance(download_file, str):
            st.error("Backend response is missing expected fields.")
            return

        # ---------------------------
        # Display Report
        # ---------------------------
        st.success("DDR Generated Successfully")
        _render_report(report_data)

        # ---------------------------
        # Download DOCX
        # ---------------------------
        try:
            docx_bytes, file_name = _download_docx(download_file)

            st.download_button(
                label="Download DDR DOCX",
                data=docx_bytes,
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        except requests.RequestException as exc:
            st.error(f"Unable to download DOCX from backend: {exc}")


# ===========================
# ENTRYPOINT
# ===========================

if __name__ == "__main__":
    main()
