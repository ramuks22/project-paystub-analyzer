# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0-beta.1] - 2026-02-20

### Added
- **UI Data Editor Overrides**: Replaced static Gross Pay Override with embedded `st.data_editor` to allow simultaneous updates to `gross_pay`, `federal_income_tax`, `social_security_tax`, and `medicare_tax`.
- **Trace Accountability**: The system now exposes a structured `correction_trace` array describing explicit field overrides.

### Changed
- **Schema**: Output contract strongly guarantees `correction_trace` metadata is present for every filer, preventing silent data edits.
- **Reporting**: Normalized "State Tax Verification" table rules to $1.00 tolerance and explicitly tagged `MISSING (PAYSTUB)` / `MISSING (W-2)` disparities.

## [0.3.0] - 2026-02-20

### Added
- **Multi-W2 Aggregation**: Support for summing amounts from multiple W-2 forms per filer.
- **Strict Deduplication**: Logic to prevent processing the same W-2 twice (Idempotency).
- **Corrections Engine**: `corrections.json` override schema with integration into the primary computation pipeline to edit YTD amounts.
- **Real E2E Testing**: `scripts/generate_e2e_fixtures.py` and `tests/test_e2e_real.py` using `reportlab`.

### Changed
- **Schema Version**: Bumped output schema to `"0.3.0"`.
- **Output Contract**: `package.json` now includes `w2_aggregate` and `w2_sources` fields.
- **Sanitization**: Removed all hardcoded user data from `tests/test_annual.py`.

### Fixed
- **OCR State YTD Underflow**: Engine now detects when a YTD amount is lost in OCR truncation and auto-heals using previous continuity blocks.
- **Missing Correction Keys**: `box3` and `box5` mappings now natively initialize if they were not historically extracted from the paystub.
- **State Tax Nested Overrides**: Handled regex paths (`state_income_tax_[A-Z]{2}`) inside `corrections.py` to enforce state-level accuracy.
- **Validation**: Strict schema rejection and Python warnings added for "bare" `state_income_tax` keys.

## [0.2.0-alpha.2] - 2026-02-18

### Fixed
- **Type Safety**: Fixed `mypy` strictness errors in `console.py` by forcing explicit type casts on `rich` return values.

## [0.2.0-alpha.1] - 2026-02-18

### Added
- **Household Filing Support**: Process multiple filers (Primary + Optional Spouse) in a single run.
    - `paystub-annual --household-config <file>`: New argument for multi-filer analysis.
    - `household_config.json`: Strict schema for defining household members and sources.
    - Duplicate filer ID detection and source isolation.
- **Interactive Mode**: New `--interactive` flag for `paystub-annual` to prompt for missing configuration.
- **Enhanced CLI Output**: Rich text tables and panels for better readability (graceful ASCII fallback).
- **Strict W-2 Validation**:
    - Case-insensitive matching for status ("MATCH", "MISMATCH").
    - Schema-enforced `w2_files` cardinality (max 1 per filer).
- **Quality Gates**:
    - Runtime schema validation for household configuration.
    - Comprehensive unit, contract, and integration tests for household logic.

### Changed
- Refactored `annual.py` to support `analyze_filer` (single) and `build_household_package` (orchestrator).
- Updated `README.md` with Household Filing and Interactive Mode instructions.

## [0.1.0-alpha.1] - 2026-02-18

### Added
- **Docker Support**: Added `Dockerfile` for reproducible builds.
- **CLI Tools**: New consolidated CLI structure:
    - `paystub-analyze`: Single paystub analysis.
    - `paystub-annual`: Full year reconciliation.
    - `paystub-w2`: W-2 OCR and parsing.
    - `paystub-ui`: Streamlit web interface.
- **Testing**:
    - True E2E OCR test pipeline (`tests/test_e2e_ocr.py`).
    - Full unit and integration test suite (18+ tests).
- **Security & Governance**:
    - Pre-commit hooks for secrets (`gitleaks`) and sensitive file blocking.
    - `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- **UI Improvements**:
    - High-contrast accessibility theme.
    - Semantic button styling and improved alignment.
    - Fix for spinbutton focus states.

### Changed
- Replaced legacy `scripts/*.py` with installed package entry points.
- Updated `README.md` with modern installation instructions (`pip install -e`).
- Migrated from `requirements.txt` to `pyproject.toml`.

### Removed
- Deprecated standalone scripts in root directory.
