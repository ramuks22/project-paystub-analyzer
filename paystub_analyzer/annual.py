#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from paystub_analyzer.core import (
    AmountPair,
    PaystubSnapshot,
    as_float,
    extract_paystub_snapshot,
    format_money,
    list_paystub_files,
    parse_pay_date_from_filename,
    sum_state_this_period,
    sum_state_ytd,
)
from paystub_analyzer.w2 import compare_snapshot_to_w2

STATE_YTD_OUTLIER_MIN_ABS = Decimal("250.00")
STATE_YTD_NEIGHBOR_TOLERANCE = Decimal("1.00")
STATE_YTD_SPIKE_MULTIPLIER = Decimal("4.00")


@dataclass
class ConsistencyIssue:
    severity: str
    code: str
    message: str


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def snapshot_sort_key(snapshot: PaystubSnapshot) -> tuple[date, str]:
    parsed = parse_iso_date(snapshot.pay_date)
    if parsed is None:
        parsed = parse_pay_date_from_filename(Path(snapshot.file))
    if parsed is None:
        parsed = date.min
    return (parsed, snapshot.file)


def collect_annual_snapshots(
    paystubs_dir: Path,
    year: int,
    render_scale: float = 2.5,
    psm: int = 6,
) -> list[PaystubSnapshot]:
    files = list_paystub_files(paystubs_dir, year=year)
    snapshots = [extract_paystub_snapshot(path, render_scale=render_scale, psm=psm) for path in files]
    snapshots.sort(key=snapshot_sort_key)
    return snapshots


def clone_snapshots(snapshots: list[PaystubSnapshot]) -> list[PaystubSnapshot]:
    cloned: list[PaystubSnapshot] = []
    for snapshot in snapshots:
        state_copy = {
            state: AmountPair(pair.this_period, pair.ytd, pair.source_line)
            for state, pair in snapshot.state_income_tax.items()
        }
        cloned.append(
            PaystubSnapshot(
                file=snapshot.file,
                pay_date=snapshot.pay_date,
                gross_pay=snapshot.gross_pay,
                federal_income_tax=snapshot.federal_income_tax,
                social_security_tax=snapshot.social_security_tax,
                medicare_tax=snapshot.medicare_tax,
                k401_contrib=snapshot.k401_contrib,
                state_income_tax=state_copy,
                normalized_lines=list(snapshot.normalized_lines),
            )
        )
    return cloned


