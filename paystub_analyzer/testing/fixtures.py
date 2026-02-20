#!/usr/bin/env python3
"""
Generates synthetic PDF fixtures (Paystubs and W-2s) for E2E testing.
Requires: pip install reportlab
"""

import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
except ImportError:
    print("Error: reportlab not installed. Run: pip install reportlab")
    sys.exit(1)


def generate_paystub(path: Path, date_str: str, gross: str, taxes: dict[str, str], net: str) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica", 12)

    # Header
    c.drawString(50, 750, "ACME CORP PAYSTUB")
    c.drawString(50, 735, f"Pay Date: {date_str}")

    # Grid of values (simple text layout for OCR to catch)
    y = 700
    c.drawString(50, y, "Earnings")
    c.drawString(200, y, "Rate")
    c.drawString(300, y, "Hours")
    c.drawString(400, y, "Current")
    c.drawString(500, y, "YTD")

    y -= 20
    c.drawString(50, y, "Regular Pay")
    c.drawString(400, y, gross)  # Current
    c.drawString(500, y, gross)  # YTD (assuming single stub for simplicity or consistent)

    y -= 40
    c.drawString(50, y, "Taxes")

    for tax_name, amount in taxes.items():
        y -= 15
        c.drawString(50, y, tax_name)
        c.drawString(400, y, amount)
        c.drawString(500, y, amount)

    y -= 40
    c.drawString(50, y, "Net Pay Distribution")
    c.drawString(400, y, net)

    # Specific keywords for classifier
    y -= 40
    c.drawString(50, y, "Gross Pay")
    c.drawString(150, y, gross)
    c.drawString(300, y, "Net Pay")
    c.drawString(400, y, net)

    c.save()
    print(f"Generated Paystub: {path}")


def generate_w2(path: Path, year: int, ein: str, wages: str, fed_tax: str, control_no: str) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Courier", 12)

    # W-2 Layout simulation (Boxes)
    c.drawString(50, 750, f"Form W-2 Wage and Tax Statement {year}")

    # Box b: EIN
    c.rect(50, 700, 150, 40)
    c.drawString(55, 730, "b Employer identification number (EIN)")
    c.drawString(55, 710, ein)

    # Vertical Stack for robust OCR

    # Box 1: Wages (Top)
    c.rect(300, 700, 200, 40)
    c.drawString(305, 715, f"1 Wages, tips, other comp. ${wages}")

    # Box 2: Fed Tax (Below Box 1)
    c.rect(300, 650, 200, 40)
    c.drawString(305, 665, f"2 Federal income tax withheld ${fed_tax}")

    # Box 3: Social Security Wages
    c.rect(300, 600, 200, 40)
    c.drawString(305, 615, f"3 Social security wages ${wages}")

    # Box 4: Social Security Tax
    c.rect(300, 550, 200, 40)
    c.drawString(305, 565, "4 Social security tax withheld $0.00")

    c.save()
    print(f"Generated W-2: {path}")


def main_gen(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Paystub
    generate_paystub(
        output_dir / "Pay Date 2025-01-15.pdf",
        date_str="01/15/2025",
        gross="5000.00",
        taxes={"Federal Income Tax": "500.00", "Social Security Tax": "310.00", "Medicare Tax": "72.50"},
        net="4117.50",
    )

    # 2. W-2
    generate_w2(
        output_dir / "w2_2025.pdf",
        year=2025,
        ein="12-3456789",
        wages="60000.00",  # Projecting 12 * 5000
        fed_tax="6000.00",
        control_no="CN-12345",
    )

    # 3. Duplicate W-2 (same content, different file) for dedupe test
    generate_w2(
        output_dir / "w2_2025_copy.pdf",
        year=2025,
        ein="12-3456789",
        wages="60000.00",
        fed_tax="6000.00",
        control_no="CN-12345",
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    else:
        out = Path("e2e_fixtures")
    main_gen(out)
