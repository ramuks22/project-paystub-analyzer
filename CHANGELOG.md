# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
