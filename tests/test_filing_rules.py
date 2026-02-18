import pytest
from decimal import Decimal
from paystub_analyzer.filing_rules import validate_filing_safety


@pytest.mark.unit
def test_filing_safety_pass():
    extracted = {
        "gross_pay": {"ytd": Decimal("50000.00")},
        "federal_income_tax": {"ytd": Decimal("5000.00")},
        "social_security_tax": {"ytd": Decimal("3100.00")},
        "medicare_tax": {"ytd": Decimal("725.00")},
    }
    comparisons = []
    issues = []
    tolerance = Decimal("0.05")

    result = validate_filing_safety(extracted, comparisons, issues, tolerance)
    assert result.passed is True
    assert not result.errors


@pytest.mark.unit
def test_filing_safety_fail_missing_required():
    extracted = {
        "gross_pay": {"ytd": None},  # Missing required field
        "federal_income_tax": {"ytd": Decimal("5000.00")},
    }
    comparisons = []
    issues = []
    tolerance = Decimal("0.05")

    result = validate_filing_safety(extracted, comparisons, issues, tolerance)
    assert result.passed is False
    assert any("gross_pay" in err for err in result.errors)


@pytest.mark.unit
def test_filing_safety_fail_mismatch():
    extracted = {
        "gross_pay": {"ytd": Decimal("50000.00")},
        "federal_income_tax": {"ytd": Decimal("5000.00")},
        "social_security_tax": {"ytd": Decimal("3100.00")},
        "medicare_tax": {"ytd": Decimal("725.00")},
    }
    comparisons = [{"status": "mismatch", "field": "gross_pay", "difference": Decimal("100.00")}]
    issues = []
    tolerance = Decimal("0.05")

    result = validate_filing_safety(extracted, comparisons, issues, tolerance)
    assert result.passed is False
    assert any("Mismatch in gross_pay" in err for err in result.errors)


@pytest.mark.unit
def test_filing_safety_fail_critical_issue():
    extracted = {
        "gross_pay": {"ytd": Decimal("50000.00")},
        "federal_income_tax": {"ytd": Decimal("5000.00")},
        "social_security_tax": {"ytd": Decimal("3100.00")},
        "medicare_tax": {"ytd": Decimal("725.00")},
    }
    comparisons = []
    # Mocking a critical issue dict
    issues = [{"severity": "critical", "message": "Date mismatch"}]
    tolerance = Decimal("0.05")

    result = validate_filing_safety(extracted, comparisons, issues, tolerance)
    assert result.passed is False
    assert any("Critical Consistency Issue" in err for err in result.errors)