def verify_and_repair_state_ytd_anomalies(
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
) -> tuple[list[PaystubSnapshot], list[ConsistencyIssue], dict[str, list[str]]]:
    if not snapshots:
        return snapshots, [], {}

    repaired = clone_snapshots(snapshots)
    issues: list[ConsistencyIssue] = []
    notes_by_file: dict[str, list[str]] = {}
    states = sorted({state for snapshot in repaired for state in snapshot.state_income_tax.keys()})

    for state in states:
        indices = [
            idx
            for idx, snapshot in enumerate(repaired)
            if state in snapshot.state_income_tax and snapshot.state_income_tax[state].ytd is not None
        ]
        for position, idx in enumerate(indices):
            snapshot = repaired[idx]
            pair = snapshot.state_income_tax[state]
            current_ytd = pair.ytd
            if current_ytd is None:
                continue

            prev_ytd = None
            next_ytd = None
            if position > 0:
                prev_ytd = repaired[indices[position - 1]].state_income_tax[state].ytd
            if position + 1 < len(indices):
                next_ytd = repaired[indices[position + 1]].state_income_tax[state].ytd

            corrected_ytd = None
            corrected_this = pair.this_period
            reason = None

            if (
                prev_ytd is not None
                and next_ytd is not None
                and abs(prev_ytd - next_ytd) <= STATE_YTD_NEIGHBOR_TOLERANCE
            ):
                anchor_ytd = ((prev_ytd + next_ytd) / Decimal("2")).quantize(Decimal("0.01"))
                if (
                    current_ytd > anchor_ytd + STATE_YTD_OUTLIER_MIN_ABS
                    and current_ytd > anchor_ytd * STATE_YTD_SPIKE_MULTIPLIER
                ):
                    corrected_ytd = anchor_ytd
                    if (
                        corrected_this is not None
                        and abs(corrected_this - corrected_ytd) <= max(tolerance, Decimal("0.01"))
                        and (pair.source_line is None or "-" not in pair.source_line)
                    ):
                        corrected_this = None
                    reason = "neighbor_consistency"
            elif prev_ytd is None and next_ytd is not None and pair.this_period is not None:
                if (
                    current_ytd > next_ytd + STATE_YTD_OUTLIER_MIN_ABS
                    and current_ytd > next_ytd * STATE_YTD_SPIKE_MULTIPLIER
                    and pair.this_period <= next_ytd + max(tolerance, Decimal("0.05"))
                ):
                    corrected_ytd = pair.this_period
                    reason = "opening_entry_spike"
            elif prev_ytd is not None and next_ytd is None and pair.this_period is not None:
                if (
                    current_ytd > prev_ytd + STATE_YTD_OUTLIER_MIN_ABS
                    and current_ytd > prev_ytd * STATE_YTD_SPIKE_MULTIPLIER
                    and abs(pair.this_period - prev_ytd) <= Decimal("0.50")
                    and (pair.source_line is None or "-" not in pair.source_line)
                ):
                    corrected_ytd = prev_ytd
                    corrected_this = None
                    reason = "closing_entry_spike"

            if corrected_ytd is None:
                continue

            snapshot.state_income_tax[state] = AmountPair(corrected_this, corrected_ytd, pair.source_line)
            target = snapshot.pay_date or snapshot.file
            message = (
                f"{state} state tax YTD on {target} was auto-corrected from "
                f"{format_money(current_ytd)} to {format_money(corrected_ytd)} ({reason})."
            )
            issues.append(
                ConsistencyIssue(
                    severity="warning",
                    code="state_ytd_outlier_corrected",
                    message=message,
                )
            )
            notes_by_file.setdefault(snapshot.file, []).append(
                f"{state}: {format_money(current_ytd)} -> {format_money(corrected_ytd)}"
            )

    return repaired, issues, notes_by_file


def row_total_state_this(snapshot: PaystubSnapshot) -> Decimal:
    return sum_state_this_period(snapshot.state_income_tax)


def row_total_state_ytd(snapshot: PaystubSnapshot) -> Decimal:
    return sum_state_ytd(snapshot.state_income_tax)


def state_dict(snapshot: PaystubSnapshot, field: str) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for state, pair in sorted(snapshot.state_income_tax.items()):
        value = pair.this_period if field == "this_period" else pair.ytd
        result[state] = as_float(value)
    return result


