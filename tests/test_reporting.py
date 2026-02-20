from paystub_analyzer.annual import package_to_markdown


def test_reporting_state_tax_verification():
    # Mock package structure
    package = {
        "schema_version": "0.3.0",
        "household_summary": {"total_gross_pay_cents": 100000, "total_fed_tax_cents": 20000, "ready_to_file": True},
        "filers": [
            {
                "id": "primary",
                "role": "PRIMARY",
                "gross_pay_cents": 50000,
                "fed_tax_cents": 10000,
                "status": "MATCH",
                "state_tax_by_state_cents": {
                    "VA": 5000,  # Paystub says $50.00
                    "MD": 2000,  # Paystub says $20.00
                },
                "w2_aggregate": {
                    "state_boxes": [
                        {"state": "VA", "box_17_state_income_tax": 50.00},  # Match
                        {"state": "MD", "box_17_state_income_tax": 15.00},  # Mismatch ($15.00 vs $20.00)
                    ]
                },
            }
        ],
    }

    md = package_to_markdown(package)

    # Assertions
    assert "### State Tax Verification" in md
    assert "| State | Paystub YTD | W-2 Box 17 | Difference | Status |" in md

    # VA Row (Match)
    # Paystub: 50.00, W-2: 50.00, Diff: 0.00
    assert "| VA | $50.00 | $50.00 | $0.00 | MATCH |" in md

    # MD Row (Mismatch)
    # Paystub: 20.00, W-2: 15.00, Diff: 5.00
    assert "| MD | $20.00 | $15.00 | $5.00 | MISMATCH |" in md


def test_reporting_state_tax_missing_w2():
    # Case where W-2 data is missing for a state present on paystub
    package = {
        "schema_version": "0.3.0",
        "household_summary": {"total_gross_pay_cents": 0, "total_fed_tax_cents": 0, "ready_to_file": False},
        "filers": [
            {
                "id": "primary",
                "role": "PRIMARY",
                "gross_pay_cents": 0,
                "fed_tax_cents": 0,
                "status": "REVIEW_NEEDED",
                "state_tax_by_state_cents": {"CA": 1000},
                "w2_aggregate": {},  # No W-2 state boxes
            }
        ],
    }

    md = package_to_markdown(package)
    assert "| CA | $10.00 | — | $10.00 | MISMATCH |" in md
