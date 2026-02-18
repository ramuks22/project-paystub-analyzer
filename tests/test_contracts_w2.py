import pytest
from paystub_analyzer.utils.contracts import validate_output, ContractError

VALID_W2_COMPARISON = {
    "schema_version": "0.2.0",
    "match_status": "MATCH",
    "discrepancies": [{"field": "box_1", "paystub_value_cents": 100, "w2_value_cents": 100, "diff_cents": 0}],
}


def test_validate_w2_comparison_valid():
    validate_output(VALID_W2_COMPARISON, "w2_comparison")


def test_validate_w2_comparison_invalid_key():
    invalid = VALID_W2_COMPARISON.copy()
    invalid["extra_key"] = "not allowed"
    with pytest.raises(ContractError, match="Data Contract Violation"):
        validate_output(invalid, "w2_comparison", mode="FILING")


def test_validate_w2_comparison_missing_field():
    invalid = VALID_W2_COMPARISON.copy()
    del invalid["match_status"]
    with pytest.raises(ContractError):
        validate_output(invalid, "w2_comparison", mode="FILING")
