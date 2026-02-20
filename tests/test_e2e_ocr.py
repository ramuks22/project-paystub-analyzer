import pytest
import shutil
import json
from unittest.mock import patch
from paystub_analyzer.cli.annual import main as annual_main

# Skip if tesseract is not installed (dev environments without it)
tesseract_available = shutil.which("tesseract") is not None

try:
    from reportlab.pdfgen import canvas

    reportlab_available = True
except ImportError:
    reportlab_available = False


@pytest.mark.e2e
@pytest.mark.skipif(not tesseract_available, reason="Tesseract not installed")
@pytest.mark.skipif(not reportlab_available, reason="ReportLab not installed")
def test_annual_cli_real_ocr(tmp_path):
    """
    True E2E Test.
    1. Generates a real PDF using ReportLab.
    2. Runs the CLI which uses pypdfium2 to render and Tesseract to OCR.
    3. Verifies extraction logic works on the OCR output.
    """
    paystubs_dir = tmp_path / "paystubs"
    paystubs_dir.mkdir()
    pdf_path = paystubs_dir / "Pay Date 2025-12-31.pdf"
    output_json = tmp_path / "package.json"

    # 1. Generate PDF
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 800, "ADP STATEMENT")
    c.drawString(100, 780, "Pay Date: 12/31/2025")

    # Use simple layout clearly separated to help OCR
    # Label       This Period    YTD
    y = 750
    c.drawString(50, y, "Gross Pay")
    c.drawString(200, y, "5,000.00")
    c.drawString(300, y, "60,000.00")
    y -= 20
    c.drawString(50, y, "Federal Income Tax")
    c.drawString(200, y, "800.00")
    c.drawString(300, y, "9,600.00")
    y -= 20
    c.drawString(50, y, "Social Security Tax")
    c.drawString(200, y, "310.00")
    c.drawString(300, y, "3,720.00")
    y -= 20
    c.drawString(50, y, "Medicare Tax")
    c.drawString(200, y, "72.50")
    c.drawString(300, y, "870.00")
    y -= 20
    c.drawString(50, y, "VA State Income Tax")
    c.drawString(200, y, "200.00")
    c.drawString(300, y, "2,400.00")
    y -= 20
    c.drawString(50, y, "401(K) Contrib")
    c.drawString(200, y, "500.00")
    c.drawString(300, y, "6,000.00")

    c.save()

    # 2. Invoke CLI
    # We do NOT mock OCR here.
    test_args = [
        "paystub-annual",
        "--year",
        "2025",
        "--paystubs-dir",
        str(paystubs_dir),
        "--package-json-out",
        str(output_json),
        "--render-scale",
        "2.0",  # Lower scale for speed/test
    ]

    with patch("sys.argv", test_args):
        try:
            annual_main()
        except SystemExit as e:
            assert e.code == 0 or e.code is None

    # 3. Verify Output
    assert output_json.exists()
    data = json.loads(output_json.read_text(encoding="utf-8"))

    assert data["schema_version"] == "0.4.0"
    # Tax year and paystub count are not in the public report in v0.2.0 schema currently,
    # but we can infer things from the summary.

    # Note: OCR is non-deterministic. We check if it got *something* reasonable.
    # Gross Pay check: 60,000.00 -> 6,000,000 cents
    assert data["household_summary"]["total_gross_pay_cents"] == 6000000
    assert data["household_summary"]["total_fed_tax_cents"] == 960000
