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
- Spouse paystubs (recommended): `pay_statements/spouse`
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
- Applies continuity-gated zero-period YTD promotion (for unpaid-leave style stubs where tax values are shown once as YTD).
- Auto-repairs gross this-period values when OCR swaps in cumulative totals (uses YTD continuity delta and audit flags).
- Filters implausible OCR money tokens and records `implausible_amount_filtered` parse anomalies for audit review.
- Produces a tax filing packet (JSON + Markdown + ledger CSV).
- Provides a Streamlit UI for interactive review.

## Prerequisites

1. Install dependencies:

```bash
pip install -e ".[dev]"
```

2. Ensure `tesseract` is installed and available in `PATH`.

## CLI Usage

### 1) Analyze Paystub Taxes (`paystub-analyze`)

Single file:

```bash
paystub-analyze "pay_statements/Pay Date 2025-01-15.pdf"
```

All files in folder:

```bash
paystub-analyze --default-folder pay_statements
```

JSON output:

```bash
paystub-analyze --default-folder pay_statements --json
```

### 2) Validate Against W-2 (`paystub-w2`)

Create template:

```bash
paystub-w2 \
  --write-w2-template w2_forms/w2_template_2025.json \
  --paystubs-dir pay_statements \
  --year 2025
```

Template state boxes are auto-populated from states detected in the latest paystub for that year.

Extraction-only run:

```bash
paystub-w2 --paystubs-dir pay_statements --year 2025
```

Extraction + W-2 comparison:

```bash
paystub-w2 \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-json w2_forms/w2_2025.json
```

Extraction + W-2 **PDF** comparison (OCR):

```bash
paystub-w2 \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-pdf w2_forms/W2_2025_Sasie_Redacted.pdf \
  --w2-render-scale 3.0
```

Outputs:

- `reports/w2_validation.md`
- `reports/w2_validation.json`

### 3) Build Annual Filing Packet (`paystub-annual`)

```bash
paystub-annual \
  --paystubs-dir pay_statements \
  --year 2025 \
  --w2-json w2_forms/w2_2025.json
```

or with W-2 PDF directly:

```bash
paystub-annual \
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

### Household Filing (v0.3.0 & v0.4.0)

> [!NOTE]
> **v0.4.0 Scope Note**: Any newly collected household properties such as `filing_year`, `state`, and `filing_status` are currently treated as **metadata only**. They are included in the output packets for completeness but do not currently alter the internal tax calculation or comparison math.

Analyze multiple filers (Primary + Optional Spouse) together. Supports **multiple W-2s** per filer with strict deduplication.

**Configuration (`household_config.json`):**

```json
{
  "version": "0.4.0",
  "household_id": "smith_family_2025",
  "filers": [
    {
      "id": "jane",
      "role": "PRIMARY",
      "sources": {
        "paystubs_dir": "docs/jane/paystubs",
        "w2_files": ["docs/jane/w2.pdf"]
      }
    },
    {
      "id": "john",
      "role": "SPOUSE",
      "sources": {
        "paystubs_dir": "docs/john/paystubs"
      }
    }
  ]
}
```

**Run:**

```bash
paystub-annual --year 2025 --household-config household_config.json
```

In the UI setup wizard, you can now set per-filer W-2 files directly. For your current layout:

- Primary paystubs: `pay_statements`
- Spouse paystubs: `pay_statements/spouse`
- Spouse W-2: `w2_forms/W2_2025_Spouse_Redacted.pdf`

**Interactive Mode:**

If you prefer prompts instead of arguments:

```bash
paystub-annual --interactive
```

### 5) Convert W-2 PDF to JSON (optional)

```bash
# Note context: standalone extraction script not exposed as CLI yet, use library or add script if needed.
# For now, paystub-w2 handles this. Removing standalone script ref to avoid confusion.
```

### 6) Freeze Local Baseline Snapshots (v0.5.1 hotfix support)

Use this to capture private regression artifacts from real files without committing sensitive data:

```bash
python scripts/freeze_baseline.py \
  --paystubs-dir pay_statements \
  --year 2025 \
  --out-dir private_notes/baseline_v0.5.0
```

Real-data mode refuses writing under `tests/fixtures/` to prevent accidental PII commits.

### Tests

Run the full test suite (requires `tesseract` installed):

```bash
pytest
```

Run only unit tests (fast, no OCR):

```bash
pytest -m unit
```

Run only CLI pipeline tests:

```bash
pytest -m e2e
```

## Notes

- Extraction uses OCR heuristics to handle mixed-column PDF text.
- `gross_pay_vs_box1_informational` is intentionally informational because Box 1 and gross pay can differ due to pre-tax treatments.
- Use W-2 as filing source-of-truth; use paystub analysis for cross-verification and anomaly detection.
- `.gitignore` excludes sensitive artifacts by default (paystub PDFs, W-2 PDFs/JSON payloads, and generated reports).

## 🔒 Dataset Security & Governance
This project follows strict PII-protection policies. Accuracy measurement and benchmarking utilizes a "Gold Dataset" stored in `tests/fixtures/gold/`.
- **Manifest Requirement**: `tests/fixtures/gold/manifest.json` MUST map every asset SHA-256 to ground-truth labels.
- **Provenance Policy**: Every benchmark asset must document its synthetic origin or redaction methodology to ensure no raw PII leak.
- **No Raw PII**: Unredacted or real-user paystubs must **never** be committed to the repository.
- **Zero-Bypass Hooks**: Pre-commit hooks enforcing PII-blocking are non-negotiable for all PRs.
