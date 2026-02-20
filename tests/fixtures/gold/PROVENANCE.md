# Gold Dataset Provenance & PII Safety

## Overview
All fixtures in `tests/fixtures/gold/` are **100% synthetic**. They were generated programmatically to benchmark extraction accuracy without exposing real user PII.

## Generator Methodology
- **Tool**: Programmatically generated via `scripts/generate_gold_fixtures.py` using the `reportlab` library.
- **Data Source**: Hardcoded templates representing common payroll layouts (ADP, Gusto, TriNet).
- **Redaction**: No redaction was performed because no original sensitive data was used. All names, values, and dates are fabricated.

## Manifest
The `manifest.json` file in this directory serves as the source of truth for ground-truth labels. It contains SHA-256 hashes (to be verified by validation scripts) and expected extraction values.

## Rules for Contributions
1. No real paystubs or W-2s may be added to this directory.
2. Every new fixture must be accompanied by an entry in `manifest.json`.
3. Preferred contribution method: Update `scripts/generate_gold_fixtures.py` to support new layouts.
