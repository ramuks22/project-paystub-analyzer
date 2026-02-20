#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import inspect
import io
import json
import tempfile
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import streamlit as st


from paystub_analyzer.core import (
    as_float,
    extract_paystub_snapshot,
    format_money,
    list_paystub_files,
    parse_pay_date_from_filename,
    select_latest_paystub,
    PaystubSnapshot,
)
from paystub_analyzer import annual as annual_module
from paystub_analyzer.w2 import build_w2_template, compare_snapshot_to_w2
from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload
from paystub_analyzer.annual import build_household_package


def _hash_file(path: Path) -> str:
    import hashlib

    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@st.cache_data(show_spinner=False)
def get_cached_paystub_snapshot(path_str: str, file_hash: str, render_scale: float) -> PaystubSnapshot:
    return extract_paystub_snapshot(Path(path_str), render_scale=render_scale)


@st.cache_data(show_spinner=False)
def get_cached_w2_payload(
    pdf_path_str: str, file_hash: str, render_scale: float, psm: int, fallback_year: int
) -> dict[str, Any]:
    return w2_pdf_to_json_payload(Path(pdf_path_str), render_scale=render_scale, psm=psm, fallback_year=fallback_year)


build_tax_filing_package = annual_module.build_tax_filing_package
collect_annual_snapshots = annual_module.collect_annual_snapshots
package_to_markdown = annual_module.package_to_markdown

APP_SESSION_SCHEMA_VERSION = "2026-02-19-ui-polish-v3"
ButtonKind = Literal["primary", "secondary", "tertiary"]


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
  --button-width: 220px;

  --border-subtle: #dee2e6;
  --border-strong: #ced4da;
}

/* Reduce default spacing */
.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    padding-left: 2rem;
    padding-right: 2rem;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.75rem !important; /* Reduce gap between elements */
}

/* Global resets for Streamlit containers */
[data-testid="stAppViewContainer"] {
  background-color: var(--bg-core);
  color: var(--text-primary);
  font-family: 'Inter', sans-serif;
}

[data-testid="stHeader"] {
  background-color: rgba(255, 255, 255, 0.95);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 90;
  backdrop-filter: blur(4px);
}

/* Real fixed title in top app header row (next to Deploy/menu) */
.app-topline-title {
  position: fixed;
  left: 3rem;
  top: 0.62rem;
  z-index: 120;
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  line-height: 1;
  max-width: calc(100vw - 15rem);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}
[data-testid="stSidebar"][aria-expanded="true"] + div .app-topline-title {
  left: calc(300px + 1rem) !important;
  max-width: calc(100vw - 300px - 12rem) !important;
}
[data-testid="stSidebar"][aria-expanded="false"] + div .app-topline-title {
  left: 3rem !important;
  max-width: calc(100vw - 12rem) !important;
}

[data-testid="stSidebar"] {
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
}

/* Sidebar collapse/expand control visibility on light theme */
[data-testid="stSidebarHeader"] {
  background-color: var(--bg-surface) !important;
  border-bottom: 1px solid var(--border-subtle);
}
[data-testid="stSidebarHeader"] button,
[data-testid="stSidebarHeader"] [role="button"],
[data-testid="stSidebarHeader"] button[kind="header"],
[data-testid="stSidebarHeader"] button[aria-label*="sidebar" i],
[data-testid="stSidebarHeader"] button[title*="sidebar" i],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapseButton"] [role="button"],
[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] button,
[data-testid="stExpandSidebarButton"] [role="button"],
[data-testid="collapsedControl"] button,
[data-testid="collapsedControl"] [role="button"] {
  color: var(--text-primary) !important;
  background-color: transparent !important;
  border: 1px solid transparent !important;
  opacity: 1 !important;
  visibility: visible !important;
}
[data-testid="stSidebarHeader"] button svg,
[data-testid="stSidebarHeader"] [role="button"] svg,
[data-testid="stSidebarHeader"] button[kind="header"] svg,
[data-testid="stSidebarCollapseButton"] button svg,
[data-testid="stSidebarCollapseButton"] [role="button"] svg,
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stExpandSidebarButton"] button svg,
[data-testid="stExpandSidebarButton"] [role="button"] svg,
[data-testid="collapsedControl"] button svg,
[data-testid="collapsedControl"] [role="button"] svg {
  fill: currentColor !important;
  stroke: currentColor !important;
}
[data-testid="stSidebarHeader"] button *,
[data-testid="stSidebarHeader"] [role="button"] *,
[data-testid="stSidebarHeader"] button[kind="header"] *,
[data-testid="stSidebarCollapseButton"] button *,
[data-testid="stSidebarCollapseButton"] [role="button"] *,
[data-testid="stExpandSidebarButton"] *,
[data-testid="stExpandSidebarButton"] button *,
[data-testid="stExpandSidebarButton"] [role="button"] *,
[data-testid="collapsedControl"] button *,
[data-testid="collapsedControl"] [role="button"] * {
  color: var(--text-primary) !important;
  fill: currentColor !important;
  stroke: currentColor !important;
  opacity: 1 !important;
  visibility: visible !important;
}
[data-testid="stSidebarHeader"] button:hover,
[data-testid="stSidebarHeader"] button:focus-visible,
[data-testid="stSidebarHeader"] [role="button"]:hover,
[data-testid="stSidebarHeader"] [role="button"]:focus-visible,
[data-testid="stSidebarHeader"] button[kind="header"]:hover,
[data-testid="stSidebarHeader"] button[kind="header"]:focus-visible,
[data-testid="stSidebarHeader"] button[aria-label*="sidebar" i]:hover,
[data-testid="stSidebarHeader"] button[aria-label*="sidebar" i]:focus-visible,
[data-testid="stSidebarHeader"] button[title*="sidebar" i]:hover,
[data-testid="stSidebarHeader"] button[title*="sidebar" i]:focus-visible,
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stSidebarCollapseButton"] button:focus-visible,
[data-testid="stSidebarCollapseButton"] [role="button"]:hover,
[data-testid="stSidebarCollapseButton"] [role="button"]:focus-visible,
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stExpandSidebarButton"]:focus-visible,
[data-testid="stExpandSidebarButton"] button:hover,
[data-testid="stExpandSidebarButton"] button:focus-visible,
[data-testid="stExpandSidebarButton"] [role="button"]:hover,
[data-testid="stExpandSidebarButton"] [role="button"]:focus-visible,
[data-testid="collapsedControl"] button:hover,
[data-testid="collapsedControl"] button:focus-visible,
[data-testid="collapsedControl"] [role="button"]:hover,
[data-testid="collapsedControl"] [role="button"]:focus-visible {
  color: var(--text-primary) !important;
  background-color: var(--bg-subtle) !important;
  border-color: var(--border-strong) !important;
}

/* Typographic enhancements */
h1, h2, h3, h4, h5, h6 {
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 0.5rem !important; /* Tighten headers */
}

/* In-page intro under fixed header title */
.app-intro {
  margin: 0.25rem 0 0.6rem;
}
.app-intro p {
  margin: 0 !important;
  color: var(--text-secondary) !important;
  font-size: 0.95rem !important;
}

/* Section heading treatment for Step blocks */
.step-heading {
  display: flex;
  align-items: center; /* Change from flex-start to center */
  gap: 0.7rem;
  padding: 0.55rem 0.8rem;
  margin: 0.2rem 0 0.45rem;
  border: 1px solid #d5e3ea;
  border-radius: 10px;
  background: linear-gradient(180deg, #f8fcff 0%, #f3f8fb 100%);
}
.step-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 80px;
  height: 2.25rem;
  padding: 0 0.75rem;
  border-radius: 8px;
  border: 1px solid #b8d0db;
  background: #ffffff;
  color: #0f5d75;
  font-size: 0.9rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.step-copy h3 {
  margin: 0 !important;
  color: var(--text-primary);
  font-size: 1.25rem;
  letter-spacing: -0.01em;
}
.step-copy p {
  margin: 0.2rem 0 0 !important;
  color: var(--text-secondary) !important;
  font-size: 0.9rem !important;
}

/* Fix global text spilling into Tooltips or unexpected places */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li {
  color: var(--text-primary);
  font-size: 1rem;
  line-height: 1.5; /* Slightly tighter line height */
  margin-bottom: 0.5rem; /* Reduce paragraph spacing */
}

.stCaption {
  color: var(--text-tertiary) !important;
  font-size: 0.85rem !important;
}

/* Custom Card Component */
.metric-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 0.75rem 1rem; /* Tighter padding */
  box-shadow: 0 1px 2px rgba(0,0,0,0.05); /* Softer shadow */
  margin-bottom: 0px; /* Let flex gap handle spacing */
}

.metric-card .label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  font-weight: 600;
  margin-bottom: 0.2rem;
}

.metric-card .value {
  font-size: 1.15rem; /* Slightly smaller value text */
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
  min-height: 38px;
}

div[data-baseweb="input"] input,
div[data-baseweb="select"] span,
div[data-baseweb="base-input"] input {
  color: var(--text-primary) !important;
  -webkit-text-fill-color: var(--text-primary) !important;
  caret-color: var(--brand-primary) !important;
}
div[data-baseweb="input"] input:focus-visible,
div[data-baseweb="base-input"] input:focus-visible,
div[data-baseweb="select"] input:focus-visible,
div[data-baseweb="select"] span:focus-visible {
  outline: 2px solid var(--brand-primary) !important;
  outline-offset: 1px;
}

/* Ensure labels are readable */
label[data-baseweb="checkbox"] span,
label[data-baseweb="radio"] span,
div[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
div[data-testid="stSidebar"] [data-testid="stWidgetLabel"] * {
  color: var(--text-primary) !important;
  font-size: 0.9rem !important;
  font-weight: 500 !important;
}

/* Fix for disabled inputs if needed */
div[data-baseweb="input"] input:disabled {
  color: var(--text-tertiary) !important;
  -webkit-text-fill-color: var(--text-tertiary) !important;
}

/* Button Styling Fixes */
div.stButton > button,
div.stButton button,
div[data-testid="stFormSubmitButton"] > button,
div[data-testid="stFormSubmitButton"] button,
div.stDownloadButton > button,
div.stDownloadButton button,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stDownloadButton"] button,
div[data-testid="stFileUploader"] button,
div[data-testid="stFileUploaderDropzone"] button,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
    width: var(--button-width) !important;
    min-width: var(--button-width);
    max-width: var(--button-width);
    min-height: 2.5rem !important;
    border-radius: 6px;
    font-weight: 600;
    transition: all 0.2s ease;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    line-height: normal !important;
    padding-top: 0.5rem !important;
    padding-bottom: 0.5rem !important;
    white-space: nowrap !important;
}

