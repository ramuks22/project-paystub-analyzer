# OSS Readiness Plan: Project Paystub Analyzer

## Strategy: Personal-First -> OSS-Ready

**Current Status:** 🚧 **Alpha / Personal Workflow**
**Target Status:** 🚀 **Production-Ready Open Source**

This plan outlines the roadmap to transform the current `project-paystub-analyzer` from a personal utility script into a robust, maintainable open-source project. The focus is on stabilizing the tool for personal use first ("eating your own dogfood") while building the necessary engineering scaffolding for a public release.

---

## Part 1: Critical Findings (The "Why")

1.  **Project Identity Crisis**: The repository lacks a clear stance on its maturity. Without an explicit "Alpha/Personal" declaration, potential users (and contributors) will have mismatched expectations regarding stability and support.
2.  **Unsafe Defaults**: The current "one-size-fits-all" execution model risks generating incorrect tax filings. A distinction between `Review Mode` (lenient, for exploration) and `Filing Mode` (strict, for final output) is essential for reliability.
3.  **Data Contract Fragility**: Output formats (JSON, CSV) are unversioned. Any change to the data structure breaks downstream consumers (e.g., historical reports, other tools) without warning.
4.  **Packaging Debt**: Relying on `sys.path` hacks and loose scripts makes the tool hard to install, hard to update, and impossible to integrate into other workflows.
5.  **Blind Spots in Quality**:
    -   **CI/CD**: No automated checks mean regressions are invisible until manual testing.
    -   **Testing**: "Happy path" unit tests hide the fragility of the OCR pipeline.
6.  **Environment fragility**: System-level dependencies (`tesseract`) and Python environment mismanagement make "it works on my machine" the only guarantee.
7.  **Security Risk**: Lack of active PII scanning during the commit process makes accidental data leakage probable in a tax-sensitive domain.

---

## Part 2: Implementation Roadmap

### Phase 1: Immediate / Personal Use (This Week)
*Focus: Safety and Reliability for the current user.*

- [ ] **Scope Freeze**: No new features until Filing Mode and Schema Versioning are complete.
- [ ] **Declare Status**: Update `README.md` to explicitly state the project is in "Alpha / Personal Workflow" mode.
- [ ] **Review vs. Filing Modes**:
    -   **Review Mode**: Default. Allows partial data, soft warnings for mismatches.
    -   **Filing Mode**: Strict gate. **Fail hard (Exit Code > 0)** based on canonical rules in `paystub_analyzer/filing_rules.py`:
        -   **Blocking**: Missing required fields (`gross_pay`, `federal_tax`, `ss_tax`, `medicare_tax`).
        -   **Blocking**: Mismatches > tolerance.
        -   **Blocking**: Critical consistency codes (e.g., `ytd_decrease`).
        -   **Non-Blocking**: Cosmetic OCR warnings.
- [ ] **Data Contract & Versioning**:
    -   Add `"schema_version": "1.0.0"` to all JSON outputs.
    -   Create `schemas/` directory with:
        -   `schemas/w2_validation.schema.json`
        -   `schemas/tax_filing_package.schema.json`
    -   Define policy: Breaking changes increment Major version; additive changes increment Minor.
- [ ] **UI/UX Polish (Contrast Fixes)**:
    -   Refactor CSS injection in `ui/app.py` to support true light/dark mode detection or enforce a high-contrast single theme.
    -   Ensure text/background combinations pass WCAG AA contrast standards.

### Phase 2: Professionalization (OSS Prep)
*Focus: Engineering Rigor and Collaboration Support.*

- [ ] **Packaging & Dependencies**:
    -   Create `pyproject.toml` with pinned Python versions (e.g., `^3.10`).
    -   Pin `tesseract` major version requirement (e.g., `v5.*`) in documentation/checks.
    -   Refactor `sys.path` imports to proper relative/absolute package imports.
- [ ] **Continuous Integration (CI)**:
    -   Create `.github/workflows/ci.yml` with split jobs:
        -   **Fast**: `pytest` (unit/mock), `ruff`, `mypy` (Run on every Push/PR).
        -   **Slow**: E2E Fixture tests (Run on PRs to `main` and Releases).
- [ ] **3-Layer Testing Strategy**:
    -   **Layer 1: Parser Logic**: Pure unit tests for regex/logic (no I/O).
    -   **Layer 2: OCR Mocking**: Verify handling of OCR output using mocked returns (decoupled from Tesseract).
    -   **Layer 3: E2E Fixture**: One deterministic test with a committed sample PDF/Image to verify the full pipeline.
- [ ] **Reproducible Environment**:
    -   Create a `Dockerfile` that installs Tesseract, Python, and dependencies.
    -   (Optional) Add `.devcontainer` configuration for VS Code users.

### Phase 3: Pre-Launch (Before Public Release)
*Focus: Safety and Community.*

- [ ] **Legal & Safety Messaging**:
    -   Add "Not Tax Advice" disclaimers to CLI output, UI footer, and README.
    -   Clarify "User is responsible for return accuracy" and "Use W-2 as source of truth".
- [ ] **Security Controls**:
    -   Configure `pre-commit` hooks.
    -   **Strategy**: Use pattern/entropy-based scanning (secrets, SSNs) to avoid "name" false positives.
- [ ] **OSS Governance**:
    -   **License**: MIT License.
    -   Add `CONTRIBUTING.md` (dev setup, testing norms).
    -   Add `CODE_OF_CONDUCT.md`.
    -   Add `SECURITY.md` (reporting vulnerabilities).
    -   Create Issue/PR templates.
    -   **Release**: Create Changelog, tagged release, and check for schema version bumps.

---

## Part 3: Go/No-Go OSS Checklist

Use this checklist to determine if the project is ready to remove the "Alpha" label and invite public use.

| Category | Criteria (Must be YES to Launch) | Status |
| :--- | :--- | :--- |
| **Safety** | Does "Filing Mode" fail hard on *any* data inconsistency? | 🔴 No |
| **Safety** | Is there a pre-commit hook scanning for PII (SSNs, Names)? | 🔴 No |
| **Safety** | Are "Not Tax Advice" disclaimers present in CLI/UI/README? | 🔴 No |
| **Usability** | Can a user install via `pip install .` without editing `sys.path`? | 🔴 No |
| **Usability** | Is `tesseract` dependency usage documented *and* checked at runtime? | 🟡 Partial |
| **Quality** | Do `pytest`, `lint`, and `type-check` pass in a clean CI environment? | 🔴 No |
| **Stability** | Is the JSON output schema versioned? | 🔴 No |
| **Contract** | Is JSON schema published and validated in CI? | 🔴 No |
| **Reproducibility** | Can full pipeline run in Docker with one command? | 🔴 No |
| **Reliability** | Is there at least one end-to-end test with a sample PDF/Image? | 🔴 No |
| **Governance** | Is a license chosen and documented? | 🔴 No |
| **Release** | Is there a tagged release with a changelog? | 🔴 No |

## Part 4: Recommended Acceptance Gates

-   **Phase 1 Completion**: Filing Mode blocks unsafe output in 100% of test cases.
-   **Phase 2 Completion**: CI is green on a clean environment, and install works via `pip install .`.
-   **Phase 3 Completion**: Security hooks, docs, and license are present and validated in a dry-run OSS onboarding.
