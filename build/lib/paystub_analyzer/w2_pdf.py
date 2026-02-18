#!/usr/bin/env python3

from __future__ import annotations

import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

from paystub_analyzer.core import extract_money_values, normalize_line, run_tesseract

US_STATE_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}


def ocr_pdf_text(pdf_path: Path, render_scale: float = 3.0, psm: int = 6) -> str:
    document = pdfium.PdfDocument(str(pdf_path))
    pages_text: list[str] = []
    for page in document:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            image_path = Path(temp_file.name)
        try:
            page.render(scale=render_scale).to_pil().save(image_path)
            pages_text.append(run_tesseract(image_path, psm=psm))
        finally:
            image_path.unlink(missing_ok=True)
    return "\n".join(pages_text)


def choose_amount(amounts: list[Decimal], preferred_index: int) -> Decimal | None:
    if not amounts:
        return None
    if preferred_index < len(amounts):
        return amounts[preferred_index]
    return amounts[-1]


def find_amount_for_box(
    lines: list[str], patterns: list[re.Pattern[str]], preferred_index: int
) -> tuple[Decimal | None, str | None]:
    for index, line in enumerate(lines):
        for pattern in patterns:
            if not pattern.search(line):
                continue
            amounts = [abs(value) for value in extract_money_values(line)]
            if amounts:
                chosen = choose_amount(amounts, preferred_index)
                if chosen is not None:
                    return chosen, line
            # Some OCR layouts push amount to the next line.
            if index + 1 < len(lines):
                next_amounts = [abs(value) for value in extract_money_values(lines[index + 1])]
                if next_amounts:
                    chosen = choose_amount(next_amounts, preferred_index)
                    if chosen is not None:
                        return chosen, f"{line} | {lines[index + 1]}"
    return None, None


def extract_state_boxes(lines: list[str]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    state_boxes: dict[str, dict[str, Any]] = {}
    evidence: dict[str, str] = {}

    for line in lines:
        amounts = [abs(value) for value in extract_money_values(line)]
        if len(amounts) < 2:
            continue

        codes = [token for token in re.findall(r"\b[A-Z]{2}\b", line) if token in US_STATE_CODES]
        if not codes:
            continue
        state = codes[0]

        wages = max(amounts)
        tax = min(amounts)
        state_boxes[state] = {
            "state": state,
            "box_16_state_wages_tips": float(wages),
            "box_17_state_income_tax": float(tax),
        }
        evidence[state] = line

    return [state_boxes[state] for state in sorted(state_boxes)], evidence


def extract_tax_year(lines: list[str], fallback_year: int | None = None) -> int | None:
    year_candidates: list[int] = []
    for line in lines:
        # Common W-2 label: "Form W-2 Wage and Tax Statement 2025"
        if "w-2" in line.lower() or "wage and tax" in line.lower():
            for value in re.findall(r"\b20\d{2}\b", line):
                year_candidates.append(int(value))
    if year_candidates:
        return sorted(year_candidates)[-1]
    return fallback_year


def extract_w2_from_lines(lines: list[str], fallback_year: int | None = None) -> dict[str, Any]:
    box_specs: dict[str, tuple[list[re.Pattern[str]], int]] = {
        "box_1_wages_tips_other_comp": (
            [
                re.compile(r"\b1\b.*wages.*other comp", re.IGNORECASE),
                re.compile(r"box\s*1.*wages", re.IGNORECASE),
            ],
            0,
        ),
        "box_2_federal_income_tax_withheld": (
            [
                re.compile(r"\b2\b.*federal income tax", re.IGNORECASE),
                re.compile(r"box\s*2.*federal income tax", re.IGNORECASE),
            ],
            1,
        ),
        "box_3_social_security_wages": (
            [
                re.compile(r"\b3\b.*social security wages", re.IGNORECASE),
                re.compile(r"box\s*3.*social security wages", re.IGNORECASE),
            ],
            0,
        ),
        "box_4_social_security_tax_withheld": (
            [
                re.compile(r"\b4\b.*social security tax", re.IGNORECASE),
                re.compile(r"box\s*4.*social security tax", re.IGNORECASE),
            ],
            1,
        ),
        "box_5_medicare_wages_and_tips": (
            [
                re.compile(r"\b5\b.*medicare wages", re.IGNORECASE),
                re.compile(r"box\s*5.*medicare wages", re.IGNORECASE),
            ],
            0,
        ),
        "box_6_medicare_tax_withheld": (
            [
                re.compile(r"\b6\b.*medicare tax", re.IGNORECASE),
                re.compile(r"box\s*6.*medicare tax", re.IGNORECASE),
            ],
            1,
        ),
    }

    values: dict[str, float | None] = {}
    evidence: dict[str, str | None] = {}
    for field, (patterns, preferred_index) in box_specs.items():
        amount, line = find_amount_for_box(lines, patterns, preferred_index=preferred_index)
        values[field] = float(amount) if amount is not None else None
        evidence[field] = line

    state_boxes, state_evidence = extract_state_boxes(lines)

    return {
        "tax_year": extract_tax_year(lines, fallback_year=fallback_year),
        "box_1_wages_tips_other_comp": values["box_1_wages_tips_other_comp"],
        "box_2_federal_income_tax_withheld": values["box_2_federal_income_tax_withheld"],
        "box_3_social_security_wages": values["box_3_social_security_wages"],
        "box_4_social_security_tax_withheld": values["box_4_social_security_tax_withheld"],
        "box_5_medicare_wages_and_tips": values["box_5_medicare_wages_and_tips"],
        "box_6_medicare_tax_withheld": values["box_6_medicare_tax_withheld"],
        "state_boxes": state_boxes,
        "_meta": {
            "source": "ocr_pdf_parse",
            "evidence": {
                **evidence,
                "state_boxes": state_evidence,
            },
            "notes": [
                "OCR-based W-2 extraction may require manual review before filing.",
                "Use evidence lines to validate extracted box values.",
            ],
        },
    }


def w2_pdf_to_json_payload(
    pdf_path: Path,
    render_scale: float = 3.0,
    psm: int = 6,
    fallback_year: int | None = None,
) -> dict[str, Any]:
    text = ocr_pdf_text(pdf_path, render_scale=render_scale, psm=psm)
    lines = [normalize_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    payload = extract_w2_from_lines(lines, fallback_year=fallback_year)
    payload["_meta"]["source_pdf"] = str(pdf_path)
    return payload
