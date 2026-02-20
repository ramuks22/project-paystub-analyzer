# Project Paystub Analyzer Roadmap (v0.2.0 - v1.0.0)

**Current Baseline**: `v0.4.0` (Released 2026-02-20)

## 1. v0.2.x Stabilization (2-3 weeks)
*   **Theme**: Trusted Beta Reliability
*   **Scope**: Regression-only fixes from real usage.
*   **Deliverables**:
    *   Household flow bugfixes.
    *   Interactive CLI polish.
    *   Documentation clarifications.
*   **Exit Criteria**: Zero P0/P1 open bugs, no CI/release failures for two consecutive patch releases.

## 2. v0.3.0 Core Capability Expansion (3-5 weeks)
*   **Theme**: Complex Household Support
*   **Scope**: Multi-W2 per filer support.
*   **Deliverables**:
    *   W-2 aggregation logic.
    *   Per-filer multi-source matching.
    *   Updated discrepancy model.
*   **Exit Criteria**: Schema-valid outputs for multi-W2 scenarios and full test coverage for merge logic.

## 3. v0.4.0 Household UX Maturity (3-4 weeks)
*   **Theme**: User Experience & Independence
*   **Scope**: CLI + UI parity for household workflows.
*   **Deliverables**:
    *   Household setup UI.
    *   Per-filer breakdown screens.
    *   Clearer filing-readiness reasoning in UI.
*   **Exit Criteria**: User can complete primary+spouse flow fully in UI without CLI fallback.

## 4. v0.5.0 Data Quality Hardening (4 weeks)
*   **Theme**: Accuracy & Confidence
*   **Scope**: Reduce OCR/parser mismatch rate.
*   **Deliverables**:
    *   Better normalization heuristics.
    *   Confidence scoring.
    *   Automatic anomaly classification.
*   **Exit Criteria**: Measurable mismatch reduction on 2025 dataset (Target: <2% false mismatches).

## 5. v0.6.0 Contract and Compatibility (2-3 weeks)
*   **Theme**: Stability & Governance
*   **Scope**: Strict contract lifecycle management.
*   **Deliverables**:
    *   Schema migration docs.
    *   Contract compatibility tests across versions.
    *   Breaking-change policy automation.
*   **Exit Criteria**: Every public JSON artifact validated in CI with positive and negative contract tests.

## 6. v0.7.0 Security and Privacy Hardening (2-3 weeks)
*   **Theme**: Safety by Design
*   **Scope**: Prevent sensitive data leaks.
*   **Deliverables**:
    *   Stronger PII scanners.
    *   Release artifact checks.
    *   Redacted report mode defaults.
*   **Exit Criteria**: Secret/PII checks enforced in pre-commit and CI with zero bypass paths.

## 7. v0.8.0 Runtime and Ops Reliability (2-3 weeks)
*   **Theme**: Reproducibility
*   **Scope**: Reproducible runtime everywhere.
*   **Deliverables**:
    *   Docker smoke + OCR tests in CI.
    *   Deterministic fixtures.
    *   Environment diagnostics command.
*   **Exit Criteria**: Clean run on fresh machine/container with one command.

## 8. v0.9.0 OSS Readiness Finalization (2 weeks)
*   **Theme**: Community Scale
*   **Scope**: Contributor and maintainer scale-up.
*   **Deliverables**:
    *   Issue templates & Triage playbook.
    *   Release checklist.
    *   Support matrix.
*   **Exit Criteria**: External contributor can set up, test, and submit PR without manual help.

## 9. v1.0.0 Launch Gate
*   **Theme**: Production Ready
*   **Scope**: Stability, Trust, Maintainability.
*   **Deliverables**:
    *   Final API/schema freeze.
    *   Migration notes.
    *   Benchmarked accuracy report.
*   **Exit Criteria**: No unresolved critical bugs, all release gates green, documented support expectations.

---

## Strategic Operating Model
1.  **Release Train**: `alpha` -> `beta` -> `stable` progression.
2.  **Schema Policy**: Treat every schema change as a product change with migration notes.
3.  **Strict Filing**: "Filing Mode" always blocks on inconsistencies.
4.  **Validation Gate**: Real-dataset validation is a standing release gate.
