import pytest
from unittest.mock import patch
import json
from paystub_analyzer.cli.annual import main as annual_main


@pytest.fixture
def mock_ocr_text():
    return """
    ADP STATEMENT
    Pay Date: 12/31/2025
    Gross Pay  5,000.00  60,000.00
    Federal Income Tax  800.00  9,600.00
    Social Security Tax  310.00  3,720.00
    Medicare Tax  72.50  870.00
    VA State Income Tax  200.00  2,400.00
    401(K) Contrib  500.00  6,000.00
    """


@pytest.mark.e2e
def test_annual_cli_pipeline(mock_ocr_text, tmp_path, capsys):
    """
    E2E Pipeline Test.
    Creates a dummy PDF.
    Mocks ONLY the low-level OCR function to return fixed text.
    Runs the full CLI pipeline (file discovery, regex parsing, aggregation, reporting).
    """
    # 1. Create dummy PDF so file discovery works
    paystubs_dir = tmp_path / "paystubs"
    paystubs_dir.mkdir()
    (paystubs_dir / "Pay Date 2025-12-31.pdf").write_text("dummy pdf content", encoding="utf-8")

    output_json = tmp_path / "package.json"

    # 2. Mock OCR to return text parseable by core.py
    with patch("paystub_analyzer.core.ocr_first_page", return_value=mock_ocr_text):
        # 3. Invoke CLI
        test_args = [
            "paystub-annual",
            "--year",
            "2025",
            "--paystubs-dir",
            str(paystubs_dir),
            "--package-json-out",
            str(output_json),
        ]

        with patch("sys.argv", test_args):
            try:
                annual_main()
            except SystemExit as e:
                # CLI exits with 0 on success
                assert e.code == 0 or e.code is None

    # 4. Verify Output
    assert output_json.exists()
    data = json.loads(output_json.read_text(encoding="utf-8"))

    assert data["schema_version"] == "0.2.0"

    # Check values extracted via regex from mock_ocr_text
    # 60,000.00 -> 6,000,000 cents
    assert data["household_summary"]["total_gross_pay_cents"] == 6000000
    # 9,600.00 -> 960,000 cents
    assert data["household_summary"]["total_fed_tax_cents"] == 960000

    # State tax needs digging into filers[0]
    primary = data["filers"][0]
    # 2,400.00 -> 240,000 cents
    assert primary["state_tax_by_state_cents"]["VA"] == 240000
