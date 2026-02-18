# Security Policy

## Supported Versions

Use this section to tell people about which versions of your project are
currently being supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

We take the security of this project seriously.

If you find a security vulnerability, please **DO NOT** open a public issue.

Instead, please report it via [INSERT METHOD, e.g., email or security tab].

1.  Describe the vulnerability.
2.  Provide steps to reproduce.
3.  We will respond within 48 hours to acknowledge the report.

## PII & Secrets

This project involves processing potentially sensitive financial documents (paystubs, W-2s).
*   **Never commit real paystub PDFs or W-2 data to this repository.**
*   The repository is configured with pre-commit hooks to block these files.
*   If you accidentally commit sensitive data, please rotate any exposed credentials and scrub the history immediately.
