"""
Filing Rules Module

This module defines the strict gates for "Filing Mode".
It encapsulates the logic to determine if a tax filing packet is safe to generate/sign.
"""

from decimal import Decimal
from typing import Any, NamedTuple


class FilingCheckResult(NamedTuple):
    passed: bool
    errors: list[str]
    warnings: list[str]


def validate_filing_safety(
    extracted_data: dict[str, Any],
    comparisons: list[dict[str, Any]],
    consistency_issues: list[dict[str, Any]],
    tolerance: Decimal,
) -> FilingCheckResult:
    """
    Validates if the current data is safe for a 'Filing Mode' export.

    Rules:
    1. BLOCKING: Missing required tax fields (Gross Pay, Fed Tax, SS Tax, Medicare Tax).
    2. BLOCKING: Comparison mismatches > tolerance.
    3. BLOCKING: Critical consistency codes (e.g. 'ytd_decrease').
    4. NON-BLOCKING: Cosmetic/OCR warnings.
    """
    errors = []
    warnings = []

    # 1. Check required fields
    required_fields = [
        "gross_pay",
        "federal_income_tax",
        "social_security_tax",
        "medicare_tax",
    ]
    extracted_values = extracted_data.get("extracted", {})
    # Handle flat or nested structure depending on where this is called from
    # If called with the Annual Package 'extracted' dict directly:
    if "gross_pay" in extracted_data:
        extracted_values = extracted_data

    for field in required_fields:
        val = extracted_values.get(field, {}).get("ytd")
        if val is None:
            errors.append(f"Missing required field: {field} (YTD is null)")

    # 2. Check comparison mismatches
    # 2. Check comparison mismatches
    for comp in comparisons:
        status = comp.get("status")
        diff_val = comp.get("difference")

        if diff_val is None:
            # If difference is None, it means one value is missing.
            # We rely on 'status' to capture the issue (e.g. missing_paystub_value).
            # If status is mismatch but no diff, that's unexpected but we shouldn't crash.
            diff = Decimal("0.00")
        else:
            diff = abs(Decimal(str(diff_val)))

        if status == "mismatch":
            if diff > tolerance:
                errors.append(f"Mismatch in {comp['field']}: diff {diff} exceeds tolerance {tolerance}")
            else:
                warnings.append(f"Minor mismatch in {comp['field']}: diff {diff} within tolerance")
        elif status == "review_needed":
            warnings.append(f"Review needed for {comp['field']}")
        elif status in ("missing_paystub_value", "missing_w2_value"):
            # These are effectively mismatches/blockers for a clean filing
            errors.append(f"Missing value for {comp['field']}: {status}")

    # 3. Checker consistency issues
    for issue in consistency_issues:
        severity = issue.get("severity")
        code = issue.get("code")
        message = issue.get("message") or issue.get("details", "No details")

        if severity == "critical":
            errors.append(f"Critical Consistency Issue: {code} - {message}")
        else:
            warnings.append(f"Consistency warning: {code} - {message}")

    return FilingCheckResult(passed=len(errors) == 0, errors=errors, warnings=warnings)
