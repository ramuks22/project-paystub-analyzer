import json
import pytest
from unittest.mock import patch
from paystub_analyzer.cli.annual import main


@pytest.fixture
def household_config_file(tmp_path):
    config = {
        "version": "0.2.0",
        "household_id": "integration_test",
        "filers": [
            {"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "p1_docs"}},
            {"id": "spouse", "role": "SPOUSE", "sources": {"paystubs_dir": "s1_docs"}},
        ],
    }
    config_path = tmp_path / "household_config.json"
    config_path.write_text(json.dumps(config))

    # Create dummy dirs
    (tmp_path / "p1_docs").mkdir()
    (tmp_path / "s1_docs").mkdir()

    return config_path


@patch("paystub_analyzer.cli.annual.collect_annual_snapshots")
@patch("paystub_analyzer.annual.build_household_package")
@patch("paystub_analyzer.cli.annual.write_json")
@patch("paystub_analyzer.cli.annual.write_ledger_csv")
@patch("paystub_analyzer.cli.annual.write_markdown")
def test_cli_household_config_flow(
    mock_write_md, mock_write_csv, mock_write_json, mock_build, mock_collect, household_config_file
):
    # Mock return from build_household_package
    mock_build.return_value = {
        "report": {
            "schema_version": "0.4.0",
            "metadata": {"filing_year": 2025, "state": "UNKNOWN", "filing_status": "UNKNOWN"},
            "household_summary": {"total_gross_pay_cents": 100, "total_fed_tax_cents": 10, "ready_to_file": True},
            "filers": [
                {"id": "primary", "role": "PRIMARY", "status": "MATCH"},
                {"id": "spouse", "role": "SPOUSE", "status": "MATCH"},
            ],
        },
        "filers_analysis": [
            {
                "public": {"id": "primary", "role": "PRIMARY", "status": "MATCH"},
                "internal": {"ledger": [], "meta": {"filing_safety": {"passed": True}}},
            },
            {
                "public": {"id": "spouse", "role": "SPOUSE", "status": "MATCH"},
                "internal": {"ledger": [], "meta": {"filing_safety": {"passed": True}}},
            },
        ],
    }

    # Mock snapshots to return empty list so we don't crash before build
    # Actually snapshot_loader is called INSIDE build_household_package in the real code.
    # But here we mocked build_household_package, so snapshot_loader won't be called unless WE call it.
    # The CLI creates the loader function and passes it to build_household_package.
    # So we just verify build_household_package was called with the right config.

    with patch("sys.argv", ["paystub-annual", "--year", "2025", "--household-config", str(household_config_file)]):
        main()

    # Verify build_household_package called
    assert mock_build.called
    args, kwargs = mock_build.call_args
    assert kwargs["household_config"]["household_id"] == "integration_test"
    assert kwargs["tax_year"] == 2025

    # Verify outputs written
    assert mock_write_json.called
    assert mock_write_csv.call_count == 2  # Once per filer logic attempt
