import json
import pytest
from pathlib import Path
from unittest.mock import patch
from paystub_analyzer.cli.annual import main


@pytest.fixture
def household_setup(tmp_path):
    p1_dir = tmp_path / "p1_paystubs"
    p1_dir.mkdir()
    s1_dir = tmp_path / "s1_paystubs"
    s1_dir.mkdir()

    # Create dummy PDF files
    (p1_dir / "Pay Date 2025-01-15.pdf").touch()
    (s1_dir / "Pay Date 2025-01-15.pdf").touch()

    config = {
        "version": "0.2.0",
        "household_id": "real_integration",
        "filers": [
            {"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "p1_paystubs"}},
            {"id": "spouse", "role": "SPOUSE", "sources": {"paystubs_dir": "s1_paystubs"}},
        ],
    }
    config_path = tmp_path / "household_config.json"
    config_path.write_text(json.dumps(config))

    return config_path


def mock_ocr_provider(path: Path, scale: float, psm: int) -> str:
    """Return specific text based on path to simulate different paystubs."""
    # Strict directory checking to avoid partial matches in tmp path
    if "p1_paystubs" in str(path):
        return "Gross Pay $1,000.00\nFederal Income Tax $100.00\nSocial Security Tax $60.00\nMedicare Tax $15.00\nPay Date: 01/15/2025\nNet Pay $825.00"
    if "s1_paystubs" in str(path):
        return "Gross Pay $2,000.00\nFederal Income Tax $200.00\nSocial Security Tax $120.00\nMedicare Tax $30.00\nPay Date: 01/15/2025\nNet Pay $1650.00"
    return ""


# We mock core.ocr_first_page which is used by extract_paystub_snapshot
# This allows us to use REAL file system crawling and REAL logic, just skipping Pdfs.
@patch("paystub_analyzer.core.ocr_first_page", side_effect=mock_ocr_provider)
def test_integration_household_cli_real_fs(mock_ocr, household_setup, tmp_path):
    """
    Test the full CLI flow with a real config file and real directory structure.
    Only the OCR step is mocked.
    """
    pkg_json = tmp_path / "output.json"

    with patch(
        "sys.argv",
        [
            "paystub-annual",
            "--year",
            "2025",
            "--household-config",
            str(household_setup),
            "--package-json-out",
            str(pkg_json),
            "--force",  # Force generation even if validation fails (e.g. missing fields in mock text)
        ],
    ):
        # We expect SystemExit(0) or just return if we handle it
        # The main logic uses sys.exit(1) on failure.
        # If success, it returns None.
        try:
            main()
        except SystemExit as e:
            # allow exit 0 (success) or None
            if e.code not in [None, 0]:
                raise

    assert pkg_json.exists()
    data = json.loads(pkg_json.read_text())

    assert data["schema_version"] == "0.3.0"
    summary = data["household_summary"]

    # P1: 1000, S1: 2000 -> Total 3000 -> 300,000 cents
    assert summary["total_gross_pay_cents"] == 300000

    # Check Filers
    filers = data["filers"]
    assert len(filers) == 2
    p1 = next(f for f in filers if f["role"] == "PRIMARY")
    assert p1["gross_pay_cents"] == 100000

    s1 = next(f for f in filers if f["role"] == "SPOUSE")
    assert s1["gross_pay_cents"] == 200000
