import sys
from pathlib import Path
from typing import Dict, Any

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib import colors
except ImportError:
    print("Error: reportlab is required. Install it with: pip install reportlab")
    sys.exit(1)


def generate_layout_adp(c: canvas.Canvas, data: Dict[str, Any]):
    """Classic ADP-style top-down layout."""
    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, 780, "ADP Wage Statement")
    c.setFont("Helvetica", 10)
    c.drawString(100, 760, f"Pay Date: {data['pay_date']}")

    y = 720
    c.drawString(50, y, "Earnings")
    c.drawString(300, y, "This Period")
    c.drawString(400, y, "Year to Date")

    y -= 20
    c.line(50, y + 15, 500, y + 15)

    fields = [
        ("Gross Pay", "gross_pay"),
        ("Federal Income Tax", "fed_tax"),
        ("Social Security", "ss_tax"),
        ("Medicare", "med_tax"),
        ("401(k) Contribution", "401k"),
    ]

    for label, key in fields:
        c.drawString(50, y, label)
        c.drawRightString(350, y, f"{data['period'].get(key, 0.0):,.2f}")
        c.drawRightString(450, y, f"{data['ytd'].get(key, 0.0):,.2f}")
        y -= 15


def generate_layout_gusto(c: canvas.Canvas, data: Dict[str, Any]):
    """Modern Gusto-style clean layout with large section headers."""
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 780, "Gusto Pay Stub")
    c.setFont("Helvetica", 12)
    c.drawString(50, 760, f"Period Ending: {data['pay_date']}")

    # Left Column: Earnings
    y = 700
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "EARNINGS")
    c.setFont("Helvetica", 10)
    y -= 20
    c.drawString(50, y, "Regular Pay")
    c.drawRightString(200, y, f"{data['period'].get('gross_pay', 0.0):,.2f}")

    # Right Column: Taxes & Deductions
    y = 700
    c.setFont("Helvetica-Bold", 12)
    c.drawString(300, y, "TAXES & DEDUCTIONS")
    c.setFont("Helvetica", 10)
    y -= 20

    ded_fields = [
        ("Federal Income Tax", "fed_tax"),
        ("Social Security", "ss_tax"),
        ("Medicare", "med_tax"),
    ]

    for label, key in ded_fields:
        c.drawString(300, y, label)
        c.drawRightString(450, y, f"{data['period'].get(key, 0.0):,.2f}")
        y -= 15

    # Bottom Summary
    y = 600
    c.setFont("Helvetica-Bold", 12)
    c.drawString(300, y, "YTD TOTALS")
    c.setFont("Helvetica", 10)
    y -= 20
    c.drawString(300, y, "YTD Gross")
    c.drawRightString(450, y, f"{data['ytd'].get('gross_pay', 0.0):,.2f}")
    y -= 15
    c.drawString(300, y, "YTD Federal withholding")
    c.drawRightString(450, y, f"{data['ytd'].get('fed_tax', 0.0):,.2f}")


def generate_layout_trinet(c: canvas.Canvas, data: Dict[str, Any]):
    """TriNet complex grid layout."""
    c.setFont("Times-Bold", 14)
    c.drawString(50, 780, "TriNet / Professional Employer Organization")
    c.setFont("Times-Roman", 9)
    c.drawString(50, 770, f"Advice Number: 999999 | Date: {data['pay_date']}")

    # Boxed Layout
    c.rect(50, 600, 500, 150)
    c.line(250, 600, 250, 750)

    # Left: Earnings Grid
    c.drawString(55, 740, "Description")
    c.drawString(150, 740, "Rate")
    c.drawString(200, 740, "Total")
    c.drawString(55, 720, "REGULAR")
    c.drawString(200, 720, f"{data['period'].get('gross_pay', 0.0):,.2f}")

    # Right: Taxes & Deductions YTD
    c.drawString(255, 740, "YTD TAXES")
    y = 720
    for label, key in [("Fed Income Tax", "fed_tax"), ("Soc Sec", "ss_tax"), ("Medicare", "med_tax")]:
        c.drawString(255, y, label)
        c.drawRightString(450, y, f"{data['ytd'].get(key, 0.0):,.2f}")
        y -= 12


def generate_layout_paychex(c: canvas.Canvas, data: Dict[str, Any]):
    """Paychex-style layout with centered header and bold totals."""
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(300, 780, "Paychex Earnings Statement")
    c.setFont("Helvetica", 10)
    c.drawCentredString(300, 765, f"Check Date: {data['pay_date']}")

    y = 720
    c.drawString(50, y, "Earnings")
    c.drawString(450, y, "Amount")
    c.line(50, y - 5, 550, y - 5)
    y -= 25
    c.drawString(50, y, "Regular")
    c.drawRightString(500, y, f"{data['period'].get('gross_pay', 0.0):,.2f}")

    y -= 40
    c.drawString(50, y, "Statutory Taxes")
    c.line(50, y - 5, 550, y - 5)
    y -= 25
    for label, key in [("Federal Income Tax", "fed_tax"), ("Social Security", "ss_tax")]:
        c.drawString(50, y, label)
        c.drawRightString(500, y, f"{data['period'].get(key, 0.0):,.2f}")
        y -= 15

    y -= 40
    c.drawString(50, y, "Year to Date Information")
    c.line(50, y - 5, 550, y - 5)
    y -= 25
    c.drawString(50, y, "Gross Pay")
    c.drawRightString(500, y, f"{data['ytd'].get('gross_pay', 0.0):,.2f}")