def build_ledger_rows(
    snapshots: list[PaystubSnapshot],
    verification_notes_by_file: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        notes = (verification_notes_by_file or {}).get(snapshot.file, [])
        rows.append(
            {
                "pay_date": snapshot.pay_date,
                "file": snapshot.file,
                "gross_pay_this_period": as_float(snapshot.gross_pay.this_period),
                "gross_pay_ytd": as_float(snapshot.gross_pay.ytd),
                "federal_tax_this_period": as_float(snapshot.federal_income_tax.this_period),
                "federal_tax_ytd": as_float(snapshot.federal_income_tax.ytd),
                "social_security_tax_this_period": as_float(snapshot.social_security_tax.this_period),
                "social_security_tax_ytd": as_float(snapshot.social_security_tax.ytd),
                "medicare_tax_this_period": as_float(snapshot.medicare_tax.this_period),
                "medicare_tax_ytd": as_float(snapshot.medicare_tax.ytd),
                "state_tax_this_period_total": as_float(row_total_state_this(snapshot)),
                "state_tax_ytd_total": as_float(row_total_state_ytd(snapshot)),
                "state_tax_this_period_by_state": state_dict(snapshot, "this_period"),
                "state_tax_ytd_by_state": state_dict(snapshot, "ytd"),
                "ytd_verification": " | ".join(notes),
            }
        )
    return rows


def merge_verification_notes(*maps: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for notes_map in maps:
        for file_path, notes in notes_map.items():
            merged.setdefault(file_path, [])
            merged[file_path].extend(notes)
    for file_path in merged:
        merged[file_path] = list(dict.fromkeys(merged[file_path]))
    return merged


def record_note(notes_by_file: dict[str, list[str]], file_path: str, note: str) -> None:
    notes_by_file.setdefault(file_path, []).append(note)


def verify_ytd_calculations(
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
) -> tuple[dict[str, list[str]], list[ConsistencyIssue]]:
    notes_by_file: dict[str, list[str]] = {}
    issues: list[ConsistencyIssue] = []
    prev_snapshot: PaystubSnapshot | None = None

    for snapshot in snapshots:
        if prev_snapshot is None:
            prev_snapshot = snapshot
            continue

        field_pairs = [
            ("gross_pay", prev_snapshot.gross_pay, snapshot.gross_pay),
            ("federal_income_tax", prev_snapshot.federal_income_tax, snapshot.federal_income_tax),
            ("social_security_tax", prev_snapshot.social_security_tax, snapshot.social_security_tax),
            ("medicare_tax", prev_snapshot.medicare_tax, snapshot.medicare_tax),
        ]
        for label, prev_pair, curr_pair in field_pairs:
            if prev_pair.ytd is None or curr_pair.ytd is None:
                continue
            if curr_pair.ytd + tolerance < prev_pair.ytd:
                note = (
                    f"{label} YTD decreased {format_money(prev_pair.ytd)} -> {format_money(curr_pair.ytd)}"
                )
                record_note(notes_by_file, snapshot.file, note)
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="ytd_calc_decrease",
                        message=f"{label} YTD decreased on {snapshot.pay_date}.",
                    )
                )
            if curr_pair.this_period is None:
                continue
            expected_ytd = (prev_pair.ytd + curr_pair.this_period).quantize(Decimal("0.01"))
            if abs(curr_pair.ytd - expected_ytd) > tolerance:
                note = (
                    f"{label} parsed YTD {format_money(curr_pair.ytd)} vs calculated "
                    f"{format_money(expected_ytd)}"
                )
                record_note(notes_by_file, snapshot.file, note)
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="ytd_calc_mismatch",
                        message=(
                            f"{label} on {snapshot.pay_date} differs from calculated YTD "
                            f"({format_money(curr_pair.ytd)} vs {format_money(expected_ytd)})."
                        ),
                    )
                )

        states = sorted(set(prev_snapshot.state_income_tax.keys()) | set(snapshot.state_income_tax.keys()))
        for state in states:
            prev_pair = prev_snapshot.state_income_tax.get(state)
            curr_pair = snapshot.state_income_tax.get(state)
            if prev_pair is None or curr_pair is None:
                continue
            if prev_pair.ytd is None or curr_pair.ytd is None:
                continue
            if curr_pair.ytd + tolerance < prev_pair.ytd:
                note = (
                    f"{state} state YTD decreased {format_money(prev_pair.ytd)} -> {format_money(curr_pair.ytd)}"
                )
                record_note(notes_by_file, snapshot.file, note)
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="state_ytd_decrease",
                        message=f"{state} YTD decreased on {snapshot.pay_date}.",
                    )
                )
            if curr_pair.this_period is None:
                continue
            expected_ytd = (prev_pair.ytd + curr_pair.this_period).quantize(Decimal("0.01"))
            if abs(curr_pair.ytd - expected_ytd) > tolerance:
                note = (
                    f"{state} parsed YTD {format_money(curr_pair.ytd)} vs calculated "
                    f"{format_money(expected_ytd)}"
                )
                record_note(notes_by_file, snapshot.file, note)
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="state_ytd_calc_mismatch",
                        message=(
                            f"{state} state YTD on {snapshot.pay_date} differs from calculated "
                            f"({format_money(curr_pair.ytd)} vs {format_money(expected_ytd)})."
                        ),
                    )
                )

        prev_snapshot = snapshot

    return notes_by_file, issues


