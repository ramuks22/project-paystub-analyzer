import pytest
from decimal import Decimal
from unittest.mock import Mock
from paystub_analyzer.annual import build_household_package
from paystub_analyzer.core import PaystubSnapshot, AmountPair


@pytest.fixture
def mock_loader():
    return Mock()


@pytest.fixture
def mock_w2_loader():
    return Mock(return_value=None)


def create_snapshot(file, gross_ytd):
    return PaystubSnapshot(
        file=file,
        pay_date="2025-12-31",
        gross_pay=AmountPair(Decimal("0"), Decimal(gross_ytd), "line"),
        federal_income_tax=AmountPair(Decimal("0"), Decimal("100"), "line"),
        social_security_tax=AmountPair(Decimal("0"), Decimal("100"), "line"),
        medicare_tax=AmountPair(Decimal("0"), Decimal("100"), "line"),
        k401_contrib=AmountPair(Decimal("0"), Decimal("0"), "line"),
        state_income_tax={},
        normalized_lines=[],
    )


def test_household_aggregation_success(mock_loader, mock_w2_loader):
    config = {
        "version": "0.2.0",
        "household_id": "test_hh",
        "filers": [
            {"id": "p1", "role": "PRIMARY", "sources": {"paystubs_dir": "p1_dir"}},
            {"id": "s1", "role": "SPOUSE", "sources": {"paystubs_dir": "s1_dir"}},
        ],
    }

    # Loader returns different snapshots for each source
    mock_loader.side_effect = lambda src: (
        [create_snapshot("p1.pdf", "1000.00")]
        if src["paystubs_dir"] == "p1_dir"
        else [create_snapshot("s1.pdf", "500.00")]
    )

    result = build_household_package(config, 2025, mock_loader, mock_w2_loader, Decimal("0.01"))
    summary = result["report"]["household_summary"]

    # 1000 + 500 = 1500 -> 150,000 cents
    assert summary["total_gross_pay_cents"] == 150000
    assert len(result["filers_analysis"]) == 2


def test_household_shared_file_error(mock_loader, mock_w2_loader):
    config = {
        "version": "0.2.0",
        "household_id": "test_err",
        "filers": [
            {"id": "p1", "role": "PRIMARY", "sources": {"paystubs_dir": "dir"}},
            {
                "id": "s1",
                "role": "SPOUSE",
                "sources": {"paystubs_dir": "dir"},  # Same sources
            },
        ],
    }

    # Both return the SAME file path
    mock_loader.return_value = [create_snapshot("shared.pdf", "100.00")]

    with pytest.raises(ValueError, match="is claimed by both"):
        build_household_package(config, 2025, mock_loader, mock_w2_loader, Decimal("0.01"))


def test_household_cardinality_error(mock_loader, mock_w2_loader):
    # No PRIMARY
    config = {"filers": [{"id": "s1", "role": "SPOUSE", "sources": {}}]}
    with pytest.raises(ValueError, match="exactly one PRIMARY"):
        build_household_package(config, 2025, mock_loader, mock_w2_loader, Decimal("0.01"))
