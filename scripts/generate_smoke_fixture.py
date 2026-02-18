import sys
from pathlib import Path

try:
    from reportlab.pdfgen import canvas
except ImportError:
    print("Error: reportlab is required. Install it with: pip install reportlab")
    sys.exit(1)


def generate_paystub(output_path: Path):
    """Generates a simple paystub PDF for Docker smoke testing."""
    c = canvas.Canvas(str(output_path))
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
    print(f"Generated fixture: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_smoke_fixture.py <output_path>")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_paystub(output_dir / "Pay Date 2025-12-31.pdf")