/* Reset inner text elements for deterministic alignment */
div.stButton > button > div,
div.stButton > button > div *,
div.stButton button > div,
div.stButton button > div *,
div[data-testid="stFormSubmitButton"] > button > div,
div[data-testid="stFormSubmitButton"] > button > div *,
div[data-testid="stFormSubmitButton"] button > div,
div[data-testid="stFormSubmitButton"] button > div *,
div.stDownloadButton > button > div,
div.stDownloadButton > button > div *,
div.stDownloadButton button > div,
div.stDownloadButton button > div *,
div[data-testid="stDownloadButton"] > button > div,
div[data-testid="stDownloadButton"] > button > div *,
div[data-testid="stDownloadButton"] button > div,
div[data-testid="stDownloadButton"] button > div *,
div[data-testid="stFileUploader"] button > div,
div[data-testid="stFileUploader"] button > div *,
div[data-testid="stFileUploaderDropzone"] button > div,
div[data-testid="stFileUploaderDropzone"] button > div *,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] > div,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] > div * {
    line-height: 1 !important;
    margin: 0 !important;
    padding: 0 !important;
    color: inherit !important;
}

/* Spinbutton Fixes: Neutral focus ring for A11Y, no stuck colors */
button[data-baseweb="spinbutton"] {
    background-color: transparent !important;
    color: var(--text-primary) !important;
    border: none !important;
}
button[data-baseweb="spinbutton"]:hover {
    background-color: var(--bg-subtle) !important;
    color: var(--brand-primary) !important;
}
button[data-baseweb="spinbutton"]:focus-visible {
    outline: 2px solid var(--text-primary) !important;
    outline-offset: -2px;
    background-color: var(--bg-subtle) !important;
    box-shadow: none !important;
}
/* Prevent "stuck" active color when parent input has focus, unless hovering */
div[data-baseweb="input"]:focus-within button[data-baseweb="spinbutton"]:not(:hover):not(:focus-visible) {
    background-color: transparent !important;
    color: var(--text-primary) !important;
    box-shadow: none !important;
}

/* Unified action button theme (Extract / Compare / Build) */
div.stButton > button,
div.stButton button,
div.stFormSubmitButton > button,
div.stFormSubmitButton button,
div[data-testid="stFormSubmitButton"] > button,
div[data-testid="stFormSubmitButton"] button,
div.stDownloadButton > button,
div.stDownloadButton button,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stDownloadButton"] button,
div[data-testid="stFileUploader"] button,
div[data-testid="stFileUploaderDropzone"] button,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
  background-color: var(--brand-primary) !important;
  color: #ffffff !important;
  border: 1px solid var(--brand-primary) !important;
}
div.stButton > button:hover,
div.stButton button:hover,
div.stFormSubmitButton > button:hover,
div.stFormSubmitButton button:hover,
div[data-testid="stFormSubmitButton"] > button:hover,
div[data-testid="stFormSubmitButton"] button:hover,
div.stDownloadButton > button:hover,
div.stDownloadButton button:hover,
div[data-testid="stDownloadButton"] > button:hover,
div[data-testid="stDownloadButton"] button:hover,
div[data-testid="stFileUploader"] button:hover,
div[data-testid="stFileUploaderDropzone"] button:hover,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:hover {
  background-color: var(--brand-primary-hover) !important;
  border-color: var(--brand-primary-hover) !important;
  color: #ffffff !important;
}
div.stButton > button:focus,
div.stButton > button:focus-visible,
div.stButton button:focus,
div.stButton button:focus-visible,
div.stFormSubmitButton > button:focus,
div.stFormSubmitButton > button:focus-visible,
div.stFormSubmitButton button:focus,
div.stFormSubmitButton button:focus-visible,
div[data-testid="stFormSubmitButton"] > button:focus,
div[data-testid="stFormSubmitButton"] > button:focus-visible,
div[data-testid="stFormSubmitButton"] button:focus,
div[data-testid="stFormSubmitButton"] button:focus-visible,
div.stDownloadButton > button:focus,
div.stDownloadButton > button:focus-visible,
div.stDownloadButton button:focus,
div.stDownloadButton button:focus-visible,
div[data-testid="stDownloadButton"] > button:focus,
div[data-testid="stDownloadButton"] > button:focus-visible,
div[data-testid="stDownloadButton"] button:focus,
div[data-testid="stDownloadButton"] button:focus-visible,
div[data-testid="stFileUploader"] button:focus,
div[data-testid="stFileUploader"] button:focus-visible,
div[data-testid="stFileUploaderDropzone"] button:focus,
div[data-testid="stFileUploaderDropzone"] button:focus-visible,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:focus,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:focus-visible {
  background-color: var(--brand-primary) !important;
  border-color: var(--brand-primary) !important;
  color: #ffffff !important;
}
div.stButton > button:active,
div.stButton button:active,
div.stFormSubmitButton > button:active,
div.stFormSubmitButton button:active,
div[data-testid="stFormSubmitButton"] button:active,
div[data-testid="stFormSubmitButton"] > button:active,
div.stDownloadButton > button:active,
div.stDownloadButton button:active,
div[data-testid="stDownloadButton"] > button:active,
div[data-testid="stDownloadButton"] button:active,
div[data-testid="stFileUploader"] button:active,
div[data-testid="stFileUploaderDropzone"] button:active,
div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]:active {
  background-color: var(--brand-primary-hover) !important;
  border-color: var(--brand-primary-hover) !important;
  color: #ffffff !important;
}

/* Tooltip Visibility */
div[data-testid="stTooltipContent"] {
    background-color: #333333 !important;
    color: #ffffff !important;
}