def generate_layout_workday(c: canvas.Canvas, data: Dict[str, Any]):
    """Workday-style extremely clean, blue-accented layout."""
    c.setFillColor(colors.HexColor("#005CB9"))
    c.rect(0, 750, 612, 50, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 770, "Payslip")
    c.setFillColor(colors.black)

    c.setFont("Helvetica", 10)
    c.drawString(50, 730, f"Payment Date: {data['pay_date']}")

    y = 680
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Summary")
    c.line(50, y - 5, 550, y - 5)
    y -= 25
    c.setFont("Helvetica", 10)
    c.drawString(50, y, "Total Gross")
    c.drawRightString(350, y, f"{data['period'].get('gross_pay', 0.0):,.2f}")
    c.drawRightString(500, y, f"{data['ytd'].get('gross_pay', 0.0):,.2f}")


def inject_noise(c: canvas.Canvas):
    """Inject subtle visual noise to test OCR resilience."""
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.1)
    # Random diagonal lines
    for i in range(0, 800, 50):
        c.line(i, 0, i + 100, 800)
    c.setStrokeColor(colors.black)


def generate_fixture(output_path: Path, layout: str, data: Dict[str, Any], noise: bool = False):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=LETTER)

    # Make PDF deterministic
    c.setCreator("PaystubAnalyzer-Gold-Dataset-Generator")
    c.setAuthor("Antigravity-AI")
    c.setKeywords("synthetic-gold-dataset")
    # Force fixed metadata dates
    c._doc.info.CreationDate = "D:19700101000000Z"
    c._doc.info.ModDate = "D:19700101000000Z"

    if noise:
        inject_noise(c)

    if layout == "adp":
        generate_layout_adp(c, data)
    elif layout == "gusto":
        generate_layout_gusto(c, data)
    elif layout == "trinet":
        generate_layout_trinet(c, data)
    elif layout == "paychex":
        generate_layout_paychex(c, data)
    elif layout == "workday":
        generate_layout_workday(c, data)
    else:
        # Generic fallback
        generate_layout_adp(c, data)

    c.save()
    print(f"Generated {layout} fixture: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_gold_fixtures.py <output_root>")
        sys.exit(1)

    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=True)

    # Data templates
    standard_data = {
        "pay_date": "12/31/2025",
        "iso_date": "2025-12-31",
        "period": {"gross_pay": 5000.0, "fed_tax": 800.0, "ss_tax": 310.0, "med_tax": 72.5, "401k": 500.0},
        "ytd": {"gross_pay": 60000.0, "fed_tax": 9600.0, "ss_tax": 3720.0, "med_tax": 870.0, "401k": 6000.0},
    }

    # 1. ADP Standard
    generate_fixture(
        root / "adp_standard" / "paystubs" / f"Pay Date {standard_data['iso_date']}.pdf", "adp", standard_data
    )

    # 2. Gusto Modern
    generate_fixture(
        root / "gusto_clean" / "paystubs" / f"Pay Date {standard_data['iso_date']}.pdf", "gusto", standard_data
    )

    # 3. TriNet Grid (Noisy)
    generate_fixture(
        root / "trinet_complex" / "paystubs" / f"Pay Date {standard_data['iso_date']}.pdf",
        "trinet",
        standard_data,
        noise=True,
    )

    # 4. Paychex
    generate_fixture(
        root / "paychex_classic" / "paystubs" / f"Pay Date {standard_data['iso_date']}.pdf", "paychex", standard_data
    )

    # 5. Workday
    generate_fixture(
        root / "workday_modern" / "paystubs" / f"Pay Date {standard_data['iso_date']}.pdf", "workday", standard_data
    )

    # 6. Revised ADP (Different Period data, Same YTD)
    revised_data = standard_data.copy()
    revised_data["period"] = {"gross_pay": 6000.0, "fed_tax": 1000.0, "ss_tax": 372.0, "med_tax": 87.0, "401k": 600.0}
    generate_fixture(
        root / "adp_revised" / "paystubs" / f"Pay Date {standard_data['iso_date']}_REV.pdf", "adp", revised_data
    )

    # 7. Generic OCR Challenge (Heavy noise)
    generate_fixture(
        root / "ocr_challenge" / "paystubs" / f"Pay Date {standard_data['iso_date']}_NOISY.pdf",
        "adp",
        standard_data,
        noise=True,
    )
