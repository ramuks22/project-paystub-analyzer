#!/usr/bin/env python3

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium

MONEY_RE = re.compile(
    r"[+-]?(?:\$|S)?(?:\d{1,3}(?:,\s?\d{3})+|\d+)\.\d{2}",
    re.IGNORECASE,
)
ADP_FILENAME_PAY_DATE_RE = re.compile(r"Pay Date (\d{4}-\d{2}-\d{2})(?:_.*)?\.pdf$", re.IGNORECASE)
UKG_FILENAME_PAY_DATE_RE = re.compile(r"^EEPayrollPayCheckDetail_(\d{8})\.pdf$", re.IGNORECASE)
TEXT_PAY_DATE_PRIMARY_RE = re.compile(
    r"Pay Date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
TEXT_PAY_DATE_FALLBACK_RE = re.compile(
    r"(?:Pay Period End|Period Ending)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
STATE_TAX_LINE_RE = re.compile(r"\b([A-Z]{2}) State Income Tax\b", re.IGNORECASE)
MAX_PLAUSIBLE_AMOUNT = Decimal("10000000.00")
OcrTextProvider = Callable[[Path, float, int], str]


@dataclass
class AmountPair:
    this_period: Decimal | None
    ytd: Decimal | None
    source_line: str | None
    is_ytd_confirmed: bool = False  # Track if context/labels confirmed it as YTD


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
    parse_anomalies: list[dict[str, str]] = field(default_factory=list)


def heal_numeric_noise(text: str) -> str:
    """Heal common OCR character swaps and whitespace inside numbers."""
    # S -> $ when followed by digits
    text = re.sub(r"\bS(?=\d)", "$", text)

    # O -> 0, I/l -> 1 when surrounded by digits/separators
    # This is a bit aggressive but often necessary for noisy OCR
    # We only apply it within segments that look like they should be numeric
    def swap_chars(match: re.Match[str]) -> str:
        segment = match.group(0)
        segment = segment.replace("O", "0").replace("o", "0")
        segment = segment.replace("I", "1").replace("l", "1")
        return segment

    # Targeted swap within tokens containing digits
    text = re.sub(r"[\dOIlo,\.]{3,}", swap_chars, text)

    # Remove internal spaces in suspected money tokens
    # e.g. "5, 000.00" -> "5,000.00"
    text = re.sub(r"(\d)\s+([,\.])\s+(\d)", r"\1\2\3", text)
    # We DO NOT want to aggressively replace comma with dot here because it breaks "5, 000.00" -> "5.000.00"
    # Only heal spaces after separators
    text = re.sub(r"(\d)[,\.]\s+(\d)", r"\1\2", text)
    return text


def normalize_line(line: str) -> str:
    line = line.strip()
    line = heal_numeric_noise(line)
    line = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", line)
    line = re.sub(r"(?<!\d)-\s+(\d)", r"-\1", line)
    line = re.sub(r"\s+", " ", line)
    return line


def parse_money(token: str) -> Decimal | None:
    # Clean non-numeric except dot/dash
    clean = re.sub(r"[^\d\.-]", "", token.replace("S", "$").replace("O", "0"))
    if not clean or clean == ".":
        return None
    try:
        return Decimal(clean)
    except Exception:
        return None


def extract_money_values_with_anomalies(line: str) -> tuple[list[Decimal], list[dict[str, str]]]:
    tokens = MONEY_RE.findall(line)
    values: list[Decimal] = []
    anomalies: list[dict[str, str]] = []
    for token in tokens:
        parsed = parse_money(token)
        if parsed is None:
            continue
        abs_value = abs(parsed)
        if abs_value > MAX_PLAUSIBLE_AMOUNT:
            anomalies.append(
                {
                    "code": "implausible_amount_filtered",
                    "severity": "warning",
                    "message": f"Filtered implausible money token `{token}` parsed as {abs_value}.",
                    "evidence": line,
                }
            )
            continue
        values.append(parsed)
    return values, anomalies


def extract_money_values(line: str) -> list[Decimal]:
    values, _ = extract_money_values_with_anomalies(line)
    return values


def guess_field_from_line(line: str) -> str:
    upper = line.upper()
    state_match = STATE_TAX_LINE_RE.search(line)
    if state_match:
        return f"state_income_tax_{state_match.group(1).upper()}"
    if "FEDERAL" in upper or "WITHHOLDING" in upper:
        return "federal_income_tax"
    if "SOCIAL SECURITY" in upper or "SOC SEC" in upper or "SOC." in upper:
        return "social_security_tax"
    if "MEDICARE" in upper:
        return "medicare_tax"
    if "GROSS" in upper or "REGULAR" in upper:
        return "gross_pay"
    if "401" in upper:
        return "k401_contrib"
    return "unknown"


def parse_amount_pair_from_line(line: str) -> AmountPair:
    normalized = normalize_line(line)
    amounts = [abs(value) for value in extract_money_values(normalized)]
    if not amounts:
        return AmountPair(None, None, normalized)

    # Keyword-based disambiguation for single amounts
    is_ytd_explicit = any(k in normalized.upper() for k in ["YTD", "YEAR TO DATE"])
    is_period_explicit = any(k in normalized.upper() for k in ["THIS PERIOD", "CURRENT", "REGULAR", "EARNINGS"])

    if len(amounts) == 1:
        if is_ytd_explicit:
            return AmountPair(None, amounts[0], normalized)
        if is_period_explicit:
            return AmountPair(amounts[0], None, normalized)
        # Default for single value without keyword: this_period
        # Caller (find_line_amount_pair) will resolve YTD context.
        return AmountPair(amounts[0], None, normalized)

    first, second = amounts[0], amounts[1]
    # If the line contains both, usually this period is first.
    # But check if one is explicitly YTD via proximity?
    # For now, stick to the relative magnitude heuristic as it's quite reliable for same-line pairs.
    if second >= first:
        return AmountPair(first, second, normalized)

    # If second is smaller, it might be unrelated column data (like in Gusto column collision).
    # Check if we have explicit markers.
    if is_ytd_explicit:
        return AmountPair(None, first, normalized)
    if is_period_explicit:
        return AmountPair(first, None, normalized)

    # If no keywords, but second is much smaller, assume it's noise/unrelated.
    return AmountPair(first, None, normalized)


def parse_pay_date_from_filename_any(path: Path) -> date | None:
    adp_match = ADP_FILENAME_PAY_DATE_RE.search(path.name)
    if adp_match:
        return datetime.strptime(adp_match.group(1), "%Y-%m-%d").date()

    ukg_match = UKG_FILENAME_PAY_DATE_RE.search(path.name)
    if ukg_match:
        return datetime.strptime(ukg_match.group(1), "%m%d%Y").date()

    return None


def parse_pay_date_from_filename(path: Path) -> date | None:
    # Backward-compatible wrapper used throughout the codebase.
    return parse_pay_date_from_filename_any(path)


def parse_pay_date_from_text(text: str) -> date | None:
    for pattern in (TEXT_PAY_DATE_PRIMARY_RE, TEXT_PAY_DATE_FALLBACK_RE):
        for match in pattern.finditer(text):
            try:
                return datetime.strptime(match.group(1), "%m/%d/%Y").date()
            except ValueError:
                continue
    return None


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
    candidates: list[AmountPair] = []

    # All known labels that might collide in a single line
    # All known labels that might collide in a single line.
    # We use a flexible boundary to handle non-word characters like ')' in '401(k)'.
    ALL_LABELS_PAT = r"(?:^|\s|\|)(Gross Pay|YTD Gross|REGULAR|Total Gross|Gross|Federal Income Tax|Fed Income Tax|Federal Tax|Fed Tax|YTD TAXES|withholding|Social Security|Soc Sec|Soc\. Sec\.|Soc See|Soc|Medicare|Med|401\(k\)|401k|Net Pay|Net|Total|Total Due)(?:\s|\||$|:)"

    for i, line in enumerate(lines):
        line_up = line.upper()
        # Look for all occurrences of the pattern in the line
        for match in compiled.finditer(line):
            matched_label = match.group(0).upper()

            # 1. Detect orientation context
            # Explicit label markers in the text itself (e.g. "Gross YTD")
            is_ytd_explicit = any(k in matched_label for k in ["YTD", "TOTAL", "YEAR TO DATE"])

            # 2. Extract context_text but stop if another known label starts
            remaining = line[match.end() :]
            start_off = match.start()
            next_label = re.search(ALL_LABELS_PAT, remaining, re.IGNORECASE)
            context_text = remaining[: next_label.start()] if next_label else remaining

            # Boundary for right-side context: next label or end of line (max 50 chars)
            next_start = next_label.start() if next_label else (len(remaining) + 0)
            right_limit = min(50, next_start)

            # Context only includes text belonging to THIS match
            local_context = line_up[max(0, start_off - 20) : start_off] + remaining[:right_limit].upper()
            is_ytd_marker = any(k in local_context for k in ["YTD", "YEAR TO DATE", "TOTAL"])

            # Section header markers (look back 2 lines)
            lookback = " ".join(lines[max(0, i - 2) : i]).upper()
            is_ytd_section = any(k in lookback for k in ["YEAR TO DATE", "YTD TOTALS", "YTD TAXES", "YTD INFORMATION"])

            pair = parse_amount_pair_from_line(context_text)

            # 3. Resolve YTD vs Period
            # Period labels (REGULAR) take precedence over section headers
            is_period_label = any(k in matched_label for k in ["REGULAR", "PERIOD", "CURRENT", "EARNINGS"])
            final_is_ytd = is_ytd_explicit or is_ytd_marker or is_ytd_section
            if is_period_label and not is_ytd_explicit:
                final_is_ytd = False

            if final_is_ytd and pair.ytd is None and pair.this_period is not None:
                pair.ytd = pair.this_period
                pair.this_period = None

            if final_is_ytd:
                pair.is_ytd_confirmed = True

            candidates.append(pair)

    if not candidates:
        return AmountPair(None, None, None)

    # 1. Look for a perfect pair in a single line
    for c in candidates:
        if c.this_period is not None and c.ytd is not None:
            return c

    # 2. Aggregate from multiple lines, prioritizing explicit labels
    best_this_period: Decimal | None = None
    best_ytd: Decimal | None = None
    sources: list[str] = []

    # Priority 1: Explicitly labeled period values
    for c in candidates:
        source_up = (c.source_line or "").upper()
        is_period = any(k in source_up for k in ["THIS PERIOD", "CURRENT", "REGULAR", "EARNINGS"])
        if is_period and c.this_period is not None:
            best_this_period = c.this_period
            if c.source_line:
                sources.append(c.source_line)
            break

    # Priority 2: Confirmed YTD values (via label, marker, or section)
    for c in candidates:
        source_up = (c.source_line or "").upper()
        if c.is_ytd_confirmed and c.ytd is not None:
            # Prefer labels that actually CONTAIN 'YTD' over generic markers
            is_explicit = any(k in source_up for k in ["YTD", "YEAR TO DATE"])
            if best_ytd is None or (is_explicit and "YTD" not in (sources[0] if sources else "")):
                best_ytd = c.ytd
                if c.source_line and c.source_line not in sources:
                    sources.append(c.source_line)
            if is_explicit:
                # Highly confident in explicit YTD label
                break

    # Priority 3: Fallbacks (First available)
    if best_this_period is None:
        for c in candidates:
            if c.this_period is not None:
                best_this_period = c.this_period
                if c.source_line and c.source_line not in sources:
                    sources.append(c.source_line)
                break

    if best_ytd is None:
        for c in candidates:
            if c.ytd is not None:
                best_ytd = c.ytd
                if c.source_line not in sources and c.source_line:
                    sources.append(c.source_line)
                break

    return AmountPair(this_period=best_this_period, ytd=best_ytd, source_line=" | ".join(sources) if sources else None)


def extract_state_tax_pairs(lines: list[str]) -> dict[str, AmountPair]:
    result: dict[str, AmountPair] = {}
    for line in lines:
        match = STATE_TAX_LINE_RE.search(line)
        if not match:
            continue
        state = match.group(1).upper()
        pair = parse_amount_pair_from_line(line)
        # If line has ONLY one value, it might be this_period (common for state taxes in some views)
        # We accept it if EITHER this_period or ytd is found.
        if pair.ytd is None and pair.this_period is None:
            continue

        existing = result.get(state)
        if existing is None:
            result[state] = pair
            continue
        existing_ytd = existing.ytd or Decimal("0.00")
        if (pair.ytd or Decimal("0.00")) > existing_ytd:
            result[state] = pair
    return result


def extract_ukg_pay_summary_gross_pair(lines: list[str]) -> AmountPair:
    pay_summary_index: int | None = None
    for index, line in enumerate(lines):
        if "PAY SUMMARY" in line.upper():
            pay_summary_index = index
            break

    if pay_summary_index is None:
        return AmountPair(None, None, None)

    current: Decimal | None = None
    ytd: Decimal | None = None
    sources: list[str] = []

    for line in lines[pay_summary_index + 1 : pay_summary_index + 12]:
        upper = line.upper()
        if upper.startswith("CURRENT"):
            amounts = [abs(value) for value in extract_money_values(line)]
            if amounts:
                current = amounts[0]
                sources.append(line)
            continue
        if upper.startswith("YTD"):
            amounts = [abs(value) for value in extract_money_values(line)]
            if amounts:
                ytd = amounts[0]
                sources.append(line)
            continue
        if (
            current is not None
            and ytd is not None
            and (
                upper.startswith("PAID TIME OFF")
                or upper.startswith("PLAN ")
                or upper.startswith("EARNINGS")
                or upper.startswith("DEDUCTIONS")
                or upper.startswith("TAX")
            )
        ):
            break

    if current is None and ytd is None:
        return AmountPair(None, None, None)

    return AmountPair(
        this_period=current,
        ytd=ytd,
        source_line=" | ".join(dict.fromkeys(sources)) if sources else "Pay Summary",
        is_ytd_confirmed=ytd is not None,
    )


def extract_regular_wages_pair(lines: list[str]) -> AmountPair:
    for line in lines:
        if re.search(r"\b(REGULAR|REGULAR EARNING)\b", line, re.IGNORECASE) is None:
            continue
        amounts = [abs(value) for value in extract_money_values(line)]
        wage_amounts = [amount for amount in amounts if amount >= Decimal("250.00")]
        if len(wage_amounts) >= 2:
            return AmountPair(
                this_period=wage_amounts[0],
                ytd=wage_amounts[1],
                source_line=line,
            )
    return AmountPair(None, None, None)


def extract_adp_gross_line_pair(lines: list[str]) -> AmountPair:
    for line in lines:
        if re.search(r"\bGross Pay\b", line, re.IGNORECASE) is None:
            continue

        amounts = [abs(value) for value in extract_money_values(line)]
        if len(amounts) < 2:
            continue

        first = amounts[0]
        second = amounts[1]
        if second >= first:
            return AmountPair(first, second, line, is_ytd_confirmed=True)

        # ADP collision case: OCR can prepend an unrelated larger column before Gross YTD.
        # Example: "Gross Pay 81,704.78 27,788.98 ...", where 27,788.98 is the true YTD.
        if first >= Decimal("10000.00") and second >= Decimal("1000.00") and first >= second * Decimal("1.50"):
            return AmountPair(None, second, line, is_ytd_confirmed=True)

    return AmountPair(None, None, None)


def extract_gross_pay_pair(lines: list[str]) -> AmountPair:
    ukg_pay_summary = extract_ukg_pay_summary_gross_pair(lines)
    if ukg_pay_summary.this_period is not None or ukg_pay_summary.ytd is not None:
        return ukg_pay_summary

    adp_gross_line = extract_adp_gross_line_pair(lines)
    regular_wages = extract_regular_wages_pair(lines)
    if adp_gross_line.ytd is not None:
        this_candidate = adp_gross_line.this_period
        if (
            this_candidate is None
            and regular_wages.this_period is not None
            and regular_wages.this_period < adp_gross_line.ytd
        ):
            this_candidate = regular_wages.this_period
        merged_source_parts = [part for part in [adp_gross_line.source_line, regular_wages.source_line] if part]
        return AmountPair(
            this_period=this_candidate,
            ytd=adp_gross_line.ytd,
            source_line=" | ".join(dict.fromkeys(merged_source_parts)),
            is_ytd_confirmed=True,
        )

    # Prefer explicit gross labels first. "REGULAR" is kept only as fallback because
    # some layouts have separate regular earnings rows that can collide with gross rows.
    strict = find_line_amount_pair(lines, r"\b(Gross Pay|YTD Gross|Total Gross|Gross)\b")
    regular = find_line_amount_pair(lines, r"\b(REGULAR)\b")

    if strict.ytd is not None:
        return strict

    if strict.this_period is None and strict.ytd is None:
        return regular

    # OCR can drop punctuation in this-period on "Gross Pay" lines and leave a single
    # large value that is actually YTD. If that happens, salvage this-period from a
    # regular row and treat the strict large value as YTD.
    strict_value = strict.this_period
    if strict_value is not None and strict_value >= Decimal("10000.00"):
        regular_this = regular.this_period
        regular_ytd = regular.ytd
        this_candidate = regular_ytd if regular_ytd is not None and regular_ytd < strict_value else regular_this
        if this_candidate is not None and this_candidate <= strict_value:
            merged_source_parts = [part for part in [strict.source_line, regular.source_line] if part]
            return AmountPair(
                this_period=this_candidate,
                ytd=strict_value,
                source_line=" | ".join(dict.fromkeys(merged_source_parts)),
                is_ytd_confirmed=True,
            )

    return strict


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
    parse_anomalies: list[dict[str, str]] = []
    seen_anomalies: set[tuple[str, str, str]] = set()
    for index, line in enumerate(lines):
        _, anomalies = extract_money_values_with_anomalies(line)
        for anomaly in anomalies:
            enriched = dict(anomaly)
            enriched["field_guess"] = guess_field_from_line(line)
            enriched["line_index"] = str(index + 1)
            key = (
                enriched.get("code", ""),
                enriched.get("message", ""),
                enriched.get("evidence", ""),
            )
            if key in seen_anomalies:
                continue
            seen_anomalies.add(key)
            parse_anomalies.append(enriched)

    pay_date = parse_pay_date_from_text(text)
    if pay_date is None:
        pay_date = parse_pay_date_from_filename(pdf_path)
    gross_pair = extract_gross_pay_pair(lines)

    source_line = gross_pair.source_line or ""
    source_upper = source_line.upper()
    if (
        gross_pair.this_period is not None
        and gross_pair.this_period <= Decimal("250.00")
        and "HOUR" in source_upper
        and "GROSS" not in source_upper
    ):
        evidence = source_line.split(" | ")[0].strip()
        parse_anomalies.append(
            {
                "code": "gross_hours_suspected",
                "severity": "warning",
                "message": (
                    "Gross pay extraction may have captured hours instead of pay amount. "
                    "Review gross pay evidence line."
                ),
                "evidence": evidence,
                "field_guess": "gross_pay",
                "line_index": str(lines.index(evidence) + 1) if evidence in lines else "",
            }
        )

    return PaystubSnapshot(
        file=str(pdf_path),
        pay_date=pay_date.isoformat() if pay_date else None,
        gross_pay=gross_pair,
        federal_income_tax=find_line_amount_pair(
            lines, r"\b(Federal Income Tax|Fed Income Tax|Federal Tax|withholding)\b"
        ),
        social_security_tax=find_line_amount_pair(lines, r"\b(Social Security Tax|Soc Sec|Social Security)\b"),
        medicare_tax=find_line_amount_pair(lines, r"\b(Medicare Tax|Medicare|Med)\b"),
        k401_contrib=find_line_amount_pair(lines, r"\b(401\(K\) Contrib|401k)\b"),
        state_income_tax=extract_state_tax_pairs(lines),
        normalized_lines=lines,
        parse_anomalies=parse_anomalies,
    )


def list_paystub_files(paystub_dir: Path, year: int | None) -> list[Path]:
    files = sorted(paystub_dir.glob("*.pdf"))
    if year is None:
        return files
    filtered: list[Path] = []
    for file_path in files:
        pay_date = parse_pay_date_from_filename(file_path)
        # Keep unresolved files so users can assign pay dates manually in UI/CLI overrides.
        if pay_date is None or pay_date.year == year:
            filtered.append(file_path)
    return filtered


def select_latest_paystub(files: list[Path]) -> tuple[Path, date]:
    dated: list[tuple[Path, date]] = []
    unresolved: list[str] = []
    for file_path in files:
        pay_date = parse_pay_date_from_filename(file_path)
        if pay_date is not None:
            dated.append((file_path, pay_date))
        else:
            unresolved.append(file_path.name)
    if not dated:
        unresolved_preview = ", ".join(sorted(unresolved)[:5])
        if len(unresolved) > 5:
            unresolved_preview += ", ..."
        raise RuntimeError(
            "Could not determine pay dates from paystub filenames. "
            f"Unresolved files: {unresolved_preview or 'none'}."
        )
    return sorted(dated, key=lambda item: (item[1], item[0].name))[-1]


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
