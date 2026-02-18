#!/usr/bin/env python3

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium

MONEY_RE = re.compile(r"[+-]?\$?\d[\d,]*\.\d{2}")
FILENAME_PAY_DATE_RE = re.compile(r"Pay Date (\d{4}-\d{2}-\d{2})(?:_\d+)?\.pdf$", re.IGNORECASE)
TEXT_PAY_DATE_RE = re.compile(r"Pay Date:\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
STATE_TAX_LINE_RE = re.compile(r"\b([A-Z]{2}) State Income Tax\b", re.IGNORECASE)
OcrTextProvider = Callable[[Path, float, int], str]


@dataclass
class AmountPair:
    this_period: Decimal | None
    ytd: Decimal | None
    source_line: str | None


@dataclass
class PaystubSnapshot:
    file: str
    pay_date: str | None
    gross_pay: AmountPair
    federal_income_tax: AmountPair
    social_security_tax: AmountPair
    medicare_tax: AmountPair
    k401_contrib: AmountPair
    state_income_tax: dict[str, AmountPair]
    normalized_lines: list[str]


def normalize_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    # Repair OCR splits like "1, 234.56" or "-123 .45".
    line = re.sub(r"(\d)\s*,\s*(\d)", r"\1,\2", line)
    line = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", line)
    line = re.sub(r"(?<!\d)-\s+(\d)", r"-\1", line)
    line = re.sub(r"\s+", " ", line)
    return line


def parse_money(token: str) -> Decimal:
    return Decimal(token.replace("$", "").replace(",", ""))


def extract_money_values(line: str) -> list[Decimal]:
    return [parse_money(token) for token in MONEY_RE.findall(line)]


def parse_amount_pair_from_line(line: str) -> AmountPair:
    normalized = normalize_line(line)
    amounts = [abs(value) for value in extract_money_values(normalized)]
    if not amounts:
        return AmountPair(None, None, normalized)
    if len(amounts) == 1:
        return AmountPair(None, amounts[0], normalized)

    first, second = amounts[0], amounts[1]
    # On standard statements this order is "this period, ytd".
    # If second is smaller, the second number is often unrelated spillover from the right column.
    if second >= first:
        return AmountPair(first, second, normalized)
    return AmountPair(None, first, normalized)


def parse_pay_date_from_filename(path: Path) -> date | None:
    match = FILENAME_PAY_DATE_RE.search(path.name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d").date()


def parse_pay_date_from_text(text: str) -> date | None:
    match = TEXT_PAY_DATE_RE.search(text)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%m/%d/%Y").date()


def ensure_tesseract_available() -> None:
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract is required but not found in PATH.")


def run_tesseract(image_path: Path, psm: int = 6) -> str:
    ensure_tesseract_available()
    process = subprocess.run(
        ["tesseract", str(image_path), "stdout", "--psm", str(psm)],
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout


def ocr_first_page(pdf_path: Path, render_scale: float = 2.5, psm: int = 6) -> str:
    document = pdfium.PdfDocument(str(pdf_path))
    page = document[0]
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        image_path = Path(temp_file.name)
    try:
        page.render(scale=render_scale).to_pil().save(image_path)
        return run_tesseract(image_path, psm=psm)
    finally:
        image_path.unlink(missing_ok=True)


def find_line_amount_pair(lines: list[str], pattern: str) -> AmountPair:
    compiled = re.compile(pattern, re.IGNORECASE)
    for line in lines:
        if compiled.search(line):
            pair = parse_amount_pair_from_line(line)
            if pair.ytd is not None:
                return pair
    return AmountPair(None, None, None)


def extract_state_tax_pairs(lines: list[str]) -> dict[str, AmountPair]:
    result: dict[str, AmountPair] = {}
    for line in lines:
        match = STATE_TAX_LINE_RE.search(line)
        if not match:
            continue
        state = match.group(1).upper()
        pair = parse_amount_pair_from_line(line)
        if pair.ytd is None:
            continue
        existing = result.get(state)
        if existing is None:
            result[state] = pair
            continue
        existing_ytd = existing.ytd or Decimal("0.00")
        if (pair.ytd or Decimal("0.00")) > existing_ytd:
            result[state] = pair
    return result


def extract_paystub_snapshot(
    pdf_path: Path,
    render_scale: float = 2.5,
    psm: int = 6,
    ocr_text_provider: OcrTextProvider | None = None,
) -> PaystubSnapshot:
    provider = ocr_text_provider or ocr_first_page
    text = provider(pdf_path, render_scale, psm)
    lines = [normalize_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    pay_date = parse_pay_date_from_text(text)
    if pay_date is None:
        pay_date = parse_pay_date_from_filename(pdf_path)

    return PaystubSnapshot(
        file=str(pdf_path),
        pay_date=pay_date.isoformat() if pay_date else None,
        gross_pay=find_line_amount_pair(lines, r"\bGross Pay\b"),
        federal_income_tax=find_line_amount_pair(lines, r"\bFederal Income Tax\b"),
        social_security_tax=find_line_amount_pair(lines, r"\bSocial Security Tax\b"),
        medicare_tax=find_line_amount_pair(lines, r"\bMedicare Tax\b"),
        k401_contrib=find_line_amount_pair(lines, r"\b401\(K\) Contrib\b"),
        state_income_tax=extract_state_tax_pairs(lines),
        normalized_lines=lines,
    )


def list_paystub_files(paystub_dir: Path, year: int | None) -> list[Path]:
    files = sorted(paystub_dir.glob("*.pdf"))
    if year is None:
        return files
    filtered: list[Path] = []
    for file_path in files:
        pay_date = parse_pay_date_from_filename(file_path)
        if pay_date and pay_date.year == year:
            filtered.append(file_path)
    return filtered


def select_latest_paystub(files: list[Path]) -> tuple[Path, date]:
    dated: list[tuple[Path, date]] = []
    for file_path in files:
        pay_date = parse_pay_date_from_filename(file_path)
        if pay_date is not None:
            dated.append((file_path, pay_date))
    if not dated:
        raise RuntimeError("Could not determine pay dates from paystub filenames.")
    return sorted(dated, key=lambda item: item[1])[-1]


def as_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01")))


def format_money(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"${value.quantize(Decimal('0.01')):,.2f}"


def sum_state_ytd(state_pairs: dict[str, AmountPair]) -> Decimal:
    total = Decimal("0.00")
    for pair in state_pairs.values():
        if pair.ytd is not None:
            total += pair.ytd
    return total


def sum_state_this_period(state_pairs: dict[str, AmountPair]) -> Decimal:
    total = Decimal("0.00")
    for pair in state_pairs.values():
        if pair.this_period is not None:
            total += pair.this_period
    return total
