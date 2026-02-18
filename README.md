# Paystub Analyzer (W-2 Cross-Check)

> [!WARNING]
> **Status: Alpha / Personal Workflow**
> This tool is currently in an experimental state designed for a specific personal workflow. It is **not** production-ready software.
>
> **DISCLAIMER: NOT TAX ADVICE**
> This software is for educational and data extraction purposes only. It does **not** provide tax advice.
> *   **You are responsible for the accuracy of your own tax returns.**
> *   **Always treat your W-2 as the source of truth.**
> *   The extracted data may contain errors due to OCR imperfections or heuristic failures.


This project extracts tax evidence from ADP-style paystubs, cross-verifies it against W-2 values, and generates a filing packet.

Default folders:

- Paystubs: `pay_statements`
- W-2 files: `w2_forms`

## What It Does

- Extracts from paystubs:
  - Per-paystub values (this period + YTD)
  - Annual chronological ledger across all pay dates
- Extracts from latest paystub in a tax year:
  - Gross pay (YTD)
  - Federal income tax withheld (YTD)
  - Social Security tax withheld (YTD)
  - Medicare tax withheld (YTD)
  - 401(k) contribution (YTD)
  - State income tax withheld (YTD, per state)
- Stores evidence lines used for each extracted value.
- Compares extracted values with W-2 JSON inputs and reports field-level differences.
- Runs consistency checks (duplicate pay dates, YTD decreases, this-period vs YTD delta anomalies).
- Verifies parsed YTD values against calculated YTD (`previous_ytd + this_period`) during annual runs.
- Auto-corrects high-confidence OCR state-tax YTD spikes and records them in ledger column `ytd_verification`.
- Produces a tax filing packet (JSON + Markdown + ledger CSV).
- Provides a Streamlit UI for interactive review.

## Prerequisites

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Ensure `tesseract` is installed and available in `PATH`.

## CLI Usage

### 1) Analyze Paystub Taxes

Single file:

```bash
python3 scripts/analyze_payslip_taxes.py "pay_statements/Pay Date 2025-01-15.pdf"
```

All files in folder:

```bash
python3 scripts/analyze_payslip_taxes.py --default-folder pay_statements
```

JSON output:

```bash
python3 scripts/analyze_payslip_taxes.py --default-folder pay_statements --json
```

### 2) Validate Against W-2

Create template:

```bash
python3 scripts/validate_w2_with_paystubs.py \
  --write-w2-template w2_forms/w2_template_2025.json \
  --paystubs-dir pay_statements \
  --year 2025
```

Template state boxes are auto-populated from states detected in the latest paystub for that year.

Extraction-only run:

```bash
python3 scripts/validate_w2_with_paystubs.py --paystubs-dir pay_statements --year 2025
```

Extraction + W-2 comparison:

```bash
python3 scripts/validate_w2_with_paystubs.py \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-json w2_forms/w2_2025.json
```

Extraction + W-2 **PDF** comparison (OCR):

```bash
python3 scripts/validate_w2_with_paystubs.py \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-pdf w2_forms/W2_2025_Sasie_Redacted.pdf \
  --w2-render-scale 3.0
```

Outputs:

- `reports/w2_validation.md`
- `reports/w2_validation.json`

### 3) Build Annual Filing Packet (recommended for filing)

```bash
python3 scripts/build_tax_filing_package.py \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-json w2_forms/w2_2025.json
```

or with W-2 PDF directly:

```bash
python3 scripts/build_tax_filing_package.py \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-pdf w2_forms/W2_2025_Sasie_Redacted.pdf \
  --w2-render-scale 3.0
```

Outputs:

- `reports/paystub_ledger_2025.csv`
- `reports/tax_filing_package_2025.json`
- `reports/tax_filing_package_2025.md`

Ledger CSV includes `ytd_verification` to show any parsed-vs-calculated mismatches or auto-corrections detected for a row.

### 4) Convert W-2 PDF to JSON (optional)

```bash
python3 scripts/extract_w2_from_pdf.py \
  --w2-pdf w2_forms/W2_2025_Sasie_Redacted.pdf \
  --out w2_forms/w2_2025.json \
  --year 2025 \
  --render-scale 3.0
```

Annual package includes:

- `paystub_count_raw` and `paystub_count_canonical` (deduplicated by pay date)
- `consistency_issues` (warnings/critical checks)
- `authenticity_assessment` with score and verdict
- `ready_to_file` gate (true only when W-2 comparison has no mismatches and no critical extraction gaps)

## UI Usage

Run the Streamlit app:

```bash
streamlit run ui/app.py
```

UI features:

- Select analysis scope: single payslip or all payslips for the year
- Extract YTD values with evidence lines
- In all-year scope, show whole-year summary + per-payslip annual ledger in one run
- Show YTD verification flags when parsed values differ from calculated values
- View per-state tax YTD cards when multiple states are detected
- Enter W-2 values manually or upload W-2 JSON/PDF
- Auto-populate W-2 Inputs and State Boxes from uploaded W-2 JSON/PDF OCR payload
- Compare uses the visible W-2 form values (so you can upload, then adjust before running comparison)
- See match/mismatch/review-needed results
- Build annual filing packet with consistency checks
- Annual filing checkbox controls whether W-2 comparison is included in packet calculations
- Download validation and filing artifacts (JSON/Markdown/CSV)

## Parameter Guide

### OCR render scale

What it controls:

- Resolution used when converting PDF page to image before OCR.
- Higher values can improve text recognition quality but take more time.

Typical range:

- `2.0` to `4.0` (UI)
- Defaults: `2.5` or `2.8` depending on script

Examples:

- If your PDF is sharp and digital, use `2.5` for faster runs.
- If text is faint/blurred or numbers are misread, increase to `3.2` or `3.5`.
- If OCR is already stable and you want speed, reduce to `2.2`.
- For redacted/scanned W-2 PDFs, use `--w2-render-scale 3.0` or higher.

### W-2 OCR render scale

What it controls:

- OCR resolution specifically for W-2 PDF parsing (`--w2-pdf` flows).
- Kept separate from paystub OCR scale so you can tune each independently.

Examples:

- `--render-scale 2.8 --w2-render-scale 3.0`: fast paystub extraction + safer W-2 OCR.
- If W-2 PDF OCR misses values, raise to `3.2` or `3.5`.

### Comparison tolerance

What it controls:

- Dollar threshold used when matching paystub values vs W-2 values.
- Also used for parsed-vs-calculated YTD verification sensitivity in annual ledger checks.

Examples:

- Paystub federal tax: `14716.86`, W-2 federal tax: `14716.84`
- Difference: `0.02`
- With `--tolerance 0.01`: status = `mismatch`
- With `--tolerance 0.05`: status = `match`
- If a row has previous YTD `100.00`, this-period `25.00`, and parsed YTD `125.02`:
  - With `--tolerance 0.01`: YTD verification flag is raised.
  - With `--tolerance 0.05`: YTD verification passes.

Recommended starting point:

- `0.01` (strict, cents-level)
- Use `0.05` only if you need to absorb minor OCR/rounding noise and then review evidence lines.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Notes

- Extraction uses OCR heuristics to handle mixed-column PDF text.
- `gross_pay_vs_box1_informational` is intentionally informational because Box 1 and gross pay can differ due to pre-tax treatments.
- Use W-2 as filing source-of-truth; use paystub analysis for cross-verification and anomaly detection.
- `.gitignore` excludes sensitive artifacts by default (paystub PDFs, W-2 PDFs/JSON payloads, and generated reports).
