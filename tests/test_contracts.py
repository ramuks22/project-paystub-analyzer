import pytest
from paystub_analyzer.utils.contracts import validate_output, ContractError

VALID_ANNUAL_SUMMARY = {
    "schema_version": "0.3.0",
    "household_summary": {"total_gross_pay_cents": 15000000, "total_fed_tax_cents": 3500000, "ready_to_file": False},
    "filers": [
        {
            "id": "primary",
            "role": "PRIMARY",
            "gross_pay_cents": 10000000,
            "fed_tax_cents": 2500000,
            "state_tax_by_state_cents": {"CA": 5000},
            "status": "MATCH",
            "audit_flags": [],
            "correction_trace": [],
            "w2_source_count": 1,
            "w2_aggregate": {
                "box1_wages_cents": 10000000,
                "box2_fed_tax_cents": 2500000,
                "box4_social_security_tax_cents": 620000,
                "box6_medicare_tax_cents": 145000,
            },
            "w2_sources": [
                {
                    "filename": "w2.pdf",
                    "control_number": "CTRL123",
                    "employer_ein": "12-3456789",
                    "box1_wages_contribution_cents": 10000000,
                }
            ],
        }
    ],
}


def test_validate_annual_summary_valid():
    """Should pass for valid data."""
    validate_output(VALID_ANNUAL_SUMMARY, "v0_3_0_contract")


def test_validate_annual_summary_invalid_type():
    """Should fail if type is wrong (e.g. string instead of int)."""
    invalid_data = VALID_ANNUAL_SUMMARY.copy()
    invalid_data["household_summary"] = {
        "total_gross_pay_cents": "150000.00",  # String not allowed
        "total_fed_tax_cents": 3500000,
        "ready_to_file": False,
    }
    with pytest.raises(ContractError) as excinfo:
        validate_output(invalid_data, "v0_3_0_contract", mode="FILING")
    assert "Data Contract Violation" in str(excinfo.value)


def test_validate_annual_summary_missing_field():
    """Should fail if required field is missing."""
    invalid_data = VALID_ANNUAL_SUMMARY.copy()
    del invalid_data["schema_version"]
    with pytest.raises(ContractError):
        validate_output(invalid_data, "v0_3_0_contract", mode="FILING")


def test_validate_review_mode_warning(capsys):
    """Should not raise exception in REVIEW mode, but print warning."""
    invalid_data = VALID_ANNUAL_SUMMARY.copy()
    del invalid_data["schema_version"]

    validate_output(invalid_data, "v0_3_0_contract", mode="REVIEW")
    captured = capsys.readouterr()
    assert "WARNING: Data Contract Violation" in captured.out