/* Tooltip Fix (Attempt to override dark-on-dark if Streamlit inherits colors incorrectly) */
div[data-testid="stTooltipContent"] {
    background-color: #333333 !important;
    color: #ffffff !important;
}
div[role="tooltip"] {
    background-color: #333333 !important;
    color: #ffffff !important;
    font-size: 0.85rem;
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

/* Run summary strip */
.run-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.6rem;
  margin: 0.25rem 0 0.85rem;
}
.run-item {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-surface);
  padding: 0.5rem 0.65rem;
}
.run-item .label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  font-weight: 600;
  margin-bottom: 0.2rem;
}
.run-item .value {
  font-size: 0.9rem;
  color: var(--text-primary);
  font-weight: 600;
  line-height: 1.2;
  word-break: break-word;
}
.run-value-good { color: #166534 !important; }
.run-value-warn { color: #b45309 !important; }
.run-value-bad { color: #991b1b !important; }

/* Extraction quality panel */
.quality-panel {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: #f8fafc;
  padding: 0.7rem 0.85rem;
}
.quality-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
}
.quality-chip {
  display: inline-flex;
  border-radius: 9999px;
  font-size: 0.72rem;
  padding: 0.14rem 0.55rem;
  font-weight: 700;
  text-transform: uppercase;
}
.quality-high { background: #dcfce7; color: #166534; }
.quality-medium { background: #fef9c3; color: #854d0e; }
.quality-low { background: #fee2e2; color: #991b1b; }

/* Dataframe readability */
div[data-testid="stDataFrame"] [role="columnheader"] {
  font-weight: 700 !important;
  background-color: #f1f5f9 !important;
  color: #0f172a !important;
  border-bottom: 1px solid var(--border-strong) !important;
}
div[data-testid="stDataFrame"] [role="columnheader"] * {
  color: #0f172a !important;
}
div[data-testid="stDataFrame"] [role="gridcell"] {
  line-height: 1.35 !important;
}
div[data-testid="stDataFrame"] [role="gridcell"] [data-testid="stMarkdownContainer"] p {
  margin: 0 !important;
}

/* Expander readability */
div[data-testid="stExpander"] details {
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  background: #ffffff !important;
}
div[data-testid="stExpander"] summary {
  background: var(--bg-surface) !important;
  color: var(--text-primary) !important;
  border-radius: 8px !important;
}
div[data-testid="stExpander"] summary * {
  color: var(--text-primary) !important;
}
div[data-testid="stExpander"] summary:hover {
  background: var(--bg-subtle) !important;
}

/* Popover as clickable info icon */
div[data-testid="stPopover"] button {
  width: 2rem !important;
  min-width: 2rem !important;
  height: 2rem !important;
  padding: 0 !important;
  border-radius: 999px !important;
  background: #e8f2f7 !important;
  color: #0f5d75 !important;
  border: 1px solid #b8d0db !important;
  font-weight: 700 !important;
}
div[data-testid="stPopover"] button:hover,
div[data-testid="stPopover"] button:focus-visible {
  background: #d8eaf3 !important;
  border-color: #8eb3c4 !important;
  color: #0b4a5d !important;
}
[data-baseweb="popover"] {
  max-width: min(92vw, 520px) !important;
}
[data-baseweb="popover"] * {
  color: var(--text-primary) !important;
}
[data-baseweb="popover"] p,
[data-baseweb="popover"] li {
  color: var(--text-primary) !important;
}

/* Top-right Streamlit main menu readability (next to Deploy) */
div[data-testid="stMainMenuPopover"],
div[data-testid="stMainMenuPopover"] > div,
div[data-testid="stMainMenuPopover"] [role="menu"] {
  background: var(--bg-core) !important;
  color: var(--text-primary) !important;
  border-color: var(--border-strong) !important;
}
div[data-testid="stMainMenuPopover"] [role="menuitem"],
div[data-testid="stMainMenuPopover"] [role="menuitem"] * {
  color: var(--text-primary) !important;
  background: transparent !important;
}
div[data-testid="stMainMenuPopover"] a,
div[data-testid="stMainMenuPopover"] a *,
div[data-testid="stMainMenuPopover"] button,
div[data-testid="stMainMenuPopover"] button *,
div[data-testid="stMainMenuPopover"] [role="link"],
div[data-testid="stMainMenuPopover"] [role="link"] * {
  color: var(--text-primary) !important;
  background: transparent !important;
  box-shadow: none !important;
}
div[data-testid="stMainMenuPopover"] [role="menuitem"]:hover,
div[data-testid="stMainMenuPopover"] [role="menuitem"]:focus-visible {
  background: var(--bg-subtle) !important;
  color: var(--text-primary) !important;
}
div[data-testid="stMainMenuPopover"] a:hover,
div[data-testid="stMainMenuPopover"] button:hover,
div[data-testid="stMainMenuPopover"] [role="link"]:hover,
div[data-testid="stMainMenuPopover"] a:focus-visible,
div[data-testid="stMainMenuPopover"] button:focus-visible,
div[data-testid="stMainMenuPopover"] [role="link"]:focus-visible {
  background: var(--bg-subtle) !important;
  color: var(--text-primary) !important;
}

/* Fallback for Streamlit/BaseWeb menu portal structures */
[data-baseweb="popover"] [role="menu"] {
  background: var(--bg-core) !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-strong) !important;
}
[data-baseweb="popover"] [role="menu"] > *,
[data-baseweb="popover"] [role="menu"] [role="none"],
[data-baseweb="popover"] [role="menu"] ul,
[data-baseweb="popover"] [role="menu"] li,
[data-baseweb="popover"] [role="menu"] div {
  background: transparent !important;
  color: var(--text-primary) !important;
}
[data-baseweb="popover"] [role="menu"] [role="menuitem"],
[data-baseweb="popover"] [role="menu"] a,
[data-baseweb="popover"] [role="menu"] button,
[data-baseweb="popover"] [role="menu"] [role="link"] {
  background: transparent !important;
  color: var(--text-primary) !important;
  box-shadow: none !important;
}
[data-baseweb="popover"] [role="menu"] [role="menuitem"] *,
[data-baseweb="popover"] [role="menu"] a *,
[data-baseweb="popover"] [role="menu"] button *,
[data-baseweb="popover"] [role="menu"] [role="link"] * {
  color: var(--text-primary) !important;
  background: transparent !important;
}
[data-baseweb="popover"] [role="menu"] [role="menuitem"]:hover,
[data-baseweb="popover"] [role="menu"] [role="menuitem"]:focus-visible,
[data-baseweb="popover"] [role="menu"] a:hover,
[data-baseweb="popover"] [role="menu"] a:focus-visible,
[data-baseweb="popover"] [role="menu"] button:hover,
[data-baseweb="popover"] [role="menu"] button:focus-visible,
[data-baseweb="popover"] [role="menu"] [role="link"]:hover,
[data-baseweb="popover"] [role="menu"] [role="link"]:focus-visible {
  background: var(--bg-subtle) !important;
  color: var(--text-primary) !important;
}

/* Explicit Streamlit main menu list rows (role=option) */
[data-testid="stMainMenuList"] {
  background: var(--bg-core) !important;
  color: var(--text-primary) !important;
}
[data-testid="stMainMenuList"] li,
[data-testid="stMainMenuList"] ul,
[data-testid="stMainMenuList"] [role="option"],
[data-testid="stMainMenuList"] [role="option"] *,
[data-testid="stMainMenuList"] li *,
[data-testid="stMainMenuList"] span,
[data-testid="stMainMenuList"] kbd {
  color: var(--text-primary) !important;
}
[data-testid="stMainMenuList"] li,
[data-testid="stMainMenuList"] [role="option"] {
  background: var(--bg-core) !important;
}
[data-testid="stMainMenuList"] li:hover,
[data-testid="stMainMenuList"] li:focus-visible,
[data-testid="stMainMenuList"] [role="option"]:hover,
[data-testid="stMainMenuList"] [role="option"]:focus-visible {
  background: var(--bg-subtle) !important;
}

/* Workflow Step Tracker */
.workflow-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0.25rem 0 1.0rem;
}
.workflow-step {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-surface);
  padding: 0.55rem 0.7rem;
}
.workflow-step.active {
  border-color: var(--brand-primary);
  box-shadow: 0 0 0 1px rgba(15, 93, 117, 0.25);
}
.workflow-step .step-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
}
.workflow-step .step-state {
  display: inline-flex;
  margin-top: 0.3rem;
  border-radius: 9999px;
  padding: 0.15rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
}
.workflow-step .state-not-run,
.workflow-step .state-locked {
  background: #f3f4f6;
  color: #4b5563;
}
.workflow-step .state-in-progress {
  background: #dbeafe;
  color: #1d4ed8;
}
.workflow-step .state-completed {
  background: #dcfce7;
  color: #166534;
}
.workflow-step .state-needs-review {
  background: #fee2e2;
  color: #991b1b;
}
@media (max-width: 980px) {
  .app-topline-title {
    left: 2.6rem;
    font-size: 1.1rem;
    max-width: calc(100vw - 11rem);
  }
  [data-testid="stSidebar"][aria-expanded="true"] + div .app-topline-title {
    left: calc(300px + 0.6rem) !important;
    max-width: calc(100vw - 300px - 9rem) !important;
  }
  [data-testid="stSidebar"][aria-expanded="false"] + div .app-topline-title {
    left: 2.6rem !important;
    max-width: calc(100vw - 9rem) !important;
  }
  .step-heading {
    flex-direction: column;
    gap: 0.4rem;
    padding: 0.55rem 0.65rem;
  }
  .run-summary {
    grid-template-columns: 1fr;
  }
  .workflow-steps {
    grid-template-columns: 1fr;
  }
  div[data-testid="stElementContainer"]:has(> div[data-testid="stButton"]),
  div[data-testid="stElementContainer"]:has(> div[data-testid="stFormSubmitButton"]),
  div[data-testid="stElementContainer"]:has(> div[data-testid="stDownloadButton"]),
  div[data-testid="stElementContainer"]:has(> div[data-testid="stFileUploader"]),
  div[data-testid="stElementContainer"]:has(> div[data-testid="stFileUploaderDropzone"]) {
    width: 100% !important;
  }
  div.stButton,
  div[data-testid="stButton"],
  div[data-testid="stFormSubmitButton"],
  div.stDownloadButton,
  div[data-testid="stDownloadButton"],
  div[data-testid="stFileUploader"],
  div[data-testid="stFileUploaderDropzone"] {
    width: 100% !important;
  }
  div.stButton > button,
  div.stButton button,
  div[data-testid="stFormSubmitButton"] > button,
  div[data-testid="stFormSubmitButton"] button,
  div.stDownloadButton > button,
  div.stDownloadButton button,
  div[data-testid="stDownloadButton"] > button,
  div[data-testid="stDownloadButton"] button,
  div[data-testid="stFileUploader"] button,
  div[data-testid="stFileUploaderDropzone"] button,
  div[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
    width: 100% !important;
    min-width: 100% !important;
    max-width: 100% !important;
  }
}

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


def clear_workflow_state() -> None:
    keys_to_clear = [
        "snapshot",
        "annual_summary_preview",
        "analysis_scope",
        "annual_packet",
        "w2_validation",
        "extract_run_meta",
        "extract_quality",
        "pay_date_overrides",
        "_w2_autofilled_fields",
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
        if not isinstance(key, str):
            continue
        if key in keys_to_clear or key.startswith("box16_") or key.startswith("box17_"):
            st.session_state.pop(key, None)


def reset_session_if_schema_changed() -> None:
    existing = st.session_state.get("_app_schema_version")
    if existing == APP_SESSION_SCHEMA_VERSION:
        return
    clear_workflow_state()
    st.session_state.pop("_analysis_scope_last", None)
    st.session_state["_w2_upload_version"] = 0
    st.session_state["_app_schema_version"] = APP_SESSION_SCHEMA_VERSION


def to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None


def format_currency_display(value: Any) -> str:
    amount = to_decimal(value)
    if amount is None:
        return "—"
    return f"${amount:,.2f}"


def format_plain_display(value: Any) -> str:
    if value in (None, ""):
        return "—"
    return str(value)


def format_state_map_display(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "—"
    pairs: list[str] = []
    for state in sorted(value.keys()):
        pairs.append(f"{state}: {format_currency_display(value.get(state))}")
    return ", ".join(pairs) if pairs else "—"


def display_file_name(value: Any) -> str:
    text = format_plain_display(value)
    if text in {"—", ""}:
        return "—"
    if text.startswith("ALL ("):
        return text
    normalized = str(text).replace("\\", "/")
    base_name = normalized.rsplit("/", 1)[-1]
    return base_name or text


def build_extraction_quality(snapshot: PaystubSnapshot) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    score = 100

    gross_ytd = to_decimal(snapshot.gross_pay.ytd)
    fed_ytd = to_decimal(snapshot.federal_income_tax.ytd)
    ss_ytd = to_decimal(snapshot.social_security_tax.ytd)
    med_ytd = to_decimal(snapshot.medicare_tax.ytd)

    if gross_ytd is None or gross_ytd <= 0:
        issues.append({"severity": "critical", "message": "Gross pay YTD is missing or zero."})
        score -= 35
    for label, value in [
        ("Federal tax YTD", fed_ytd),
        ("Social Security tax YTD", ss_ytd),
        ("Medicare tax YTD", med_ytd),
    ]:
        if value is None:
            issues.append({"severity": "critical", "message": f"{label} could not be extracted."})
            score -= 35

    if gross_ytd is not None and gross_ytd > 1000 and fed_ytd is not None and fed_ytd == 0:
        issues.append({"severity": "warning", "message": "Federal tax YTD is zero while gross pay is significant."})
        score -= 15
    if not snapshot.state_income_tax:
        issues.append({"severity": "warning", "message": "No state tax entries were detected in this payslip."})
        score -= 10

    evidence_lines = [
        snapshot.gross_pay.source_line,
        snapshot.federal_income_tax.source_line,
        snapshot.social_security_tax.source_line,
        snapshot.medicare_tax.source_line,
        snapshot.k401_contrib.source_line,
        *[pair.source_line for pair in snapshot.state_income_tax.values()],
    ]
    evidence_count = sum(1 for line in evidence_lines if line)
    if evidence_count < 5:
        issues.append({"severity": "warning", "message": "Low evidence coverage detected; verify OCR output lines."})
        score -= 10

    score = max(0, min(100, score))
    confidence = "High" if score >= 85 else "Medium" if score >= 65 else "Low"
    return {"confidence": confidence, "score": score, "issues": issues, "evidence_count": evidence_count}


def render_extraction_quality_panel(quality: dict[str, Any]) -> None:
    confidence = str(quality.get("confidence", "Medium"))
    score = int(quality.get("score", 0))
    issue_rows = cast(list[dict[str, str]], quality.get("issues", []))
    evidence_count = int(quality.get("evidence_count", 0))
    chip_class = (
        "quality-high" if confidence == "High" else "quality-medium" if confidence == "Medium" else "quality-low"
    )

    issue_markdown = ""
    if issue_rows:
        issue_markdown = (
            "<ul>"
            + "".join(
                f"<li><strong>{row.get('severity', '').title()}:</strong> {row.get('message', '')}</li>"
                for row in issue_rows
            )
            + "</ul>"
        )
    else:
        issue_markdown = "<p>No extraction warnings detected.</p>"

    st.markdown(
        (
            "<div class='quality-panel'>"
            "<div class='quality-head'>"
            f"<span class='quality-chip {chip_class}'>{confidence}</span>"
            f"<strong>Extraction Confidence: {score}/100</strong>"
            "</div>"
            f"<p>Evidence lines captured: <strong>{evidence_count}</strong></p>"
            f"{issue_markdown}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_run_summary(tax_year: int, file_count: int) -> None:
    run_meta = cast(dict[str, Any], st.session_state.get("extract_run_meta", {}))
    quality_meta = cast(dict[str, Any], st.session_state.get("extract_quality", {}))
    w2_validation = cast(dict[str, Any], st.session_state.get("w2_validation", {}))
    packet = cast(dict[str, Any], st.session_state.get("annual_packet", {}))

    last_run_text = "Not run"
    last_run_class = "run-value-warn"
    if run_meta:
        ts = format_plain_display(run_meta.get("timestamp"))
        duration_s = run_meta.get("duration_s")
        run_status = str(run_meta.get("status", "Completed"))
        if duration_s is not None:
            last_run_text = f"{run_status}: {ts} ({duration_s:.1f}s)"
        else:
            last_run_text = f"{run_status}: {ts}"
        last_run_class = "run-value-bad" if run_status.lower() == "failed" else "run-value-good"

    mismatch_count = 0
    if w2_validation:
        summary = cast(dict[str, Any], w2_validation.get("comparison_summary", {}))
        mismatch_count = int(summary.get("mismatch", 0)) + int(summary.get("review_needed", 0))

    ready_text = "Pending"
    ready_class = "run-value-warn"
    if packet:
        is_ready = bool(packet.get("ready_to_file"))
        ready_text = "Ready" if is_ready else "Needs review"
        ready_class = "run-value-good" if is_ready else "run-value-bad"

    confidence_text = "Pending"
    confidence_class = "run-value-warn"
    if quality_meta:
        confidence_text = str(quality_meta.get("confidence", "Pending"))
        confidence_class = (
            "run-value-good"
            if confidence_text == "High"
            else "run-value-warn"
            if confidence_text == "Medium"
            else "run-value-bad"
        )

    mismatch_class = "run-value-good" if mismatch_count == 0 else "run-value-bad"

    st.markdown(
        (
            "<div class='run-summary'>"
            f"<div class='run-item'><div class='label'>Tax Year</div><div class='value'>{tax_year}</div></div>"
            f"<div class='run-item'><div class='label'>Paystubs Found</div><div class='value'>{file_count}</div></div>"
            f"<div class='run-item'><div class='label'>Last Extraction</div><div class='value {last_run_class}'>{last_run_text}</div></div>"
            f"<div class='run-item'><div class='label'>Step 2 Flags</div><div class='value {mismatch_class}'>{mismatch_count}</div></div>"
            f"<div class='run-item'><div class='label'>Ready To File</div><div class='value {ready_class}'>{ready_text}</div>"
            f"<div class='label' style='margin-top:0.25rem;'>Extraction Confidence</div>"
            f"<div class='value {confidence_class}'>{confidence_text}</div></div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def style_flagged_rows(
    df: pd.DataFrame, flag_column: str, right_align_columns: list[str] | None = None
) -> pd.io.formats.style.Styler:
    def apply_row_style(row: pd.Series) -> list[str]:
        flagged = str(row.get(flag_column, "—")) != "—"
        if not flagged:
            return [""] * len(row)
        return ["background-color: #fef2f2; color: #b91c1c; font-weight: 600"] * len(row)

    styled = df.style.apply(apply_row_style, axis=1)
    if right_align_columns:
        available = [col for col in right_align_columns if col in df.columns]
        if available:
            styled = styled.set_properties(
                subset=available,
                **{"text-align": "right", "font-family": "'JetBrains Mono', monospace"},
            )
    return styled


def build_comparison_display_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    display_rows: list[dict[str, str]] = []
    for row in rows:
        status_raw = str(row.get("status", ""))
        status = status_raw.replace("_", " ").title()
        severity = "Flagged" if status_raw in {"mismatch", "review_needed"} else "OK"
        display_rows.append(
            {
                "Field": format_plain_display(row.get("field")),
                "Paystub": format_currency_display(row.get("paystub")),
                "W-2": format_currency_display(row.get("w2")),
                "Difference": format_currency_display(row.get("difference")),
                "Status": status,
                "Flag": severity if severity == "Flagged" else "—",
            }
        )
    return pd.DataFrame(display_rows)


def build_ledger_display_df(
    ledger: list[dict[str, Any]],
    include_calc_columns: bool = False,
) -> pd.DataFrame:
    if not ledger:
        return pd.DataFrame()
    rows: list[dict[str, str]] = []
    for row_num, row in enumerate(ledger, start=1):
        record = {
            "S.No": str(row_num),
            "Pay Date": format_plain_display(row.get("pay_date")),
            "File": display_file_name(row.get("file")),
        }
        if include_calc_columns:
            record["Calculation Status"] = format_plain_display(row.get("calculation_status"))
            record["Canonical File"] = display_file_name(row.get("canonical_file"))

        record.update(
            {
                "Gross YTD": format_currency_display(row.get("gross_pay_ytd")),
                "Federal YTD": format_currency_display(row.get("federal_tax_ytd")),
                "SS YTD": format_currency_display(row.get("social_security_tax_ytd")),
                "Medicare YTD": format_currency_display(row.get("medicare_tax_ytd")),
                "State YTD Total": format_currency_display(row.get("state_tax_ytd_total")),
                "State YTD By State": format_state_map_display(row.get("state_tax_ytd_by_state")),
                "YTD Verification": format_plain_display(row.get("ytd_verification")),
            }
        )
        rows.append(record)
    return pd.DataFrame(rows)


def build_state_detail_rows(snapshot: PaystubSnapshot) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for state, pair in sorted(snapshot.state_income_tax.items()):
        rows.append(
            {
                "State": state,
                "This Period": format_currency_display(pair.this_period),
                "YTD": format_currency_display(pair.ytd),
                "Evidence": pair.source_line if pair.source_line else "—",
            }
        )
    return rows


def collect_evidence_lines(extracted: dict[str, Any]) -> list[tuple[str, str]]:
    evidence_lines: list[tuple[str, str]] = []
    for key in ["gross_pay", "federal_income_tax", "social_security_tax", "medicare_tax", "k401_contrib"]:
        line = extracted.get(key, {}).get("evidence")
        if line:
            evidence_lines.append((key, line))
    for state, row in sorted(extracted.get("state_income_tax", {}).items()):
        evidence = row.get("evidence")
        if evidence:
            evidence_lines.append((f"state_{state}", evidence))
    return evidence_lines


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


def snapshot_to_dict(snapshot: PaystubSnapshot) -> dict[str, Any]:
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


def get_filer_pay_date_overrides(filer_id: str) -> dict[str, str]:
    all_overrides = cast(dict[str, dict[str, str]], st.session_state.setdefault("pay_date_overrides", {}))
    return all_overrides.setdefault(filer_id, {})


def render_pay_date_override_editor(
    filer_id: str,
    files: list[Path],
    tax_year: int,
) -> dict[str, str]:
    existing = get_filer_pay_date_overrides(filer_id)
    rows: list[dict[str, str]] = []
    for file_path in files:
        detected = parse_pay_date_from_filename(file_path)
        detected_iso = detected.isoformat() if detected else ""
        assigned_iso = existing.get(file_path.name, detected_iso)
        rows.append(
            {
                "File": file_path.name,
                "Detected Pay Date": detected_iso,
                "Assigned Pay Date": assigned_iso,
            }
        )

    editor_df = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        key=f"pay_date_override_editor_{filer_id}_{tax_year}",
        column_config={
            "File": st.column_config.Column(disabled=True),
            "Detected Pay Date": st.column_config.Column(disabled=True),
            "Assigned Pay Date": st.column_config.TextColumn(
                help="Use YYYY-MM-DD. Leave as detected date to keep automatic behavior."
            ),
        },
    )

    valid_overrides: dict[str, str] = {}
    invalid_rows: list[str] = []
    for _, row in editor_df.iterrows():
        file_name = str(row.get("File", "")).strip()
        detected_str = str(row.get("Detected Pay Date", "")).strip()
        assigned = str(row.get("Assigned Pay Date", "")).strip()
        if not file_name or not assigned or assigned == detected_str:
            continue
        try:
            normalized = date.fromisoformat(assigned).isoformat()
        except ValueError:
            invalid_rows.append(file_name)
            continue
        valid_overrides[file_name] = normalized

    all_overrides = cast(dict[str, dict[str, str]], st.session_state.setdefault("pay_date_overrides", {}))
    all_overrides[filer_id] = valid_overrides
    if invalid_rows:
        st.warning(
            "Ignored invalid pay-date override format for: " + ", ".join(sorted(invalid_rows)) + ". Use YYYY-MM-DD."
        )

    return valid_overrides


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


def supports_kwarg(func: Any, kwarg_name: str) -> bool:
    try:
        return kwarg_name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


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
    autofilled_fields: set[str] = set()

    st.session_state["box1"] = as_number(uploaded_w2_data.get("box_1_wages_tips_other_comp"), st.session_state["box1"])
    autofilled_fields.add("box1")
    st.session_state["box2"] = as_number(
        uploaded_w2_data.get("box_2_federal_income_tax_withheld"), st.session_state["box2"]
    )
    autofilled_fields.add("box2")
    st.session_state["box3"] = as_number(uploaded_w2_data.get("box_3_social_security_wages"), st.session_state["box3"])
    autofilled_fields.add("box3")
    st.session_state["box4"] = as_number(
        uploaded_w2_data.get("box_4_social_security_tax_withheld"), st.session_state["box4"]
    )
    autofilled_fields.add("box4")
    st.session_state["box5"] = as_number(
        uploaded_w2_data.get("box_5_medicare_wages_and_tips"), st.session_state["box5"]
    )
    autofilled_fields.add("box5")
    st.session_state["box6"] = as_number(uploaded_w2_data.get("box_6_medicare_tax_withheld"), st.session_state["box6"])
    autofilled_fields.add("box6")

    for state in form_states:
        state_row = uploaded_states.get(state)
        if state_row:
            st.session_state[f"box16_{state}"] = state_row["box16"]
            st.session_state[f"box17_{state}"] = state_row["box17"]
            autofilled_fields.add(f"box16_{state}")
            autofilled_fields.add(f"box17_{state}")

    st.session_state["manual_w2_prefill_source"] = source_tag
    st.session_state["_w2_autofilled_fields"] = sorted(autofilled_fields)


def build_manual_w2(snapshot: PaystubSnapshot, tax_year: int) -> dict[str, Any]:
    states_from_snapshot = sorted(snapshot.state_income_tax.keys()) or ["VA"]
    prior_states = st.session_state.get("manual_w2_states", [])
    states_for_form = sorted(set(states_from_snapshot) | set(prior_states))
    if not states_for_form:
        states_for_form = ["VA"]
    st.session_state["manual_w2_states"] = states_for_form
    ensure_manual_w2_defaults(states_for_form)
    autofilled = set(cast(list[str], st.session_state.get("_w2_autofilled_fields", [])))

    def autofill_label(base: str, key: str) -> str:
        return f"{base} [Auto-filled]" if key in autofilled else base

    st.subheader("W-2 Inputs")
    st.caption("Enter your W-2 box values. Use cents for exact matching.")
    if autofilled:
        st.caption(f"{len(autofilled)} field(s) were auto-filled from the uploaded W-2.")

    st.markdown("#### Federal Income Tax")
    c1, c2 = st.columns(2)
    with c1:
        box1 = st.number_input(autofill_label("Box 1 wages", "box1"), min_value=0.0, step=0.01, key="box1")
    with c2:
        box2 = st.number_input(autofill_label("Box 2 federal tax", "box2"), min_value=0.0, step=0.01, key="box2")

    st.markdown("#### Payroll Taxes (FICA)")
    c3, c4 = st.columns(2)
    with c3:
        box3 = st.number_input(
            autofill_label("Box 3 Social Security wages", "box3"),
            min_value=0.0,
            step=0.01,
            key="box3",
        )
        box4 = st.number_input(
            autofill_label("Box 4 Social Security tax", "box4"),
            min_value=0.0,
            step=0.01,
            key="box4",
        )
    with c4:
        box5 = st.number_input(
            autofill_label("Box 5 Medicare wages", "box5"),
            min_value=0.0,
            step=0.01,
            key="box5",
        )
        box6 = st.number_input(
            autofill_label("Box 6 Medicare tax", "box6"),
            min_value=0.0,
            step=0.01,
            key="box6",
        )

    st.markdown("#### State Boxes")
    state_boxes = []
    for state in st.session_state.get("manual_w2_states", states_for_form):
        s1, s2 = st.columns(2)
        with s1:
            box16 = st.number_input(
                autofill_label(f"{state} Box 16 wages", f"box16_{state}"),
                min_value=0.0,
                step=0.01,
                key=f"box16_{state}",
            )
        with s2:
            box17 = st.number_input(
                autofill_label(f"{state} Box 17 tax", f"box17_{state}"),
                min_value=0.0,
                step=0.01,
                key=f"box17_{state}",
            )
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


def step_state_class(step_state: str) -> str:
    normalized = step_state.lower().replace(" ", "-")
    return f"state-{normalized}"


def render_workflow_steps(steps: list[dict[str, Any]]) -> None:
    cards: list[str] = []
    for step in steps:
        active_class = " active" if step.get("active", False) else ""
        state = str(step.get("state", "Not run"))
        state_class = step_state_class(state)
        title = str(step.get("title", ""))
        cards.append(
            "<div class='workflow-step"
            + active_class
            + "'><div class='step-title'>"
            + title
            + "</div><span class='step-state "
            + state_class
            + "'>"
            + state
            + "</span></div>"
        )
    st.markdown("<div class='workflow-steps'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def render_step_heading(step_number: int, title: str, subtitle: str) -> None:
    st.markdown(
        (
            "<div class='step-heading'>"
            f"<span class='step-chip'>Step {step_number}</span>"
            "<div class='step-copy'>"
            f"<h3>{title}</h3>"
            f"<p>{subtitle}</p>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


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
        csv_row["state_tax_ytd_by_state"] = json.dumps(csv_row["state_tax_ytd_by_state"], sort_keys=True)
        writer.writerow(csv_row)
        writer.writerow(csv_row)
    return buffer.getvalue()


def render_setup_wizard() -> None:
    st.markdown("## Household Setup Wizard")
    st.markdown("Configure your household details to begin the analysis.")

    tab1, tab2 = st.tabs(["Manual Setup", "Load Config File"])

    with tab1:
        with st.form("household_setup_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                tax_year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=2025)
            with col2:
                states = [
                    "AL",
                    "AK",
                    "AZ",
                    "AR",
                    "CA",
                    "CO",
                    "CT",
                    "DE",
                    "FL",
                    "GA",
                    "HI",
                    "ID",
                    "IL",
                    "IN",
                    "IA",
                    "KS",
                    "KY",
                    "LA",
                    "ME",
                    "MD",
                    "MA",
                    "MI",
                    "MN",
                    "MS",
                    "MO",
                    "MT",
                    "NE",
                    "NV",
                    "NH",
                    "NJ",
                    "NM",
                    "NY",
                    "NC",
                    "ND",
                    "OH",
                    "OK",
                    "OR",
                    "PA",
                    "RI",
                    "SC",
                    "SD",
                    "TN",
                    "TX",
                    "UT",
                    "VT",
                    "VA",
                    "WA",
                    "WV",
                    "WI",
                    "WY",
                ]
                state = st.selectbox("State", states, index=4)  # Default CA
            with col3:
                filing_status = st.selectbox(
                    "Filing Status", ["SINGLE", "MARRIED_JOINTLY", "MARRIED_SEPARATELY", "HEAD_OF_HOUSEHOLD", "WIDOWED"]
                )

            st.markdown("### Filers")
            primary_dir = st.text_input("Primary Filer Paystubs Directory", value="pay_statements")

            include_spouse = st.checkbox("Include Spouse?")
            spouse_dir = ""
            if include_spouse:
                spouse_dir = st.text_input("Spouse Paystubs Directory", value="pay_statements_spouse")

            submitted = st.form_submit_button("Start Analysis")
            if submitted:
                config: dict[str, Any] = {
                    "version": "0.4.0",
                    "household_id": f"household_{tax_year}",
                    "filing_year": int(tax_year),
                    "state": state,
                    "filing_status": filing_status,
                    "filers": [{"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": primary_dir}}],
                }
                if include_spouse and spouse_dir:
                    config["filers"].append({"id": "spouse", "role": "SPOUSE", "sources": {"paystubs_dir": spouse_dir}})

                from paystub_analyzer.utils.contracts import validate_output

                try:
                    validate_output(config, "household_config")
                    st.session_state["household_config"] = config
                    st.session_state["setup_valid"] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Configuration error: {e}")

    with tab2:
        uploaded_file = st.file_uploader("Upload household_config.json", type=["json"])
        if uploaded_file is not None:
            import json
            from paystub_analyzer.utils.migration import migrate_household_config
            from paystub_analyzer.utils.contracts import validate_output

            try:
                cfg = migrate_household_config(json.load(uploaded_file))
                validate_output(cfg, "household_config")
                st.success("Valid configuration loaded!")

                if st.button("Use this configuration", type="primary"):
                    st.session_state["household_config"] = cfg
                    st.session_state["setup_valid"] = True
                    st.rerun()
            except Exception as e:
                st.error(f"Invalid configuration file: {e}")


def main() -> None:
    st.set_page_config(page_title="Paystub Truth Check", page_icon="📄", layout="wide")
    reset_session_if_schema_changed()
    apply_theme()
    st.markdown("<div class='app-topline-title'>Paystub Truth Check</div>", unsafe_allow_html=True)

    st.markdown(
        (
            "<div class='app-intro'>"
            "<p>Cross-verify latest paystub YTD values against your W-2 with evidence lines.</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if not st.session_state.get("setup_valid"):
        render_setup_wizard()
        st.stop()

    household_config = st.session_state["household_config"]
    year = int(household_config.get("filing_year", 2025))

    with st.sidebar:
        st.header("Run Settings")
        render_scale = st.slider("OCR render scale", min_value=2.0, max_value=4.0, value=2.8, step=0.1)
        tolerance = Decimal(str(st.number_input("Comparison tolerance", min_value=0.0, value=0.01, step=0.01)))

        filers_list = [f["id"] for f in household_config["filers"]]
        household_mode = len(filers_list) > 1

        selected_filer = st.selectbox("Select Filer View", filers_list)
        st.session_state["active_filer_id"] = selected_filer

        st.divider()
        if st.button("Edit Household Setup", type="secondary"):
            st.session_state["setup_valid"] = False
            clear_workflow_state()
            # Strict UI namespace isolation on wizard edit
            for key in list(st.session_state.keys()):
                if isinstance(key, str) and (
                    key.startswith("filer_")
                    or key
                    in [
                        "snapshot",
                        "w2_validation",
                        "annual_packet",
                        "household_package",
                        "corrections",
                    ]
                ):
                    del st.session_state[key]
            st.rerun()

    active_filer_id = st.session_state["active_filer_id"]
    active_filer_cfg = next((f for f in household_config["filers"] if f["id"] == active_filer_id), None)
    paystubs_dir_str = active_filer_cfg["sources"]["paystubs_dir"] if active_filer_cfg else "pay_statements"
    paystubs_dir = Path(paystubs_dir_str)

    files = list_paystub_files(paystubs_dir, int(year))
    if not files:
        st.error(f"No PDFs found in `{paystubs_dir}` for year `{year}`.")
        return

    latest_file, latest_date = select_latest_paystub(files)
    prior_snapshot = st.session_state.get("snapshot")
    prior_w2_validation = st.session_state.get("w2_validation")
    prior_packet = st.session_state.get("annual_packet")

    step1_complete = prior_snapshot is not None
    step2_complete = prior_w2_validation is not None
    step3_complete = prior_packet is not None

    step2_needs_review = False
    if isinstance(prior_w2_validation, dict):
        summary = cast(dict[str, Any], prior_w2_validation.get("comparison_summary", {}))
        step2_needs_review = summary.get("mismatch", 0) > 0 or summary.get("review_needed", 0) > 0
    step2_marked_completed = step2_complete and not step2_needs_review

    step3_needs_review = False
    if isinstance(prior_packet, dict):
        packet_summary = cast(dict[str, Any], prior_packet)
        critical_count = sum(
            1
            for issue in packet_summary.get("consistency_issues", [])
            if isinstance(issue, dict) and issue.get("severity") == "critical"
        )
        step3_needs_review = critical_count > 0 or not bool(packet_summary.get("ready_to_file"))

    if not step1_complete:
        active_step = 1
    elif not step2_marked_completed:
        active_step = 2
    else:
        active_step = 3

    workflow_steps: list[dict[str, Any]] = [
        {
            "title": "Step 1: Extract Payslip Values",
            "state": "Completed" if step1_complete else "In progress",
            "active": active_step == 1,
        },
        {
            "title": "Step 2: Compare With W-2",
            "state": (
                "Locked"
                if not step1_complete
                else "Needs review"
                if step2_complete and step2_needs_review
                else "Completed"
                if step2_complete
                else "In progress"
            ),
            "active": active_step == 2,
        },
        {
            "title": "Step 3: Build Filing Packet",
            "state": (
                "Locked"
                if not step2_marked_completed
                else "Needs review"
                if step3_complete and step3_needs_review
                else "Completed"
                if step3_complete
                else "In progress"
            ),
            "active": active_step == 3,
        },
    ]
    render_workflow_steps(workflow_steps)
    st.markdown("### Run Summary")
    render_run_summary(int(year), len(files))

    render_step_heading(
        1,
        "Extract Payslip Values",
        "Run OCR extraction to capture YTD taxes and evidence lines from your selected payslip scope.",
    )
    with st.container():
        active_filer_id = str(st.session_state.get("active_filer_id", "primary"))
        manual_pay_date_overrides: dict[str, str] = {}
        analysis_scope = st.radio(
            "Analysis Scope",
            options=["Single payslip", "All payslips in year"],
            horizontal=True,
            key="analysis_scope_choice",
        )
        prior_scope = st.session_state.get("_analysis_scope_last")
        if prior_scope is None:
            st.session_state["_analysis_scope_last"] = analysis_scope
        elif analysis_scope != prior_scope:
            clear_workflow_state()
            st.session_state["_analysis_scope_last"] = analysis_scope
            st.session_state["_w2_upload_version"] = int(st.session_state.get("_w2_upload_version", 0)) + 1
            st.rerun()

        selected = str(latest_file)
        if analysis_scope == "Single payslip":
            selected = st.selectbox(
                "Select payslip to extract",
                options=[str(path) for path in files],
                index=[str(path) for path in files].index(str(latest_file)),
            )
        else:
            st.caption("Year mode will process every payslip in this folder/year and show a full-year summary.")
            with st.expander("Optional: Manual Pay-Date Overrides", expanded=False):
                st.caption("Use this when a revised payslip should count toward a different pay cycle.")
                manual_pay_date_overrides = render_pay_date_override_editor(
                    filer_id=active_filer_id,
                    files=files,
                    tax_year=int(year),
                )

    extract_button_type: ButtonKind = "primary" if active_step == 1 else "secondary"
    with st.container():
        st.caption("Run extraction to parse OCR values and refresh confidence checks.")
        if st.button("Run Extraction", type=extract_button_type):
            start_perf = time.perf_counter()
            run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with st.spinner("Running OCR extraction and consistency checks..."):
                    if analysis_scope == "All payslips in year":
                        # v0.3.0 Household Analysis
                        if household_mode and household_config:
                            # Define loaders for household orchestrator
                            def ui_snapshot_loader(src_config: dict[str, Any]) -> list[PaystubSnapshot]:
                                sub_dir = Path(src_config.get("paystubs_dir", "."))
                                full_path = sub_dir if sub_dir.is_absolute() else paystubs_dir / sub_dir
                                return collect_annual_snapshots(
                                    paystubs_dir=full_path,
                                    year=int(year),
                                    render_scale=render_scale,
                                    psm=6,
                                )

                            def ui_w2_loader(src_config: dict[str, Any]) -> dict[str, Any] | None:
                                # v0.3.0 TODO: Implement W-2 loader for UI if needed.
                                # For now, UI relies on separate Step 2 for W-2s, or we can scan w2_files?
                                # Let's return None to keep this "Extraction Only" step safe.
                                return None

                            if build_household_package is None:
                                st.error(
                                    "Household mode requires `build_household_package` in "
                                    "`paystub_analyzer.annual`. Please update/reinstall the package."
                                )
                                return
                            household_kwargs: dict[str, Any] = {
                                "household_config": household_config,
                                "tax_year": int(year),
                                "snapshot_loader": ui_snapshot_loader,
                                "w2_loader": ui_w2_loader,
                                "tolerance": tolerance,
                            }
                            if supports_kwarg(build_household_package, "corrections"):
                                household_kwargs["corrections"] = st.session_state.get("corrections", {})

                            all_pay_date_overrides = cast(
                                dict[str, dict[str, str]],
                                st.session_state.get("pay_date_overrides", {}),
                            )
                            if supports_kwarg(build_household_package, "pay_date_overrides"):
                                household_kwargs["pay_date_overrides"] = all_pay_date_overrides
                            elif any(all_pay_date_overrides.values()):
                                st.warning(
                                    "Manual pay-date overrides require a newer backend version. "
                                    "Overrides were ignored for this run."
                                )

                            annual_result = build_household_package(**household_kwargs)
                            # annual_result has {"report": ..., "filers_analysis": [...]}

                        else:
                            # Legacy Single Filer (wrapped to match household structure)
                            annual_snapshots = collect_annual_snapshots(
                                paystubs_dir=paystubs_dir,
                                year=int(year),
                                render_scale=render_scale,
                                psm=6,
                            )
                            if not annual_snapshots:
                                st.error("No paystubs found for full-year analysis.")
                                return
                            # Use legacy builder but ensure we get analysis result
                            # build_tax_filing_package computes analysis but returns specific flat dict
                            # We can just call analyze_filer directly or reconstruct?
                            # Let's call build_tax_filing_package and inspect.
                            package_kwargs: dict[str, Any] = {
                                "tax_year": int(year),
                                "snapshots": annual_snapshots,
                                "tolerance": tolerance,
                                "w2_data": None,  # /st.session_state.get("w2_data")?
                            }
                            if supports_kwarg(build_tax_filing_package, "pay_date_overrides"):
                                package_kwargs["pay_date_overrides"] = manual_pay_date_overrides
                            elif manual_pay_date_overrides:
                                st.warning(
                                    "Manual pay-date overrides require a newer backend version. "
                                    "Overrides were ignored for this run."
                                )

                            legacy_result = build_tax_filing_package(**package_kwargs)
                            report_payload = (
                                legacy_result["report"]
                                if isinstance(legacy_result, dict) and "report" in legacy_result
                                else legacy_result
                            )
                            if not isinstance(report_payload, dict) or "filers" not in report_payload:
                                raise KeyError("report")

                            fallback_snapshot = annual_snapshots[-1]
                            fallback_meta = {
                                "paystub_count_raw": len(annual_snapshots),
                                "paystub_count_canonical": len(annual_snapshots),
                                "latest_pay_date": fallback_snapshot.pay_date,
                                "latest_paystub_file": fallback_snapshot.file,
                                "extracted": snapshot_to_dict(fallback_snapshot),
                            }
                            legacy_meta = legacy_result.get("meta", {}) if isinstance(legacy_result, dict) else {}
                            analysis_meta = {**fallback_meta, **legacy_meta}
                            legacy_ledger = legacy_result.get("ledger", []) if isinstance(legacy_result, dict) else []
                            legacy_raw_ledger = (
                                legacy_result.get("raw_ledger", legacy_ledger)
                                if isinstance(legacy_result, dict)
                                else []
                            )

                            # Convert legacy to unified structure
                            # legacy_result: {report, ledger, meta}
                            # Construct a fake "analysis" object
                            analysis_obj = {
                                "public": report_payload["filers"][0],
                                "internal": {
                                    "ledger": legacy_ledger,
                                    "raw_ledger": legacy_raw_ledger,
                                    "meta": analysis_meta,
                                },
                            }
                            annual_result = {"report": report_payload, "filers_analysis": [analysis_obj]}

                            snapshot = fallback_snapshot
                            st.session_state["snapshot"] = snapshot

                        st.session_state["annual_summary_preview"] = annual_result
                        st.session_state["analysis_scope"] = "all_year"
                        preview_meta = annual_result["filers_analysis"][0]["internal"]["meta"]
                        preview_paystub_count = int(preview_meta.get("paystub_count_raw", 0))
                        source_file = (
                            "Household Analysis" if household_mode else f"ALL ({preview_paystub_count} payslips)"
                        )
                        raw_count = 0 if household_mode else preview_paystub_count

                    else:
                        file_hash = _hash_file(Path(selected))
                        snapshot = get_cached_paystub_snapshot(str(selected), file_hash, render_scale)
                        st.session_state["snapshot"] = snapshot
                        st.session_state.pop("annual_summary_preview", None)
                        st.session_state["analysis_scope"] = "single"
                        source_file = selected
                        raw_count = 1
                quality = build_extraction_quality(snapshot)
                duration = round(time.perf_counter() - start_perf, 2)
                st.session_state["extract_quality"] = quality
                st.session_state["extract_run_meta"] = {
                    "timestamp": run_timestamp,
                    "duration_s": duration,
                    "status": "Completed",
                    "scope": analysis_scope,
                    "source_file": source_file,
                    "paystub_count": raw_count,
                }
                st.session_state.pop("w2_validation", None)
                st.session_state.pop("annual_packet", None)
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                duration = round(time.perf_counter() - start_perf, 2)
                st.session_state["extract_run_meta"] = {
                    "timestamp": run_timestamp,
                    "duration_s": duration,
                    "status": "Failed",
                    "error": str(exc),
                }
                st.error(f"Extraction failed: {exc}")
                return

    snapshot_data = st.session_state.get("snapshot")
    if snapshot_data is None:
        st.info("Click 'Run Extraction' to begin.")
        return
    snapshot = cast(PaystubSnapshot, snapshot_data)

    active_scope = st.session_state.get("analysis_scope", "single")
    extracted = snapshot_to_dict(snapshot)

    # Helper for safe state summing
    def safe_sum_state_ytd(state_data: dict[str, Any]) -> Decimal:
        total = Decimal("0.00")
        for state_val in state_data.values():
            val = None
            # Handle if state_val is AmountPair object or dict
            if hasattr(state_val, "ytd"):
                val = state_val.ytd
            elif isinstance(state_val, dict):
                val = state_val.get("ytd")
            else:
                val = state_val  # Assume scalar or Decimal

            if val is not None:
                total += Decimal(str(val))
        return total

    state_total = safe_sum_state_ytd(snapshot.state_income_tax)

    quality_data = cast(dict[str, Any], st.session_state.get("extract_quality", {}))
    if not quality_data:
        quality_data = build_extraction_quality(snapshot)
        st.session_state["extract_quality"] = quality_data

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Federal Tax YTD", format_money(snapshot.federal_income_tax.ytd))
    with m2:
        metric_card("State Tax YTD (Total)", format_money(state_total))
    with m3:
        metric_card("Social Security YTD", format_money(snapshot.social_security_tax.ytd))
    with m4:
        metric_card("Medicare YTD", format_money(snapshot.medicare_tax.ytd))

    render_extraction_quality_panel(quality_data)

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
        app_annual_result = cast(dict[str, Any] | None, st.session_state.get("annual_summary_preview"))
        if app_annual_result:
            # v0.3.0 Multi-Filer Rendering
            active_filer_id = str(st.session_state.get("active_filer_id", "primary"))
            filers_analysis = cast(list[dict[str, Any]], app_annual_result.get("filers_analysis", []))

            # Find the analysis for active filer
            target_analysis = next((f for f in filers_analysis if f["public"]["id"] == active_filer_id), None)
            if not target_analysis and filers_analysis:
                target_analysis = filers_analysis[0]

            if target_analysis:
                public = target_analysis["public"]
                internal = target_analysis["internal"]
                meta = internal["meta"]
                extracted = meta["extracted"]
                state_total = safe_sum_state_ytd(extracted["state_income_tax"])  # re-sum from extracted dict

                st.markdown(f"### Whole-Year Summary: {public['id'].title()} ({public['role']})")

                # Corrections UI
                with st.expander("Values Verification & Corrections"):
                    st.info("Overrides applied here will be reflected in the final filing package.")

                    existing_corrections = st.session_state.get("corrections", {}).get(active_filer_id, {})
                    editor_rows = []
                    for k, v in existing_corrections.items():
                        editor_rows.append(
                            {
                                "Field": k,
                                "Value": float(v.get("value", 0.0)),
                                "Reason": v.get("audit_reason", "Manual UI Override"),
                            }
                        )

                    import pandas as pd

                    df_corrections = pd.DataFrame(editor_rows, columns=["Field", "Value", "Reason"])
                    if df_corrections.empty:
                        # Start with one empty row to make the UI obvious
                        df_corrections = pd.DataFrame(
                            [{"Field": None, "Value": None, "Reason": ""}], columns=["Field", "Value", "Reason"]
                        )

                    allowed_fields = [
                        "box1",
                        "box2",
                        "box3",
                        "box4",
                        "box5",
                        "box6",
                    ]
                    states = [
                        "AL",
                        "AK",
                        "AZ",
                        "AR",
                        "CA",
                        "CO",
                        "CT",
                        "DE",
                        "FL",
                        "GA",
                        "HI",
                        "ID",
                        "IL",
                        "IN",
                        "IA",
                        "KS",
                        "KY",
                        "LA",
                        "ME",
                        "MD",
                        "MA",
                        "MI",
                        "MN",
                        "MS",
                        "MO",
                        "MT",
                        "NE",
                        "NV",
                        "NH",
                        "NJ",
                        "NM",
                        "NY",
                        "NC",
                        "ND",
                        "OH",
                        "OK",
                        "OR",
                        "PA",
                        "RI",
                        "SC",
                        "SD",
                        "TN",
                        "TX",
                        "UT",
                        "VT",
                        "VA",
                        "WA",
                        "WV",
                        "WI",
                        "WY",
                    ]
                    for s in states:
                        allowed_fields.append(f"state_income_tax_{s}")

                    edited_df = st.data_editor(
                        df_corrections,
                        column_config={
                            "Field": st.column_config.SelectboxColumn(
                                "Override Field",
                                help="Select the exact W-2 Box (e.g., box1 for Wages, box2 for FIT) or state tax key",
                                options=allowed_fields,
                                required=True,
                            ),
                            "Value": st.column_config.NumberColumn(
                                "Corrected YTD", min_value=0.0, step=0.01, format="$%.2f", required=True
                            ),
                            "Reason": st.column_config.TextColumn("Audit Reason", required=True),
                        },
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        key=f"corrections_editor_{active_filer_id}_{st.session_state.get('_run_id', 0)}",
                    )

                    if st.button("Apply Corrections", key=f"apply_corrections_{active_filer_id}", type="primary"):
                        if "corrections" not in st.session_state:
                            st.session_state["corrections"] = {}

                        new_corrections = {}
                        for idx, row in edited_df.iterrows():
                            field = row.get("Field")
                            val = row.get("Value")
                            reason = row.get("Reason")

                            if not field or pd.isna(val) or pd.isna(field):
                                continue

                            try:
                                val_float = float(val)
                            except (ValueError, TypeError):
                                continue

                            if pd.isna(reason) or str(reason).strip() == "":
                                reason = "Manual UI Override"

                            new_corrections[str(field)] = {"value": val_float, "audit_reason": str(reason).strip()}

                        if new_corrections != existing_corrections:
                            st.session_state["corrections"][active_filer_id] = new_corrections
                            st.rerun()

                y1, y2, y3, y4 = st.columns(4)
                with y1:
                    metric_card("Paystubs (Canonical)", str(meta["paystub_count_canonical"]))
                with y2:
                    metric_card(
                        "Gross Pay YTD",
                        format_money(Decimal(str(extracted["gross_pay"]["ytd"] or 0))),
                    )
                with y3:
                    metric_card(
                        "Federal Tax YTD",
                        format_money(Decimal(str(extracted["federal_income_tax"]["ytd"] or 0))),
                    )
                with y4:
                    metric_card("State Tax YTD Total", format_money(state_total))

                st.caption(
                    f"Raw paystub files processed: {meta['paystub_count_raw']} | "
                    f"Latest pay date: {meta['latest_pay_date']}"
                )

                merge_audit_flags = [
                    issue.get("message", "")
                    for issue in cast(list[dict[str, Any]], meta.get("consistency_issues", []))
                    if issue.get("code") in {"pay_date_override_applied", "duplicate_pay_date"}
                ]
                if merge_audit_flags:
                    with st.expander("Merge / Canonicalization Audit", expanded=False):
                        for message in merge_audit_flags:
                            st.markdown(f"- {message}")

                # Ledger Rendering (using internal ledger)
                st.markdown("#### Per-Payslip Year Ledger")
                ledger_view_mode = st.radio(
                    "Ledger View",
                    options=[
                        "Canonical (used for calculations)",
                        "Raw (all uploaded files)",
                    ],
                    horizontal=True,
                    key=f"ledger_view_{active_filer_id}_{year}",
                )
                if ledger_view_mode.startswith("Raw"):
                    ledger_rows = cast(
                        list[dict[str, Any]],
                        internal.get("raw_ledger", internal["ledger"]),
                    )
                    ledger_df = build_ledger_display_df(ledger_rows, include_calc_columns=True)
                else:
                    ledger_df = build_ledger_display_df(cast(list[dict[str, Any]], internal["ledger"]))

                correction_trace = public.get("correction_trace", [])

                if not ledger_df.empty:
                    if correction_trace:
                        st.markdown(f"#### ⚠️ {len(correction_trace)} Correction(s) Applied")
                        # Emphasize that the ledger is raw but final output is corrected
                        st.caption(
                            "The ledger below represents raw OCR values. The final package has been explicitly overridden for the following fields:"
                        )
                        trace_data = []
                        for t in correction_trace:
                            trace_data.append(
                                {
                                    "Field": t.get("corrected_field"),
                                    "Original Value": float(t.get("original_value") or 0.0),
                                    "Corrected Value": float(t.get("corrected_value") or 0.0),
                                    "Reason": t.get("reason"),
                                    "Timestamp": str(t.get("timestamp"))[:19].replace("T", " "),
                                }
                            )
                        import pandas as pd

                        t_df = pd.DataFrame(trace_data)
                        st.dataframe(
                            t_df.style.set_properties(**{"background-color": "#fffbea"}),
                            use_container_width=True,
                            hide_index=True,
                        )
                    st.dataframe(ledger_df, use_container_width=True, hide_index=True)

                # Markdown Report Preview
                st.markdown("#### Filing Packet Preview")
                # We can generate markdown for just this filer or the whole household?
                # package_to_markdown takes the whole package.
                # So we can show the full markdown.
                md = package_to_markdown(app_annual_result["report"])
                st.download_button("Download Packet (Markdown)", md, file_name="filing_packet.md")
                with st.expander("View Full Report"):
                    st.markdown(md)

    st.markdown("### Extracted State Details")
    state_rows = build_state_detail_rows(snapshot)
    state_df = pd.DataFrame(state_rows)
    st.dataframe(
        state_df.style.set_properties(
            subset=[col for col in ["This Period", "YTD"] if col in state_df.columns],
            **{"text-align": "right", "font-family": "'JetBrains Mono', monospace"},
        ),
        use_container_width=True,
        hide_index=True,
    )

    evidence_rows = collect_evidence_lines(extracted)
    with st.expander(f"Evidence lines ({len(evidence_rows)})", expanded=False):
        if evidence_rows:
            evidence_df = pd.DataFrame([{"Field": key, "Evidence": line} for key, line in evidence_rows])
            st.dataframe(evidence_df, use_container_width=True, hide_index=True)
        else:
            st.info("No evidence lines were captured for this extraction.")

    step2_button_type: ButtonKind = "primary" if active_step == 2 else "secondary"
    render_step_heading(
        2,
        "W-2 Comparison",
        "Auto-fill or enter W-2 values and run a strict field-by-field comparison against the extracted payslip totals.",
    )
    upload_version = int(st.session_state.get("_w2_upload_version", 0))
    uploaded = st.file_uploader(
        "Upload W-2 JSON or PDF (optional)",
        type=["json", "pdf"],
        key=f"w2_upload_{upload_version}",
    )
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
                file_hash = _hash_file(temp_path)
                w2_data = get_cached_w2_payload(
                    pdf_path_str=str(temp_path),
                    file_hash=file_hash,
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
        submitted = st.form_submit_button("Run W-2 Comparison", type=step2_button_type)

    selected_w2 = manual_w2
    if submitted:
        comparisons, summary = compare_snapshot_to_w2(snapshot, selected_w2, tolerance)
        payload = {
            "tax_year": int(year),
            "latest_paystub_file": snapshot.file,
            "latest_pay_date": snapshot.pay_date or latest_date.isoformat(),
            "extracted": extracted,
            "w2_input": selected_w2,
            "comparisons": comparisons,
            "comparison_summary": summary,
        }
        st.session_state["w2_validation"] = payload
        st.session_state.pop("annual_packet", None)
        st.rerun()

    w2_validation_data = st.session_state.get("w2_validation")
    if w2_validation_data:
        validation_payload = cast(dict[str, Any], w2_validation_data)
        comparison_summary = cast(dict[str, Any], validation_payload.get("comparison_summary", {}))
        comparison_rows = cast(list[dict[str, Any]], validation_payload.get("comparisons", []))

        c1, c2, c3 = st.columns(3)
        c1.metric("Matches", comparison_summary.get("match", 0))
        c2.metric("Mismatches", comparison_summary.get("mismatch", 0))
        c3.metric("Review Needed", comparison_summary.get("review_needed", 0))

        st.markdown("#### Comparison Results")
        st.caption("Columns: Field, Paystub, W-2, Difference, Status, Flag")
        comparison_df = build_comparison_display_df(comparison_rows)
        st.dataframe(
            style_flagged_rows(
                comparison_df,
                "Flag",
                right_align_columns=["Paystub", "W-2", "Difference"],
            ),
            use_container_width=True,
            hide_index=True,
        )

        dl_json_col, dl_md_col, _ = st.columns([1, 1, 2], gap="small")
        with dl_json_col:
            st.download_button(
                "Download Validation (JSON)",
                data=json.dumps(validation_payload, indent=2),
                file_name="w2_validation_ui.json",
                mime="application/json",
            )
        with dl_md_col:
            st.download_button(
                "Download Validation (.md)",
                data=build_report_markdown(validation_payload),
                file_name="w2_validation_ui.md",
                mime="text/markdown",
            )
        if step2_needs_review:
            st.warning("Step 3 remains locked until Step 2 is marked Completed (no mismatches / review-needed flags).")

    if step2_marked_completed:
        st.markdown("---")
        render_step_heading(
            3,
            "Filing Packet",
            "Generate annual ledger artifacts, run filing checks, and produce exportable validation outputs.",
        )

        include_w2 = st.checkbox(
            "Include W-2 comparison in annual packet",
            value=True,
            help="Disable this to build the packet from paystubs only.",
        )
        if include_w2:
            st.caption("Checkbox ON: annual packet includes W-2 match/mismatch checks and influences Ready To File.")
        else:
            st.caption("Checkbox OFF: annual packet is paystub-only (no W-2 comparison), useful for extraction QA.")
        can_build_packet = st.session_state.get("w2_validation") is not None

        build_button_type: ButtonKind = "primary" if active_step == 3 else "secondary"
        build_col, info_col = st.columns([0.86, 0.14], gap="small")
        with build_col:
            build_packet_clicked = st.button(
                "Build Filing Packet",
                type=build_button_type,
                disabled=not can_build_packet,
            )
        with info_col:
            with st.popover("i", use_container_width=False):
                st.markdown("**Build Filing Packet details**")
                st.markdown(
                    "- Processes all payslips for the selected tax year.\n"
                    "- Applies YTD verification checks and consistency rules.\n"
                    "- Generates downloadable JSON, Markdown, and CSV artifacts.\n"
                    "- Includes W-2 checks when the checkbox is enabled."
                )

        if build_packet_clicked:
            # Use st.session_state["household_config"] as the SSOT
            household_cfg = st.session_state["household_config"]

            def packet_snapshot_loader(source_cfg: dict[str, Any]) -> list[PaystubSnapshot]:
                p_dir = Path(source_cfg["paystubs_dir"])
                return collect_annual_snapshots(
                    paystubs_dir=p_dir,
                    year=int(year),
                    render_scale=render_scale,
                    psm=6,
                )

            def packet_w2_loader(source_cfg: dict[str, Any]) -> dict[str, Any] | None:
                # If this is the active filer AND we have a W-2 session state for them, use it
                f_id = next((f["id"] for f in household_cfg["filers"] if f["sources"] == source_cfg), None)
                if f_id == st.session_state.get("active_filer_id"):
                    w2_val = st.session_state.get("w2_validation")
                    if w2_val:
                        return cast(dict[str, Any], w2_val.get("w2_input"))

                # Fallback to config-defined w2_files if present
                w2_files = source_cfg.get("w2_files", [])
                if w2_files:
                    from paystub_analyzer.w2_aggregator import load_and_aggregate_w2s

                    return load_and_aggregate_w2s(w2_files, Path.cwd(), int(year), render_scale)
                return None

            corrections_payload = st.session_state.get("corrections", {})
            packet_pay_date_overrides = cast(
                dict[str, dict[str, str]],
                st.session_state.get("pay_date_overrides", {}),
            )

            packet = build_household_package(
                household_config=household_cfg,
                tax_year=int(year),
                snapshot_loader=packet_snapshot_loader,
                w2_loader=packet_w2_loader,
                tolerance=tolerance,
                corrections=corrections_payload,
                pay_date_overrides=packet_pay_date_overrides,
            )
            st.session_state["annual_packet"] = packet
            st.rerun()

        packet_data = st.session_state.get("annual_packet")
        current_packet = None
        if packet_data:
            current_packet = cast(dict[str, Any], packet_data)

        if current_packet:
            # If it's a household report (contains 'report' key from build_household_package)
            report = current_packet.get("report", current_packet)
            summary = report.get("household_summary", {})
            metadata = report.get("metadata", {})
            filers = report.get("filers", [])

            p1, p2, p3, p4 = st.columns(4)
            if summary:
                # Household aggregate metrics
                p1.metric("Total Gross Pay", format_money(Decimal(summary.get("total_gross_pay_cents", 0)) / 100))
                p2.metric("Total Fed Tax", format_money(Decimal(summary.get("total_fed_tax_cents", 0)) / 100))
                p3.metric("Ready To File", str(summary.get("ready_to_file", False)))

                all_issues = []
                total_canonical = 0
                for f in filers:
                    all_issues.extend(f.get("consistency_issues", []))
                    total_canonical += f.get("paystub_count_canonical", 0)  # Fallback if missing
                    # Note: count_canonical/raw are often in meta, but we might have flattened some in public
                    # If not in public, we sum what we have.

                critical_count = sum(1 for issue in all_issues if issue.get("severity") == "critical")
                p4.metric("Total Critical Issues", critical_count)

                st.caption(
                    f"Household: {metadata.get('state', 'Unknown')} | "
                    f"Filing Status: {metadata.get('filing_status', 'Unknown')} | "
                    f"Year: {metadata.get('filing_year', 'Unknown')}"
                )
            else:
                # Legacy single-filer fallback metrics
                p1.metric("Paystubs (Canonical)", current_packet.get("paystub_count_canonical", 0))
                p2.metric("Authenticity Score", current_packet.get("authenticity_assessment", {}).get("score", 0))
                p3.metric("Ready To File", str(current_packet.get("ready_to_file", False)))
                critical_count = sum(
                    1 for issue in current_packet.get("consistency_issues", []) if issue.get("severity") == "critical"
                )
                p4.metric("Critical Issues", critical_count)
                st.caption(f"Raw paystub files analyzed: {current_packet.get('paystub_count_raw', 0)}")

            blockers: list[str] = []
            if summary:
                if not summary.get("ready_to_file"):
                    blockers.append("Household package is not ready to file.")
            else:
                if critical_count > 0:
                    blockers.append(f"{critical_count} critical consistency issue(s) must be resolved.")
                if not bool(current_packet.get("ready_to_file")):
                    blockers.append("Packet is currently marked not ready to file.")

            # Unified decision UI
            st.markdown("#### Filing Decision")
            if blockers:
                st.error("Step 3 decision: NOT READY TO FILE")
                for blocker in blockers:
                    st.markdown(f"- {blocker}")
            else:
                st.success("Step 3 decision: READY TO FILE")

            if summary:
                st.markdown("#### Multi-Filer Consistency Summary")
                for f in filers:
                    fid = f"{f['id']} ({f['role']})"
                    f_issues = f.get("consistency_issues", [])
                    if not f_issues:
                        st.write(f"✅ **{fid}**: No issues detected.")
                    else:
                        st.write(f"⚠️ **{fid}**: {len(f_issues)} issue(s)")
                        for issue in f_issues:
                            prefix = "[CRITICAL]" if issue.get("severity") == "critical" else "[WARNING]"
                            st.markdown(f"  - {prefix} `{issue.get('code')}`: {issue.get('message')}")
            else:
                st.markdown("#### Consistency Issues")
                issues = current_packet.get("consistency_issues", [])
                if not issues:
                    st.success("No consistency issues detected.")
                else:
                    for issue in issues:
                        prefix = "[CRITICAL]" if issue.get("severity") == "critical" else "[WARNING]"
                        st.markdown(f"- {prefix} `{issue.get('code')}`: {issue.get('message')}")

            st.markdown("#### Filing Checklist")
            for item in current_packet["filing_checklist"]:
                st.markdown(f"- **{item['item']}**: {item['detail']}")

            st.markdown("#### Annual Ledger")
            packet_ledger_df = build_ledger_display_df(cast(list[dict[str, Any]], current_packet["ledger"]))
            st.dataframe(
                style_flagged_rows(
                    packet_ledger_df,
                    "YTD Verification",
                    right_align_columns=[
                        "Gross YTD",
                        "Federal YTD",
                        "SS YTD",
                        "Medicare YTD",
                        "State YTD Total",
                    ],
                ),
                use_container_width=True,
                hide_index=True,
            )
            packet_ytd_flagged = packet_ledger_df[packet_ledger_df["YTD Verification"] != "—"]
            if not packet_ytd_flagged.empty:
                st.warning(
                    "YTD verification flags were found in this filing packet. Check the rows below before filing."
                )
                st.dataframe(packet_ytd_flagged, use_container_width=True, hide_index=True)

            packet_json = json.dumps(current_packet, indent=2)
            packet_md = package_to_markdown(current_packet)
            packet_csv = ledger_to_csv(current_packet["ledger"])
            st.download_button(
                "Download Filing Packet (JSON)",
                data=packet_json,
                file_name=f"tax_filing_package_{int(year)}.json",
                mime="application/json",
            )
            st.download_button(
                "Download Filing Packet (Markdown)",
                data=packet_md,
                file_name=f"tax_filing_package_{int(year)}.md",
                mime="text/markdown",
            )
            st.download_button(
                "Download Annual Ledger (CSV)",
                data=packet_csv,
                file_name=f"paystub_ledger_{int(year)}.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
