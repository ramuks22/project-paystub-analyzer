import pytest
from decimal import Decimal
from typing import Any


@pytest.fixture
def mock_paystub_text() -> str:
    """Returns sample text mimicking OCR output of a paystub."""
    return """
    Company Name LLC
    123 Business Rd

    Gross Pay: $5,000.00
    Federal Income Tax: $800.00
    Social Security Tax: $310.00
    Medicare Tax: $72.50
    401(K) Contrib: $500.00
    CA State Income Tax: $200.00

    Pay Date: 12/31/2025
    """


@pytest.fixture
def sample_snapshot_data() -> dict[str, Any]:
    """Returns a dictionary representation of a PaystubSnapshot."""
    return {
        "file": "test_stub.pdf",
        "pay_date": "2025-12-31",
        "gross_pay": {
            "this_period": Decimal("5000.00"),
            "ytd": Decimal("60000.00"),
            "source_line": "Gross Pay 5000.00 60000.00",
        },
        "federal_income_tax": {
            "this_period": Decimal("800.00"),
            "ytd": Decimal("9600.00"),
            "source_line": "Fed Tax 800.00 9600.00",
        },
        "social_security_tax": {
            "this_period": Decimal("310.00"),
            "ytd": Decimal("3720.00"),
            "source_line": "SS Tax ...",
        },
        "medicare_tax": {"this_period": Decimal("72.50"), "ytd": Decimal("870.00"), "source_line": "Med Tax ..."},
        "k401_contrib": {"this_period": Decimal("500.00"), "ytd": Decimal("6000.00"), "source_line": "401k ..."},
        "state_income_tax": {
            "CA": {"this_period": Decimal("200.00"), "ytd": Decimal("2400.00"), "source_line": "CA Tax ..."}
        },
        "normalized_lines": [],
    }
