import pytest
from decimal import Decimal
from paystub_analyzer.annual import build_tax_filing_package
from paystub_analyzer.core import PaystubSnapshot, AmountPair


def create_mock_snapshot(file_name, pay_date, gross_ytd):
    return PaystubSnapshot(
        file=file_name,
        pay_date=pay_date,
        gross_pay=AmountPair(Decimal("1000.00"), gross_ytd, "line"),
        federal_income_tax=AmountPair(Decimal("100.00"), Decimal("1000.00"), "line"),
        social_security_tax=AmountPair(Decimal("62.00"), Decimal("620.00"), "line"),
        medicare_tax=AmountPair(Decimal("14.50"), Decimal("145.00"), "line"),
        k401_contrib=AmountPair(Decimal("50.00"), Decimal("500.00"), "line"),
        state_income_tax={"CA": AmountPair(Decimal("40.00"), Decimal("400.00"), "line")},
        normalized_lines=[],
    )


@pytest.mark.integration
def test_build_package_success(mocker):
    # Mock extracted snapshots
    snapshot1 = create_mock_snapshot("stub1.pdf", "2025-01-15", Decimal("5000.00"))
    snapshot2 = create_mock_snapshot("stub2.pdf", "2025-01-31", Decimal("10000.00"))

    snapshots = [snapshot1, snapshot2]

    # Mock extract_paystub_snapshot is NOT needed because we pass snapshots directly to build_tax_filing_package

    result = build_tax_filing_package(tax_year=2025, snapshots=snapshots, tolerance=Decimal("0.05"), w2_data=None)

    # Check meta for internal details
    meta = result["meta"]
    assert meta["tax_year"] == 2025
    assert meta["paystub_count_raw"] == 2
    assert meta["latest_pay_date"] == "2025-01-31"
    assert meta["extracted"]["gross_pay"]["ytd"] == Decimal("10000.00")

    # Check public report for schema
    report = result["report"]
    assert report["schema_version"] == "0.4.0"

    # Safety check
    safety = meta.get("filing_safety", {})
    assert "passed" in safety


@pytest.mark.integration
def test_build_package_with_w2_mismatch(mocker):
    snapshot = create_mock_snapshot("stub.pdf", "2025-12-31", Decimal("50000.00"))

    w2_data = {
        "box_1_wages_tips_other_comp": Decimal("50000.00"),
        "box_2_federal_income_tax_withheld": Decimal("1100.00"),  # Mismatch (Strict)
        "box_4_social_security_tax_withheld": Decimal("620.00"),
        "box_6_medicare_tax_withheld": Decimal("145.00"),
        "state_boxes": [
            {
                "state": "CA",
                "box_16_state_wages_tips": Decimal("4000.00"),
                "box_17_state_income_tax": Decimal("400.00"),
            }
        ],
    }

    result = build_tax_filing_package(tax_year=2025, snapshots=[snapshot], tolerance=Decimal("0.05"), w2_data=w2_data)

    safety = result["meta"]["filing_safety"]
    assert safety["passed"] is False
    assert any("Mismatch" in err for err in safety["errors"])
