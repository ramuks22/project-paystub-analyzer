# Architectural Review: Project Paystub Analyzer

## Executive Summary

**Role:** Principal Software Architect & Open Source Maintainer
**Verdict:** ⚠️ **Proof of Concept / Alpha Quality**

This project demonstrates a clear understanding of the domain (tax data extraction) and has a clean logical separation between core modules and entry points. However, it currently functions more as a personal script collection than a maintainable, production-ready open source project. It lacks the scaffolding, testing rigor, and packaging standards required for collaboration or reliable deployment.

---

## Critical Findings

### 1. Fragile Dependencies & Environment
- **Hidden System Dependency**: The core logic relies on `tesseract` being installed at the system level (`shutil.which("tesseract")`). This is documented in the README but not enforced or checked at package installation time.
- **Missing Containerization**: For a tool dependent on specific OS-level binaries (Tesseract) and Python libraries (`pypdfium2`), a `Dockerfile` is essential to guarantee reproducibility. Currently, "it works on my machine" is the likely baseline.

### 2. Testing Gaps (The "Happy Path" Trap)
- **Zero Integration Tests**: The tests in `tests/test_core.py` and `tests/test_annual.py` are pure unit tests. They test regex logic on string inputs. There is **no test** that ensures a PDF actually compiles, renders, and OCRs correctly. If `pypdfium2` updates and breaks rendering, or Tesseract changes its output format, your test suite will pass while the application fails.
- **No Mocking**: The widely accepted pattern for testing OCR pipelines is to mock the OCR engine's output to verify the *parsing* of that output, while having a separate small set of "end-to-end" tests with known sample PDFs. You have neither.

### 3. Packaging & Distribution
- **Not a Package**: The project relies on `sys.path.insert(0, str(REPO_ROOT))` in scripts to import the `paystub_analyzer` module. This is fragile and amateurish.
    - **Fix**: Add a `pyproject.toml` or `setup.py`. Make the project installable via `pip install -e .`.
    - **Fix**: Use absolute imports treating `paystub_analyzer` as a library.

### 4. Code Quality & fragility
- **Regex Reliance**: The extraction logic is purely regex-based (`MONEY_RE`, `STATE_TAX_LINE_RE`). This is extremely brittle. A slight layout change in the paystub (e.g., "Social Security" becoming "Soc. Sec.") will break extraction silently or result in zero values.
    - **Suggestion**: Implement a schema-based validation layer using Pydantic to ensure extracted data meets expectations (e.g., "Federal Tax cannot be zero if Gross Pay > $1000").
- **Missing Linting/Formatting**: there are no configuration files for `ruff`, `black`, `mypy`, or `isort`. In a team environment, this codebase will degrade instantly.

### 5. Automation (CI/CD)
- **Non-Existent CI**: There is no `.github/` directory. No tests run on PRs. No automatic linting. This is not "Open Source" yet; it's "Source Available".

---

## Detailed Recommendations

### Phase 1: Foundation (Immediate Fixes)
1.  **Packaging**: Create `pyproject.toml` (using poetry or setuptools).
    - define `project.scripts` entries for your CLI tools instead of loose scripts in `scripts/`.
2.  **Linting**: Add `ruff` and `mypy` to your dev dependencies and fix all violations.
3.  **CI**: Add a simple GitHub Actions workflow to run tests and linters on push.

### Phase 2: Reliability
4.  **Fixture-Based Testing**: Create a `tests/fixtures` directory. Add a "mock" paystub PDF (or a raw text dump from Tesseract) and write a test that parses it.
5.  **Validation Layer**: Introduce `Pydantic` models for `PaystubSnapshot`. Fail fast if required fields are missing or data types are wrong.

### Phase 3: Architecture
6.  **Dependency Injection**: Instead of hardcoding `run_tesseract` inside `extract_paystub_snapshot`, pass an `OCREngine` interface. This allows you to swap Tesseract for AWS Textract or Google Vision later without rewriting core logic, and makes testing easier (you can inject a `MockOCREngine`).
7.  **UI Decoupling**: Move the massive CSS blobs in `ui/app.py` to an external `.css` file or a separate theme module.

## Security Note (PII)
- The `.gitignore` is correctly configured to ignore `*.pdf` and `pay_statements/`.
- **Risk**: The scripts verify `w2_forms/w2_template*.json` is allowed but `w2_forms/*.json` is ignored. Be very careful. One accidental `git add .` could commit your W-2 data if a file is misnamed.
- **Recommendation**: Add a pre-commit hook that scans for suspected PII (like SSN patterns) before allowing a commit.

---

## Grade: C+
**Good functional core, but poor engineering wrapper.**
