#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import streamlit as st

import streamlit as st

from paystub_analyzer.core import (
    as_float,
    extract_paystub_snapshot,
    format_money,
    list_paystub_files,
    select_latest_paystub,
    sum_state_ytd,
)
from paystub_analyzer.annual import (
    build_tax_filing_package,
    collect_annual_snapshots,
    package_to_markdown,
)
from paystub_analyzer.w2 import build_w2_template, compare_snapshot_to_w2
from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload

APP_SESSION_SCHEMA_VERSION = "2026-02-18-ui-contrast-and-ledger-v4"


def apply_theme() -> None:
    st.markdown(
        """
<style>
/* Import modern fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  /* Core Palette - High Contrast Light Theme */
  --bg-core: #ffffff;
  --bg-surface: #f8f9fa;
  --bg-subtle: #e9ecef;
  
  --text-primary: #1a1a1a;
  --text-secondary: #4a4a4a;
  --text-tertiary: #6c757d;
  
  --brand-primary: #0f5d75;
  --brand-primary-hover: #0b4a5d;
  --brand-secondary: #d97324;
  
  --border-subtle: #dee2e6;
  --border-strong: #ced4da;
}

/* Global resets for Streamlit containers */
[data-testid="stAppViewContainer"] {
  background-color: var(--bg-core);
  color: var(--text-primary);
  font-family: 'Inter', sans-serif;
}

[data-testid="stHeader"] {
  background-color: rgba(255, 255, 255, 0.95);
}

[data-testid="stSidebar"] {
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
}

/* Typographic enhancements */
h1, h2, h3, h4, h5, h6 {
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: -0.02em;
}

div[data-testid="stMarkdownContainer"] p, 
div[data-testid="stMarkdownContainer"] li {
  color: var(--text-primary);
  font-size: 1rem;
  line-height: 1.6;
}

.stCaption {
  color: var(--text-tertiary) !important;
}

/* Custom Card Component */
.metric-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  margin-bottom: 0.5rem;
}

.metric-card .label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.metric-card .value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--brand-primary);
  font-family: 'JetBrains Mono', monospace;
}

/* UI Elements Overrides */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
  background-color: var(--bg-core) !important;
  border-color: var(--border-strong) !important;
  color: var(--text-primary) !important;
}

div[data-baseweb="input"] input,
div[data-baseweb="select"] span,
div[data-baseweb="base-input"] input {
  color: var(--text-primary) !important;
  -webkit-text-fill-color: var(--text-primary) !important;
  caret-color: var(--brand-primary) !important;
}

/* Ensure labels are readable */
label[data-baseweb="checkbox"] span,
label[data-baseweb="radio"] span,
.stTextInput label,
.stNumberInput label,
.stSelectbox label,
.stFileUploader label {
  color: var(--text-primary) !important;
}

/* Fix for disabled inputs if needed */
div[data-baseweb="input"] input:disabled {
  color: var(--text-tertiary) !important;
  -webkit-text-fill-color: var(--text-tertiary) !important;
}

button[kind="primary"] {
  background-color: var(--brand-primary) !important;
  color: #ffffff !important;
  border: none !important;
  transition: background-color 0.15s ease-in-out;
}

button[kind="primary"]:hover {
  background-color: var(--brand-primary-hover) !important;
}

button[kind="secondary"] {
  background-color: var(--bg-surface) !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-strong) !important;
}

/* Status Pills */
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}
.status-match { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.status-mismatch { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.status-review { background: #fef9c3; color: #854d0e; border: 1px solid #fde047; }
.status-missing { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; }

/* Code blocks */
code {
  color: var(--brand-primary);
  background: var(--bg-subtle);
  padding: 0.1rem 0.3rem;
  border-radius: 4px;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def reset_session_if_schema_changed() -> None:
    existing = st.session_state.get("_app_schema_version")
    if existing == APP_SESSION_SCHEMA_VERSION:
        return
    keys_to_clear = [
        "snapshot",
        "annual_summary_preview",
        "analysis_scope",
        "annual_packet",
        "manual_w2_prefill_source",
        "manual_w2_states",
        "box1",
        "box2",
        "box3",
        "box4",
        "box5",
        "box6",
    ]
    for key in list(st.session_state.keys()):
        if key in keys_to_clear or key.startswith("box16_") or key.startswith("box17_"):
            st.session_state.pop(key, None)
    st.session_state["_app_schema_version"] = APP_SESSION_SCHEMA_VERSION


def metric_card(label: str, value: str) -> None:
    st.markdown(
        f"""
<div class="metric-card">
  <div class="label">{label}</div>
  <div class="value">{value}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def snapshot_to_dict(snapshot) -> dict[str, Any]:
    return {
        "file": snapshot.file,
        "pay_date": snapshot.pay_date,
        "gross_pay": {
            "this_period": as_float(snapshot.gross_pay.this_period),
            "ytd": as_float(snapshot.gross_pay.ytd),
            "evidence": snapshot.gross_pay.source_line,
        },
        "federal_income_tax": {
            "this_period": as_float(snapshot.federal_income_tax.this_period),
            "ytd": as_float(snapshot.federal_income_tax.ytd),
            "evidence": snapshot.federal_income_tax.source_line,
        },
        "social_security_tax": {
            "this_period": as_float(snapshot.social_security_tax.this_period),
            "ytd": as_float(snapshot.social_security_tax.ytd),
            "evidence": snapshot.social_security_tax.source_line,
        },
        "medicare_tax": {
            "this_period": as_float(snapshot.medicare_tax.this_period),
            "ytd": as_float(snapshot.medicare_tax.ytd),
            "evidence": snapshot.medicare_tax.source_line,
        },
        "k401_contrib": {
            "this_period": as_float(snapshot.k401_contrib.this_period),
            "ytd": as_float(snapshot.k401_contrib.ytd),
            "evidence": snapshot.k401_contrib.source_line,
        },
        "state_income_tax": {
            state: {
                "this_period": as_float(pair.this_period),
                "ytd": as_float(pair.ytd),
                "evidence": pair.source_line,
            }
            for state, pair in sorted(snapshot.state_income_tax.items())
        },
    }


def build_report_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Payslip vs W-2 Validation")
    lines.append("")
    lines.append(f"- Tax year: {payload['tax_year']}")
    lines.append(f"- Latest payslip used: `{payload['latest_paystub_file']}`")
    lines.append(f"- Latest payslip pay date: {payload['latest_pay_date']}")
    lines.append("")

    extracted = payload["extracted"]
    lines.append("## Extracted YTD Values")
    lines.append(f"- Gross pay: {extracted['gross_pay']['ytd']}")
    lines.append(f"- Federal tax: {extracted['federal_income_tax']['ytd']}")
    lines.append(f"- Social Security tax: {extracted['social_security_tax']['ytd']}")
    lines.append(f"- Medicare tax: {extracted['medicare_tax']['ytd']}")
    lines.append(f"- 401(k): {extracted['k401_contrib']['ytd']}")
    for state, row in sorted(extracted.get("state_income_tax", {}).items()):
        lines.append(f"- {state} state tax: {row['ytd']}")

    comparisons = payload.get("comparisons", [])
    if comparisons:
        lines.append("")
        lines.append("## Comparisons")
        for row in comparisons:
            lines.append(
                f"- {row['field']}: paystub={row['paystub']} w2={row['w2']} diff={row['difference']} status={row['status']}"
            )

    return "\n".join(lines) + "\n"


def as_number(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def show_notice(message: str, level: str = "success") -> None:
    st.markdown(
        f"<div class='notice notice-{level}'>{message}</div>",
        unsafe_allow_html=True,
    )


def state_values_from_w2_data(w2_data: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    if not w2_data:
        return result
    for row in w2_data.get("state_boxes", []):
        state = str(row.get("state", "")).strip().upper()
        if not state:
            continue
        result[state] = {
            "box16": as_number(row.get("box_16_state_wages_tips"), 0.0),
            "box17": as_number(row.get("box_17_state_income_tax"), 0.0),
        }
    return result


def ensure_manual_w2_defaults(states_for_form: list[str]) -> None:
    default = build_w2_template()
    st.session_state.setdefault("box1", as_number(default["box_1_wages_tips_other_comp"], 0.0))
    st.session_state.setdefault("box2", as_number(default["box_2_federal_income_tax_withheld"], 0.0))
    st.session_state.setdefault("box3", as_number(default["box_3_social_security_wages"], 0.0))
    st.session_state.setdefault("box4", as_number(default["box_4_social_security_tax_withheld"], 0.0))
    st.session_state.setdefault("box5", as_number(default["box_5_medicare_wages_and_tips"], 0.0))
    st.session_state.setdefault("box6", as_number(default["box_6_medicare_tax_withheld"], 0.0))
    for state in states_for_form:
        st.session_state.setdefault(f"box16_{state}", 0.0)
        st.session_state.setdefault(f"box17_{state}", 0.0)


def sync_manual_w2_from_upload(
    uploaded_w2_data: dict[str, Any] | None,
    states_from_snapshot: list[str],
    source_tag: str | None,
) -> None:
    if not uploaded_w2_data or source_tag is None:
        return
    if st.session_state.get("manual_w2_prefill_source") == source_tag:
        return

    uploaded_states = state_values_from_w2_data(uploaded_w2_data)
    form_states = sorted(set(states_from_snapshot) | set(uploaded_states.keys()))
    if not form_states:
        form_states = ["VA"]
    st.session_state["manual_w2_states"] = form_states
    ensure_manual_w2_defaults(form_states)

    st.session_state["box1"] = as_number(uploaded_w2_data.get("box_1_wages_tips_other_comp"), st.session_state["box1"])
    st.session_state["box2"] = as_number(
        uploaded_w2_data.get("box_2_federal_income_tax_withheld"), st.session_state["box2"]
    )
    st.session_state["box3"] = as_number(
        uploaded_w2_data.get("box_3_social_security_wages"), st.session_state["box3"]
    )
    st.session_state["box4"] = as_number(
        uploaded_w2_data.get("box_4_social_security_tax_withheld"), st.session_state["box4"]
    )
    st.session_state["box5"] = as_number(
        uploaded_w2_data.get("box_5_medicare_wages_and_tips"), st.session_state["box5"]
    )
    st.session_state["box6"] = as_number(
        uploaded_w2_data.get("box_6_medicare_tax_withheld"), st.session_state["box6"]
    )

    for state in form_states:
        state_row = uploaded_states.get(state)
        if state_row:
            st.session_state[f"box16_{state}"] = state_row["box16"]
            st.session_state[f"box17_{state}"] = state_row["box17"]

    st.session_state["manual_w2_prefill_source"] = source_tag


def build_manual_w2(snapshot, tax_year: int) -> dict[str, Any]:
    states_from_snapshot = sorted(snapshot.state_income_tax.keys()) or ["VA"]
    prior_states = st.session_state.get("manual_w2_states", [])
    states_for_form = sorted(set(states_from_snapshot) | set(prior_states))
    if not states_for_form:
        states_for_form = ["VA"]
    st.session_state["manual_w2_states"] = states_for_form
    ensure_manual_w2_defaults(states_for_form)

    st.subheader("W-2 Inputs")
    st.caption("Enter your W-2 box values. Use cents for exact matching.")

    c1, c2 = st.columns(2)
    with c1:
        box1 = st.number_input("Box 1 wages", min_value=0.0, step=0.01, key="box1")
        box2 = st.number_input("Box 2 federal tax", min_value=0.0, step=0.01, key="box2")
        box4 = st.number_input("Box 4 Social Security tax", min_value=0.0, step=0.01, key="box4")
    with c2:
        box3 = st.number_input("Box 3 Social Security wages", min_value=0.0, step=0.01, key="box3")
        box5 = st.number_input("Box 5 Medicare wages", min_value=0.0, step=0.01, key="box5")
        box6 = st.number_input("Box 6 Medicare tax", min_value=0.0, step=0.01, key="box6")

    st.markdown("#### State Boxes")
    state_boxes = []
    for state in st.session_state.get("manual_w2_states", states_for_form):
        s1, s2 = st.columns(2)
        with s1:
            box16 = st.number_input(f"{state} Box 16 wages", min_value=0.0, step=0.01, key=f"box16_{state}")
        with s2:
            box17 = st.number_input(f"{state} Box 17 tax", min_value=0.0, step=0.01, key=f"box17_{state}")
        state_boxes.append(
            {
                "state": state,
                "box_16_state_wages_tips": box16,
                "box_17_state_income_tax": box17,
            }
        )

    return {
        "tax_year": tax_year,
        "box_1_wages_tips_other_comp": box1,
        "box_2_federal_income_tax_withheld": box2,
        "box_3_social_security_wages": box3,
        "box_4_social_security_tax_withheld": box4,
        "box_5_medicare_wages_and_tips": box5,
        "box_6_medicare_tax_withheld": box6,
        "state_boxes": state_boxes,
    }


def status_pill(status: str) -> str:
    if status == "match":
        klass = "status-match"
    elif status == "mismatch":
        klass = "status-mismatch"
    elif status == "review_needed":
        klass = "status-review"
    else:
        klass = "status-missing"
    return f"<span class='status-pill {klass}'>{status}</span>"


def ledger_to_csv(ledger: list[dict[str, Any]]) -> str:
    if not ledger:
        return ""
    buffer = io.StringIO()
    fieldnames = [
        "pay_date",
        "file",
        "gross_pay_this_period",
        "gross_pay_ytd",
        "federal_tax_this_period",
        "federal_tax_ytd",
        "social_security_tax_this_period",
        "social_security_tax_ytd",
        "medicare_tax_this_period",
        "medicare_tax_ytd",
        "state_tax_this_period_total",
        "state_tax_ytd_total",
        "state_tax_this_period_by_state",
        "state_tax_ytd_by_state",
        "ytd_verification",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in ledger:
        csv_row = dict(row)
        csv_row["state_tax_this_period_by_state"] = json.dumps(
            csv_row["state_tax_this_period_by_state"], sort_keys=True
        )
        csv_row["state_tax_ytd_by_state"] = json.dumps(
            csv_row["state_tax_ytd_by_state"], sort_keys=True
        )
        writer.writerow(csv_row)
    return buffer.getvalue()


def main() -> None:
    st.set_page_config(page_title="Paystub Truth Check", page_icon="📄", layout="wide")
    reset_session_if_schema_changed()
    apply_theme()

    st.markdown("# Paystub Truth Check")
    st.markdown("Cross-verify latest paystub YTD values against your W-2 with evidence lines.")

    with st.sidebar:
        st.header("Run Settings")
        paystubs_dir = Path(st.text_input("Paystubs directory", value="pay_statements"))
        year = st.number_input("Tax year", min_value=2000, max_value=2100, value=2025, step=1)
        render_scale = st.slider("OCR render scale", min_value=2.0, max_value=4.0, value=2.8, step=0.1)
        tolerance = Decimal(str(st.number_input("Comparison tolerance", min_value=0.0, value=0.01, step=0.01)))

    files = list_paystub_files(paystubs_dir, int(year))
    if not files:
        st.error(f"No PDFs found in `{paystubs_dir}` for year `{year}`.")
        return

    latest_file, latest_date = select_latest_paystub(files)
    analysis_scope = st.radio(
        "Analysis Scope",
        options=["Single payslip", "All payslips in year"],
        horizontal=True,
    )

    selected = str(latest_file)
    if analysis_scope == "Single payslip":
        selected = st.selectbox(
            "Select payslip to extract",
            options=[str(path) for path in files],
            index=[str(path) for path in files].index(str(latest_file)),
        )
    else:
        st.caption(
            "Year mode will process every payslip in this folder/year and show a full-year summary."
        )

    if st.button("Extract Values", type="primary"):
        if analysis_scope == "All payslips in year":
            annual_snapshots = collect_annual_snapshots(
                paystubs_dir=paystubs_dir,
                year=int(year),
                render_scale=render_scale,
                psm=6,
            )
            if not annual_snapshots:
                st.error("No paystubs found for full-year analysis.")
                return
            snapshot = annual_snapshots[-1]
            annual_summary = build_tax_filing_package(
                tax_year=int(year),
                snapshots=annual_snapshots,
                tolerance=tolerance,
                w2_data=None,
            )
            st.session_state["snapshot"] = snapshot
            st.session_state["annual_summary_preview"] = annual_summary
            st.session_state["analysis_scope"] = "all_year"
        else:
            snapshot = extract_paystub_snapshot(Path(selected), render_scale=render_scale)
            st.session_state["snapshot"] = snapshot
            st.session_state.pop("annual_summary_preview", None)
            st.session_state["analysis_scope"] = "single"

    snapshot = st.session_state.get("snapshot")
    if snapshot is None:
        st.info("Click 'Extract Values' to begin.")
        return

    active_scope = st.session_state.get("analysis_scope", "single")
    extracted = snapshot_to_dict(snapshot)
    state_total = sum_state_ytd(snapshot.state_income_tax)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Federal Tax YTD", format_money(snapshot.federal_income_tax.ytd))
    with m2:
        metric_card("State Tax YTD (Total)", format_money(state_total))
    with m3:
        metric_card("Social Security YTD", format_money(snapshot.social_security_tax.ytd))
    with m4:
        metric_card("Medicare YTD", format_money(snapshot.medicare_tax.ytd))

    if snapshot.state_income_tax:
        st.markdown("### State Tax YTD By State")
        state_items = sorted(snapshot.state_income_tax.items())
        column_count = min(4, len(state_items))
        for offset in range(0, len(state_items), column_count):
            cols = st.columns(column_count)
            chunk = state_items[offset : offset + column_count]
            for idx, (state, pair) in enumerate(chunk):
                with cols[idx]:
                    metric_card(f"{state} Tax YTD", format_money(pair.ytd))

    if active_scope == "all_year":
        annual_summary = st.session_state.get("annual_summary_preview")
        if annual_summary:
            st.markdown("### Whole-Year Summary (From Payslips)")
            y1, y2, y3, y4 = st.columns(4)
            with y1:
                metric_card("Paystubs (Canonical)", str(annual_summary["paystub_count_canonical"]))
            with y2:
                gross_ytd = annual_summary["extracted"]["gross_pay"]["ytd"]
                metric_card(
                    "Gross Pay YTD",
                    format_money(Decimal(str(gross_ytd)) if gross_ytd is not None else None),
                )
            with y3:
                federal_ytd = annual_summary["extracted"]["federal_income_tax"]["ytd"]
                metric_card(
                    "Federal Tax YTD",
                    format_money(Decimal(str(federal_ytd)) if federal_ytd is not None else None),
                )
            with y4:
                metric_card("State Tax YTD Total", format_money(state_total))

            st.caption(
                f"Raw paystub files processed: {annual_summary['paystub_count_raw']} | "
                f"Latest pay date: {annual_summary['latest_pay_date']}"
            )
            st.markdown("#### Per-Payslip Year Ledger")
            st.dataframe(annual_summary["ledger"], use_container_width=True)
            ytd_flagged = [
                {
                    "pay_date": row.get("pay_date"),
                    "file": row.get("file"),
                    "ytd_verification": row.get("ytd_verification"),
                }
                for row in annual_summary["ledger"]
                if row.get("ytd_verification")
            ]
            if ytd_flagged:
                st.warning(
                    "YTD verification detected parsed-vs-calculated mismatches. "
                    "Review the rows below and evidence lines."
                )
                st.dataframe(ytd_flagged, use_container_width=True)
            st.download_button(
                "Download Year Ledger CSV",
                data=ledger_to_csv(annual_summary["ledger"]),
                file_name=f"paystub_ledger_{int(year)}.csv",
                mime="text/csv",
            )

    st.markdown("### Extracted State Details")
    state_rows = []
    for state, pair in sorted(snapshot.state_income_tax.items()):
        state_rows.append(
            {
                "State": state,
                "This Period": as_float(pair.this_period),
                "YTD": as_float(pair.ytd),
                "Evidence": pair.source_line,
            }
        )
    st.dataframe(state_rows, use_container_width=True)

    with st.expander("Evidence lines", expanded=False):
        for key in ["gross_pay", "federal_income_tax", "social_security_tax", "medicare_tax", "k401_contrib"]:
            line = extracted[key]["evidence"]
            if line:
                st.markdown(f"- `{key}`: `{line}`")
        for state, row in sorted(extracted["state_income_tax"].items()):
            st.markdown(f"- `state_{state}`: `{row['evidence']}`")

    st.markdown("### W-2 Cross-Check")
    uploaded = st.file_uploader("Upload W-2 JSON or PDF (optional)", type=["json", "pdf"])
    w2_data = None
    uploaded_source_tag = None
    if uploaded is not None:
        uploaded_bytes = uploaded.getvalue()
        digest = hashlib.sha1(uploaded_bytes).hexdigest()[:12]
        uploaded_source_tag = f"{uploaded.name}:{len(uploaded_bytes)}:{digest}"
        file_name = uploaded.name.lower()
        if file_name.endswith(".json"):
            try:
                w2_data = json.loads(uploaded_bytes.decode("utf-8-sig"))
                show_notice("Loaded W-2 JSON from upload. W-2 input fields were auto-populated.")
            except json.JSONDecodeError:
                st.error("Uploaded file is not valid JSON.")
                return
        elif file_name.endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                temp_pdf.write(uploaded_bytes)
                temp_path = Path(temp_pdf.name)
            try:
                w2_data = w2_pdf_to_json_payload(
                    pdf_path=temp_path,
                    render_scale=max(render_scale, 3.0),
                    psm=6,
                    fallback_year=int(year),
                )
                show_notice("Loaded W-2 PDF via OCR. W-2 input fields were auto-populated.")
                with st.expander("View extracted W-2 OCR payload", expanded=False):
                    st.json(w2_data)
            except Exception as exc:
                st.error(f"Failed to parse W-2 PDF: {exc}")
                return
            finally:
                temp_path.unlink(missing_ok=True)

    snapshot_states = sorted(snapshot.state_income_tax.keys()) or ["VA"]
    if w2_data is not None:
        sync_manual_w2_from_upload(
            uploaded_w2_data=w2_data,
            states_from_snapshot=snapshot_states,
            source_tag=uploaded_source_tag,
        )

    with st.form("manual_w2_form"):
        manual_w2 = build_manual_w2(snapshot, int(year))
        submitted = st.form_submit_button("Compare Against W-2")

    selected_w2 = manual_w2
    if submitted:
        comparisons, summary = compare_snapshot_to_w2(snapshot, selected_w2, tolerance)

        c1, c2, c3 = st.columns(3)
        c1.metric("Matches", summary.get("match", 0))
        c2.metric("Mismatches", summary.get("mismatch", 0))
        c3.metric("Review Needed", summary.get("review_needed", 0))

        st.markdown("#### Comparison Results")
        for row in comparisons:
            st.markdown(
                f"- **{row['field']}** | paystub `{row['paystub']}` | w2 `{row['w2']}` | diff `{row['difference']}` | {status_pill(row['status'])}",
                unsafe_allow_html=True,
            )

        payload = {
            "tax_year": int(year),
            "latest_paystub_file": snapshot.file,
            "latest_pay_date": snapshot.pay_date or latest_date.isoformat(),
            "extracted": extracted,
            "w2_input": selected_w2,
            "comparisons": comparisons,
            "comparison_summary": summary,
        }

        st.download_button(
            "Download Validation JSON",
            data=json.dumps(payload, indent=2),
            file_name="w2_validation_ui.json",
            mime="application/json",
        )
        st.download_button(
            "Download Validation Markdown",
            data=build_report_markdown(payload),
            file_name="w2_validation_ui.md",
            mime="text/markdown",
        )

    st.markdown("---")
    st.markdown("### Annual Filing Packet")
    st.caption(
        "Build a year-wide ledger from all payslips, run consistency checks, and generate a filing packet."
    )

    include_w2 = st.checkbox(
        "Include W-2 comparison in annual packet",
        value=True,
        help="Disable this to build the packet from paystubs only.",
    )
    if include_w2:
        st.caption(
            "Checkbox ON: annual packet includes W-2 match/mismatch checks and influences Ready To File."
        )
    else:
        st.caption(
            "Checkbox OFF: annual packet is paystub-only (no W-2 comparison), useful for extraction QA."
        )
    if st.button(
        "Build Annual Filing Packet",
        type="primary",
        help=(
            "Processes all paystubs in the selected tax year, applies YTD verification checks, "
            "and generates JSON, Markdown, and CSV outputs."
        ),
    ):
        annual_snapshots = collect_annual_snapshots(
            paystubs_dir=paystubs_dir,
            year=int(year),
            render_scale=render_scale,
            psm=6,
        )
        w2_for_packet = selected_w2 if include_w2 else None
        packet = build_tax_filing_package(
            tax_year=int(year),
            snapshots=annual_snapshots,
            tolerance=tolerance,
            w2_data=w2_for_packet,
        )
        st.session_state["annual_packet"] = packet

    packet = st.session_state.get("annual_packet")
    if packet:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Paystubs (Canonical)", packet["paystub_count_canonical"])
        p2.metric("Authenticity Score", packet["authenticity_assessment"]["score"])
        p3.metric("Ready To File", str(packet["ready_to_file"]))
        critical_count = sum(
            1 for issue in packet["consistency_issues"] if issue["severity"] == "critical"
        )
        p4.metric("Critical Issues", critical_count)
        st.caption(f"Raw paystub files analyzed: {packet['paystub_count_raw']}")

        st.markdown("#### Consistency Issues")
        if not packet["consistency_issues"]:
            st.success("No consistency issues detected.")
        else:
            for issue in packet["consistency_issues"]:
                prefix = "[CRITICAL]" if issue["severity"] == "critical" else "[WARNING]"
                st.markdown(f"- {prefix} `{issue['code']}`: {issue['message']}")

        st.markdown("#### Filing Checklist")
        for item in packet["filing_checklist"]:
            st.markdown(f"- **{item['item']}**: {item['detail']}")

        st.markdown("#### Annual Ledger")
        st.dataframe(packet["ledger"], use_container_width=True)
        packet_ytd_flagged = [
            {
                "pay_date": row.get("pay_date"),
                "file": row.get("file"),
                "ytd_verification": row.get("ytd_verification"),
            }
            for row in packet["ledger"]
            if row.get("ytd_verification")
        ]
        if packet_ytd_flagged:
            st.warning(
                "YTD verification flags were found in this filing packet. "
                "Check the rows below before filing."
            )
            st.dataframe(packet_ytd_flagged, use_container_width=True)

        packet_json = json.dumps(packet, indent=2)
        packet_md = package_to_markdown(packet)
        packet_csv = ledger_to_csv(packet["ledger"])
        st.download_button(
            "Download Filing Packet JSON",
            data=packet_json,
            file_name=f"tax_filing_package_{int(year)}.json",
            mime="application/json",
        )
        st.download_button(
            "Download Filing Packet Markdown",
            data=packet_md,
            file_name=f"tax_filing_package_{int(year)}.md",
            mime="text/markdown",
        )
        st.download_button(
            "Download Annual Ledger CSV",
            data=packet_csv,
            file_name=f"paystub_ledger_{int(year)}.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