def pair_attr(snapshot: PaystubSnapshot, key: str) -> AmountPair:
    if key == "gross_pay":
        return snapshot.gross_pay
    if key == "federal_tax":
        return snapshot.federal_income_tax
    if key == "social_security_tax":
        return snapshot.social_security_tax
    if key == "medicare_tax":
        return snapshot.medicare_tax
    raise ValueError(f"Unsupported key: {key}")


def check_monotonic(
    snapshots: list[PaystubSnapshot],
    label: str,
    getter,
    tolerance: Decimal,
    severity: str = "critical",
) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    previous = None
    previous_date = None
    for snapshot in snapshots:
        current = getter(snapshot)
        if current is None:
            continue
        if previous is not None and current + tolerance < previous:
            issues.append(
                ConsistencyIssue(
                    severity=severity,
                    code="ytd_decrease",
                    message=(
                        f"{label} YTD decreased on {snapshot.pay_date}: "
                        f"{format_money(previous)} -> {format_money(current)}"
                    ),
                )
            )
        previous = current
        previous_date = snapshot.pay_date
    _ = previous_date
    return issues


def check_this_period_consistency(
    snapshots: list[PaystubSnapshot],
    pair_name: str,
    tolerance: Decimal,
) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    prev_snapshot: PaystubSnapshot | None = None
    for snapshot in snapshots:
        pair = pair_attr(snapshot, pair_name)
        if prev_snapshot is None:
            prev_snapshot = snapshot
            continue

        prev_pair = pair_attr(prev_snapshot, pair_name)
        if prev_pair.ytd is None or pair.ytd is None or pair.this_period is None:
            prev_snapshot = snapshot
            continue

        expected = pair.ytd - prev_pair.ytd
        if expected < Decimal("0.00"):
            prev_snapshot = snapshot
            continue
        if abs(expected - pair.this_period) > tolerance:
            issues.append(
                ConsistencyIssue(
                    severity="warning",
                    code="this_period_vs_ytd_delta",
                    message=(
                        f"{pair_name} this-period amount on {snapshot.pay_date} "
                        f"({format_money(pair.this_period)}) differs from YTD delta "
                        f"({format_money(expected)})."
                    ),
                )
            )
        prev_snapshot = snapshot
    return issues


def detect_duplicate_dates(snapshots: list[PaystubSnapshot]) -> list[ConsistencyIssue]:
    seen: dict[str, int] = {}
    for snapshot in snapshots:
        if snapshot.pay_date:
            seen[snapshot.pay_date] = seen.get(snapshot.pay_date, 0) + 1

    issues: list[ConsistencyIssue] = []
    for pay_date, count in sorted(seen.items()):
        if count > 1:
            issues.append(
                ConsistencyIssue(
                    severity="warning",
                    code="duplicate_pay_date",
                    message=f"Found {count} paystubs with pay date {pay_date}.",
                )
            )
    return issues


def snapshot_quality_tuple(snapshot: PaystubSnapshot) -> tuple[int, Decimal, Decimal, Decimal, str]:
    candidates = [
        snapshot.gross_pay.ytd,
        snapshot.federal_income_tax.ytd,
        snapshot.social_security_tax.ytd,
        snapshot.medicare_tax.ytd,
        row_total_state_ytd(snapshot),
    ]
    completeness = sum(1 for value in candidates if value is not None)
    gross = snapshot.gross_pay.ytd or Decimal("0.00")
    federal = snapshot.federal_income_tax.ytd or Decimal("0.00")
    state = row_total_state_ytd(snapshot)
    return (completeness, gross, federal, state, snapshot.file)


def deduplicate_by_pay_date(
    snapshots: list[PaystubSnapshot],
) -> tuple[list[PaystubSnapshot], list[ConsistencyIssue]]:
    grouped: dict[str, list[PaystubSnapshot]] = {}
    no_date: list[PaystubSnapshot] = []
    for snapshot in snapshots:
        if snapshot.pay_date is None:
            no_date.append(snapshot)
            continue
        grouped.setdefault(snapshot.pay_date, []).append(snapshot)

    canonical: list[PaystubSnapshot] = []
    issues: list[ConsistencyIssue] = []
    for pay_date in sorted(grouped):
        group = grouped[pay_date]
        if len(group) == 1:
            canonical.append(group[0])
            continue

        best = sorted(group, key=snapshot_quality_tuple)[-1]
        canonical.append(best)
        ignored = [item.file for item in group if item.file != best.file]
        issues.append(
            ConsistencyIssue(
                severity="warning",
                code="duplicate_pay_date",
                message=(
                    f"Found {len(group)} paystubs for {pay_date}. "
                    f"Using `{best.file}` as canonical and ignoring: {', '.join(ignored)}"
                ),
            )
        )

    canonical.extend(no_date)
    canonical.sort(key=snapshot_sort_key)
    return canonical, issues


