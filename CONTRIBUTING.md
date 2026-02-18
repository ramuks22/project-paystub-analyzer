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

## Pull Request Process

1.  Fork the repo and create your branch from `main`.
2.  Add tests for any new functionality.
3.  Update documentation if necessary.
4.  Ensure the test suite passes.
5.  Submit a Pull Request with a clear description of changes.

## Security

Please see [SECURITY.md](SECURITY.md) for our security policy.
