# Contributing to Paystub Analyzer

Thank you for your interest in contributing! We welcome bug reports, feature requests, and code contributions.

## Development Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/project-paystub-analyzer.git
    cd project-paystub-analyzer
    ```

2.  **Install in editable mode with dev dependencies**:
    ```bash
    pip install -e ".[dev]"
    ```
    This installs `pytest`, `ruff`, `mypy`, `pre-commit`, and other tools.

3.  **Install pre-commit hooks**:
    ```bash
    pre-commit install
    ```
    This ensures linting and security checks run before every commit.

## Testing

We use `pytest` for testing.

-   **Run all tests**:
    ```bash
    pytest
    ```
-   **Run unit tests only**:
    ```bash
    pytest -m unit
    ```

## Code Quality

We enforce strict code quality standards:

-   **Linting & Formatting**: `ruff check .` and `ruff format .`
-   **Type Checking**: `mypy paystub_analyzer`

Please ensure all checks pass before submitting a PR. The pre-commit hooks will help you with this.

## Data Contracts & Schema Policy

We enforce strict data contracts for all public outputs (JSON reports).

*   **Schema Versioning**: All JSON outputs MUST include a `schema_version` field (e.g., `"schema_version": "0.2.0"`).
*   **Compliance**: Output validation against the defined JSON Schema is mandatory in CI.
*   **Versioning Scheme**: We follow Semantic Versioning (MAJOR.MINOR.PATCH) for schemas.
    *   **PATCH**: Backward-compatible fixes (e.g., adding a non-required field).
    *   **MINOR**: Backward-compatible feature additions.
    *   **MAJOR**: Breaking changes (e.g., renaming/removing fields).
*   **Breaking Changes**: Any breaking change requires a MAJOR version bump and a migration guide.

## Pull Request Process

1.  Fork the repo and create your branch from `main`.
2.  Add tests for any new functionality.
3.  Update documentation if necessary.
4.  Ensure the test suite passes.
5.  Submit a Pull Request with a clear description of changes.

## Security

Please see [SECURITY.md](SECURITY.md) for our security policy.