def run_consistency_checks(
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    canonical, duplicate_issues = deduplicate_by_pay_date(snapshots)
    issues.extend(duplicate_issues)

    issues.extend(
        check_monotonic(
            canonical,
            label="Gross pay",
            getter=lambda s: s.gross_pay.ytd,
            tolerance=tolerance,
            severity="critical",
        )
    )
    issues.extend(
        check_monotonic(
            canonical,
            label="Federal income tax",
            getter=lambda s: s.federal_income_tax.ytd,
            tolerance=tolerance,
            severity="warning",
        )
    )
    issues.extend(
        check_monotonic(
            canonical,
            label="Social Security tax",
            getter=lambda s: s.social_security_tax.ytd,
            tolerance=tolerance,
            severity="warning",
        )
    )
    issues.extend(
        check_monotonic(
            canonical,
            label="Medicare tax",
            getter=lambda s: s.medicare_tax.ytd,
            tolerance=tolerance,
            severity="warning",
        )
    )
    issues.extend(
        check_monotonic(
            canonical,
            label="State income tax total",
            getter=lambda s: row_total_state_ytd(s),
            tolerance=tolerance,
            severity="warning",
        )
    )

    for pair_name in ["federal_tax", "social_security_tax", "medicare_tax"]:
        issues.extend(check_this_period_consistency(canonical, pair_name, tolerance=tolerance))

    if canonical:
        final = canonical[-1]
        missing_fields = []
        if final.federal_income_tax.ytd is None:
            missing_fields.append("federal_income_tax_ytd")
        if final.social_security_tax.ytd is None:
            missing_fields.append("social_security_tax_ytd")
        if final.medicare_tax.ytd is None:
            missing_fields.append("medicare_tax_ytd")
        if final.gross_pay.ytd is None:
            missing_fields.append("gross_pay_ytd")
        if missing_fields:
            issues.append(
                ConsistencyIssue(
                    severity="critical",
                    code="missing_final_values",
                    message="Missing final YTD values: " + ", ".join(missing_fields),
                )
            )

    return issues


def extracted_summary(snapshot: PaystubSnapshot) -> dict[str, Any]:
    return {
        "gross_pay": {
            "this_period": as_float(snapshot.gross_pay.this_period),
            "ytd": as_float(snapshot.gross_pay.ytd),
            "evidence": snapshot.gross_pay.source_line,
        },
        "federal_income_tax": {
            "this_period": as_float(snapshot.federal_income_tax.this_period),
            "ytd": as_float(snapshot.federal_income_tax.ytd),
            "evidence": snapshot.federal_income_tax.source_line,
        },
        "social_security_tax": {
            "this_period": as_float(snapshot.social_security_tax.this_period),
            "ytd": as_float(snapshot.social_security_tax.ytd),
            "evidence": snapshot.social_security_tax.source_line,
        },
        "medicare_tax": {
            "this_period": as_float(snapshot.medicare_tax.this_period),
            "ytd": as_float(snapshot.medicare_tax.ytd),
            "evidence": snapshot.medicare_tax.source_line,
        },
        "k401_contrib": {
            "this_period": as_float(snapshot.k401_contrib.this_period),
            "ytd": as_float(snapshot.k401_contrib.ytd),
            "evidence": snapshot.k401_contrib.source_line,
        },
        "state_income_tax": {
            state: {
                "this_period": as_float(pair.this_period),
                "ytd": as_float(pair.ytd),
                "evidence": pair.source_line,
            }
            for state, pair in sorted(snapshot.state_income_tax.items())
        },
    }


def authenticity_assessment(
    consistency_issues: list[ConsistencyIssue],
    comparisons: list[dict[str, Any]],
) -> dict[str, Any]:
    critical = sum(1 for issue in consistency_issues if issue.severity == "critical")
    warnings = sum(1 for issue in consistency_issues if issue.severity == "warning")

    mismatch = sum(1 for row in comparisons if row.get("status") == "mismatch")
    missing_paystub = sum(1 for row in comparisons if row.get("status") == "missing_paystub_value")
    missing_w2 = sum(1 for row in comparisons if row.get("status") == "missing_w2_value")

    score = 100
    score -= critical * 35
    score -= min(warnings, 20) * 3
    score -= mismatch * 20
    score -= missing_paystub * 12
    score -= missing_w2 * 4
    score = max(0, score)

    if mismatch == 0 and critical == 0 and missing_paystub == 0:
        verdict = "strong_consistency"
    elif mismatch <= 1 and critical == 0:
        verdict = "moderate_consistency"
    else:
        verdict = "review_required"

    return {
        "score": score,
        "verdict": verdict,
        "disclaimer": (
            "This is a consistency check based on extracted payroll values and cannot by itself prove legal authenticity."
        ),
    }


def filing_checklist(tax_year: int, states: list[str]) -> list[dict[str, str]]:
    filing_year = tax_year + 1
    checklist = [
        {
            "item": "Verify W-2 identifiers",
            "detail": "Confirm your name, SSN, employer EIN, and address exactly match tax records.",
        },
        {
            "item": "Confirm withholding totals",
            "detail": "Match W-2 boxes 2, 4, 6 and state box 17 values with final paystub YTD totals.",
        },
        {
            "item": "Enter W-2 values in tax software",
            "detail": "Use W-2 as the source-of-truth for filing; use paystub report only for cross-verification.",
        },
        {
            "item": "Attach additional forms",
            "detail": "Add 1099s, interest, dividends, and deductions/credits before filing.",
        },
        {
            "item": "Review filing deadline",
            "detail": (
                f"Federal return for tax year {tax_year} is generally due by April 15, {filing_year}. "
                "If the date falls on a weekend or holiday, use the next business day."
            ),
        },
    ]

    known_state_deadlines = {
        "AZ": f"April 15, {filing_year}",
        "VA": f"May 1, {filing_year}",
    }
    for state in sorted(states):
        if state in known_state_deadlines:
            checklist.append(
                {
                    "item": f"{state} state return deadline",
                    "detail": (
                        f"{state} individual return is typically due by {known_state_deadlines[state]} "
                        "(or next business day if weekend/holiday)."
                    ),
                }
            )
        else:
            checklist.append(
                {
                    "item": f"{state} state return check",
                    "detail": f"Verify {state} filing due date on the official state tax department website.",
                }
            )
    return checklist


def build_tax_filing_package(
    tax_year: int,
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
    w2_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if not snapshots:
        raise ValueError("No snapshots available to build filing package.")

    verified_snapshots, ytd_repair_issues, verification_notes_by_file = verify_and_repair_state_ytd_anomalies(
        snapshots,
        tolerance=tolerance,
    )
    canonical_snapshots, duplicate_issues = deduplicate_by_pay_date(verified_snapshots)
    ytd_calc_notes, ytd_calc_issues = verify_ytd_calculations(
        canonical_snapshots,
        tolerance=tolerance,
    )
    combined_notes = merge_verification_notes(verification_notes_by_file, ytd_calc_notes)
    final_snapshot = canonical_snapshots[-1]
    ledger = build_ledger_rows(
        canonical_snapshots,
        verification_notes_by_file=combined_notes,
    )
    issues = ytd_repair_issues + ytd_calc_issues + duplicate_issues + run_consistency_checks(
        canonical_snapshots, tolerance=tolerance
    )

    comparisons: list[dict[str, Any]] = []
    comparison_summary: dict[str, int] = {}
    if w2_data is not None:
        comparisons, comparison_summary = compare_snapshot_to_w2(final_snapshot, w2_data, tolerance)

    assessment = authenticity_assessment(issues, comparisons)

    critical_issue_count = sum(1 for issue in issues if issue.severity == "critical")
    mismatch_count = sum(1 for row in comparisons if row.get("status") == "mismatch")
    missing_paystub_count = sum(1 for row in comparisons if row.get("status") == "missing_paystub_value")
    ready_to_file = bool(w2_data) and critical_issue_count == 0 and mismatch_count == 0 and missing_paystub_count == 0

    payload: dict[str, Any] = {
        "tax_year": tax_year,
        "paystub_count_raw": len(snapshots),
        "paystub_count_canonical": len(canonical_snapshots),
        "latest_paystub_file": final_snapshot.file,
        "latest_pay_date": final_snapshot.pay_date,
        "extracted": extracted_summary(final_snapshot),
        "ledger": ledger,
        "consistency_issues": [issue.__dict__ for issue in issues],
        "authenticity_assessment": assessment,
        "ready_to_file": ready_to_file,
        "filing_checklist": filing_checklist(
            tax_year, states=list(final_snapshot.state_income_tax.keys())
        ),
        "comparisons": comparisons,
        "comparison_summary": comparison_summary,
    }
    if w2_data is not None:
        payload["w2_input"] = w2_data
    return payload


def package_to_markdown(package: dict[str, Any]) -> str:
    extracted = package["extracted"]
    lines: list[str] = []

    lines.append("# Tax Filing Packet")
    lines.append("")
    lines.append(f"- Tax year: {package['tax_year']}")
    lines.append(
        f"- Paystubs analyzed: raw={package['paystub_count_raw']} canonical={package['paystub_count_canonical']}"
    )
    lines.append(f"- Latest paystub date: {package['latest_pay_date']}")
    lines.append(f"- Latest paystub file: `{package['latest_paystub_file']}`")
    lines.append(f"- Ready to file: `{package['ready_to_file']}`")
    lines.append("")

    lines.append("## Extracted Final YTD Values")
    lines.append(f"- Gross pay: {extracted['gross_pay']['ytd']}")
    lines.append(f"- Federal income tax: {extracted['federal_income_tax']['ytd']}")
    lines.append(f"- Social Security tax: {extracted['social_security_tax']['ytd']}")
    lines.append(f"- Medicare tax: {extracted['medicare_tax']['ytd']}")
    lines.append(f"- 401(k) contribution: {extracted['k401_contrib']['ytd']}")
    for state, row in sorted(extracted.get("state_income_tax", {}).items()):
        lines.append(f"- {state} state income tax: {row['ytd']}")
    lines.append("")

    lines.append("## Authenticity Assessment")
    assessment = package["authenticity_assessment"]
    lines.append(f"- Score: {assessment['score']}/100")
    lines.append(f"- Verdict: {assessment['verdict']}")
    lines.append(f"- Disclaimer: {assessment['disclaimer']}")
    lines.append("")

    if package.get("comparison_summary"):
        lines.append("## W-2 Comparison Summary")
        summary = package["comparison_summary"]
        lines.append(f"- match: {summary.get('match', 0)}")
        lines.append(f"- mismatch: {summary.get('mismatch', 0)}")
        lines.append(f"- review_needed: {summary.get('review_needed', 0)}")
        lines.append(f"- missing_paystub_value: {summary.get('missing_paystub_value', 0)}")
        lines.append(f"- missing_w2_value: {summary.get('missing_w2_value', 0)}")
        lines.append("")

        lines.append("## W-2 Comparison Details")
        for row in package.get("comparisons", []):
            lines.append(
                f"- {row['field']}: paystub={row['paystub']} w2={row['w2']} diff={row['difference']} status={row['status']}"
            )
        lines.append("")

    lines.append("## Consistency Issues")
    if not package["consistency_issues"]:
        lines.append("- none")
    else:
        for issue in package["consistency_issues"]:
            lines.append(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
    lines.append("")

    lines.append("## Filing Checklist")
    for item in package["filing_checklist"]:
        lines.append(f"- {item['item']}: {item['detail']}")

    return "\n".join(lines) + "\n"
