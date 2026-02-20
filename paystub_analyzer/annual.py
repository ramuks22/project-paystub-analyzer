#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, cast

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

            # For repair heuristics, treat same-pay-date rows as peers in the same cycle
            # (for example, revision duplicates) and do not use them as temporal neighbors.
            prev_ytd = None
            next_ytd = None
            current_pay_date = snapshot.pay_date
            if position > 0:
                for candidate_pos in range(position - 1, -1, -1):
                    candidate_snapshot = repaired[indices[candidate_pos]]
                    if candidate_snapshot.pay_date == current_pay_date:
                        continue
                    prev_ytd = candidate_snapshot.state_income_tax[state].ytd
                    break
            if position + 1 < len(indices):
                for candidate_pos in range(position + 1, len(indices)):
                    candidate_snapshot = repaired[indices[candidate_pos]]
                    if candidate_snapshot.pay_date == current_pay_date:
                        continue
                    next_ytd = candidate_snapshot.state_income_tax[state].ytd
                    break

            # Same-cycle peers (same pay date) are useful as a fallback anchor for
            # OCR underflow repair when a revision row is missing the YTD column.
            same_cycle_peer_ytds = [
                repaired[peer_idx].state_income_tax[state].ytd
                for peer_idx in indices
                if peer_idx != idx
                and repaired[peer_idx].pay_date == current_pay_date
                and repaired[peer_idx].state_income_tax[state].ytd is not None
            ]

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
            else:
                baseline_prev_ytd = max(cast(list[Decimal], same_cycle_peer_ytds)) if same_cycle_peer_ytds else prev_ytd

                if (
                    baseline_prev_ytd is not None
                    and pair.this_period is None
                    and current_ytd < baseline_prev_ytd - STATE_YTD_OUTLIER_MIN_ABS
                ):
                    # OCR truncation underflow: The parser saw one number and assumed it was YTD
                    # but it was actually this_period.
                    projected_ytd = (baseline_prev_ytd + current_ytd).quantize(Decimal("0.01"))
                    is_valid_underflow = True
                    if next_ytd is not None:
                        # Next YTD should be at least as big as this projected YTD (monotonic)
                        if next_ytd < projected_ytd - STATE_YTD_NEIGHBOR_TOLERANCE:
                            is_valid_underflow = False

                    if is_valid_underflow:
                        corrected_this = current_ytd
                        corrected_ytd = projected_ytd
                        reason = "state_ytd_underflow_corrected"

            if corrected_ytd is None:
                continue

            snapshot.state_income_tax[state] = AmountPair(corrected_this, corrected_ytd, pair.source_line)
            target = snapshot.pay_date or snapshot.file
            message = (
                f"{state} state tax YTD on {target} was auto-corrected from "
                f"{format_money(current_ytd)} to {format_money(corrected_ytd)} ({reason})."
            )
            issue_code = reason if reason == "state_ytd_underflow_corrected" else "state_ytd_outlier_corrected"
            issues.append(
                ConsistencyIssue(
                    severity="warning",
                    code=issue_code,
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
                note = f"{label} YTD decreased {format_money(prev_pair.ytd)} -> {format_money(curr_pair.ytd)}"
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
                note = f"{label} parsed YTD {format_money(curr_pair.ytd)} vs calculated {format_money(expected_ytd)}"
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
            # Explicitly type as optional to satisfy mypy
            prev_pair_opt: AmountPair | None = prev_snapshot.state_income_tax.get(state)
            curr_pair_opt: AmountPair | None = snapshot.state_income_tax.get(state)

            if prev_pair_opt is None or curr_pair_opt is None:
                continue

            # Now we know they are not None
            prev_pair_val: AmountPair = prev_pair_opt
            curr_pair_val: AmountPair = curr_pair_opt

            if prev_pair_val.ytd is None or curr_pair_val.ytd is None:
                continue
            if curr_pair_val.ytd + tolerance < prev_pair_val.ytd:
                note = f"{state} state YTD decreased {format_money(prev_pair_val.ytd)} -> {format_money(curr_pair_val.ytd)}"
                record_note(notes_by_file, snapshot.file, note)
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="state_ytd_decrease",
                        message=f"{state} YTD decreased on {snapshot.pay_date}.",
                    )
                )
            if curr_pair_val.this_period is None:
                continue
            expected_ytd = (prev_pair_val.ytd + curr_pair_val.this_period).quantize(Decimal("0.01"))
            if abs(curr_pair_val.ytd - expected_ytd) > tolerance:
                note = (
                    f"{state} parsed YTD {format_money(curr_pair_val.ytd)} vs calculated {format_money(expected_ytd)}"
                )
                record_note(notes_by_file, snapshot.file, note)
                issues.append(
                    ConsistencyIssue(
                        severity="warning",
                        code="state_ytd_calc_mismatch",
                        message=(
                            f"{state} state YTD on {snapshot.pay_date} differs from calculated "
                            f"({format_money(curr_pair_val.ytd)} vs {format_money(expected_ytd)})."
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
    getter: Callable[[PaystubSnapshot], Decimal | None],
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


def apply_manual_pay_date_overrides(
    snapshots: list[PaystubSnapshot],
    pay_date_overrides: dict[str, str] | None = None,
) -> tuple[list[PaystubSnapshot], list[ConsistencyIssue]]:
    if not snapshots:
        return [], []
    if not pay_date_overrides:
        return list(snapshots), []

    adjusted = list(snapshots)
    issues: list[ConsistencyIssue] = []
    for idx, snapshot in enumerate(adjusted):
        file_path = Path(snapshot.file)
        override_value = (
            pay_date_overrides.get(snapshot.file)
            or pay_date_overrides.get(str(file_path))
            or pay_date_overrides.get(file_path.name)
        )
        if not override_value:
            continue
        try:
            normalized = date.fromisoformat(str(override_value)).isoformat()
        except ValueError:
            continue
        if normalized == snapshot.pay_date:
            continue

        adjusted[idx] = replace(snapshot, pay_date=normalized)
        issues.append(
            ConsistencyIssue(
                severity="warning",
                code="pay_date_override_applied",
                message=(
                    f"Applied manual pay date override for `{snapshot.file}`: {snapshot.pay_date} -> {normalized}"
                ),
            )
        )

    adjusted.sort(key=snapshot_sort_key)
    return adjusted, issues


def deduplicate_by_pay_date(
    snapshots: list[PaystubSnapshot],
    pay_date_overrides: dict[str, str] | None = None,
) -> tuple[list[PaystubSnapshot], list[ConsistencyIssue]]:
    normalized_snapshots, override_issues = apply_manual_pay_date_overrides(
        snapshots,
        pay_date_overrides=pay_date_overrides,
    )

    grouped: dict[str, list[PaystubSnapshot]] = {}
    no_date: list[PaystubSnapshot] = []
    for snapshot in normalized_snapshots:
        if snapshot.pay_date is None:
            no_date.append(snapshot)
            continue
        grouped.setdefault(snapshot.pay_date, []).append(snapshot)

    canonical: list[PaystubSnapshot] = []
    issues: list[ConsistencyIssue] = list(override_issues)
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


def annotate_raw_ledger_rows(
    raw_rows: list[dict[str, Any]],
    canonical_snapshots: list[PaystubSnapshot],
) -> list[dict[str, Any]]:
    canonical_files = {snapshot.file for snapshot in canonical_snapshots}
    canonical_file_by_date = {
        snapshot.pay_date: snapshot.file for snapshot in canonical_snapshots if snapshot.pay_date is not None
    }
    annotated: list[dict[str, Any]] = []
    for row in raw_rows:
        file_path = str(row.get("file", ""))
        pay_date = cast(str | None, row.get("pay_date"))
        included = file_path in canonical_files

        canonical_file = None
        if pay_date is not None:
            canonical_file = canonical_file_by_date.get(pay_date)
        if canonical_file is None and included:
            canonical_file = file_path

        status = "Included" if included else "Ignored (duplicate for pay date)"
        row_copy = dict(row)
        row_copy["calculation_status"] = status
        row_copy["canonical_file"] = canonical_file
        annotated.append(row_copy)

    return annotated


def run_consistency_checks(
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
    pay_date_overrides: dict[str, str] | None = None,
) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    canonical, duplicate_issues = deduplicate_by_pay_date(snapshots, pay_date_overrides=pay_date_overrides)
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


def analyze_filer(
    tax_year: int,
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
    w2_data: dict[str, Any] | None,
    filer_id: str,
    role: str,
    corrections: dict[str, Any] | None = None,
    pay_date_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Analyze a single filer's paystubs and W-2s.
    Returns a dictionary with 'public' (filer report object) and 'internal' (ledger/meta).
    """
    if not snapshots:
        # If no snapshots, we can't really analyze much, but might have W-2?
        # For now, matching existing logic: raise ValueError if no paystubs.
        # But for spouses, they might have 0 income?
        # RFC says "Every paystub... strictly owned".
        # If a filer is defined but has no docs, they might be empty.
        # But existing logic raises ValueError. Let's keep strict for now.
        raise ValueError(f"No snapshots available for filer {filer_id}.")

    # Apply overrides first so chronology-sensitive repair logic (for example
    # state YTD underflow recovery) uses the user-assigned pay-cycle timeline.
    normalized_snapshots, override_issues = apply_manual_pay_date_overrides(
        snapshots,
        pay_date_overrides=pay_date_overrides,
    )
    verified_snapshots, ytd_repair_issues, verification_notes_by_file = verify_and_repair_state_ytd_anomalies(
        normalized_snapshots,
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
    raw_ledger = annotate_raw_ledger_rows(
        build_ledger_rows(
            verified_snapshots,
            verification_notes_by_file=verification_notes_by_file,
        ),
        canonical_snapshots=canonical_snapshots,
    )
    issues = (
        ytd_repair_issues
        + ytd_calc_issues
        + override_issues
        + duplicate_issues
        + run_consistency_checks(canonical_snapshots, tolerance=tolerance)
    )

    comparisons: list[dict[str, Any]] = []
    comparison_summary: dict[str, int] = {}
    if w2_data is not None:
        comparisons, comparison_summary = compare_snapshot_to_w2(final_snapshot, w2_data, tolerance)

    assessment = authenticity_assessment(issues, comparisons)

    # New Filing Mode Safety Check
    from paystub_analyzer.filing_rules import validate_filing_safety
    from paystub_analyzer.utils.corrections import merge_corrections

    # Convert to v0.2.0 Schema (Integer Cents)
    raw_extracted = extracted_summary(final_snapshot)

    # APPLY CORRECTIONS (v0.3.0 Phase 2)
    # corrections arg passed to analyze_filer (default None)
    effective_extracted, correction_audit = merge_corrections(raw_extracted, corrections or {})

    # Validate based on EFFECTIVE (Corrected) values
    filing_safety = validate_filing_safety(
        extracted_data=effective_extracted,
        comparisons=comparisons,
        consistency_issues=[issue.__dict__ for issue in issues],
        tolerance=tolerance,
    )

    ready_to_file = filing_safety.passed and bool(w2_data)

    # Helper to convert decimal/float to cents
    def to_cents(x: dict[str, Any] | None) -> int:
        # x is now the inner dict like {"ytd": 123.45} from effective_extracted
        if x and x.get("ytd") is not None:
            return int(round(x["ytd"] * 100))
        return 0

    state_tax_cents = {k: to_cents(v) for k, v in effective_extracted["state_income_tax"].items()}

    filer_report = {
        "id": filer_id,
        "role": role,
        "gross_pay_cents": to_cents(effective_extracted["gross_pay"]),
        "fed_tax_cents": to_cents(effective_extracted["federal_income_tax"]),
        "state_tax_by_state_cents": state_tax_cents,
        "status": "MATCH" if ready_to_file else "REVIEW_NEEDED",
        "audit_flags": sorted(
            [err for err in filing_safety.errors]
            + [warn for warn in filing_safety.warnings]
            + (w2_data.get("processing_warnings", []) if w2_data else [])
        ),
        "correction_trace": correction_audit,
    }

    # v0.3.0 Multi-W2 Metadata
    if w2_data:
        filer_report["w2_source_count"] = w2_data.get("w2_source_count", 1)
        # Assuming single-file inputs might not have these keys if bypassed via legacy loader?
        # But we updated the CLI loader. If direct callers use legacy w2_loader dicts, we should fallback.
        # v0.3.0: Copy aggregated W-2 data.
        # w2_data has keys: 'w2_aggregate' (cents), 'w2_sources', 'state_boxes'
        # We want to preserve 'state_boxes' inside 'w2_aggregate' for the report, or alongside it.
        # contracts Output Filer schema says: w2_aggregate: W2Aggregate
        # W2Aggregate has: box1..., state_boxes: list[StateBox]
        # So we must merge them.
        w2_agg = w2_data.get("w2_aggregate", {}).copy()
        if "state_boxes" in w2_data:
            translated_boxes = []
            for sbox in w2_data["state_boxes"]:
                wages = sbox.get("box_16_state_wages_tips")
                taxes = sbox.get("box_17_state_income_tax")
                w_cents = int(round(float(wages) * 100)) if wages is not None else 0
                t_cents = int(round(float(taxes) * 100)) if taxes is not None else 0

                translated_boxes.append(
                    {"state": sbox.get("state", "??"), "wages_cents": w_cents, "tax_cents": t_cents}
                )
            w2_agg["state_boxes"] = translated_boxes

        filer_report["w2_aggregate"] = w2_agg
        filer_report["w2_sources"] = w2_data.get("w2_sources")

        # Backfill if missing (e.g. single W-2 loaded directly without aggregator)
        # Check if we have the cents keys, otherwise derive from top-level floats
        # cast to dict to satisfy mypy
        w2_agg_cast = cast(dict[str, Any], filer_report["w2_aggregate"])
        if "box1_wages_cents" not in w2_agg_cast:
            w2_agg_cast.update(
                {
                    "box1_wages_cents": int((w2_data.get("box_1_wages_tips_other_comp") or 0.0) * 100),
                    "box2_fed_tax_cents": int((w2_data.get("box_2_federal_income_tax_withheld") or 0.0) * 100),
                    "box4_social_security_tax_cents": int(
                        (w2_data.get("box_4_social_security_tax_withheld") or 0.0) * 100
                    ),
                    "box6_medicare_tax_cents": int((w2_data.get("box_6_medicare_tax_withheld") or 0.0) * 100),
                }
            )
        if not filer_report["w2_sources"]:
            filer_report["w2_sources"] = [
                {
                    "filename": "legacy_implicit_source",
                    "control_number": str(w2_data.get("control_number", "UNKNOWN")),
                    "employer_ein": str(w2_data.get("employer_ein", "UNKNOWN")),
                    "box1_wages_contribution_cents": cast(dict[str, Any], filer_report["w2_aggregate"])[
                        "box1_wages_cents"
                    ],
                }
            ]

    if "w2_aggregate" not in filer_report:
        filer_report["w2_aggregate"] = {
            "box1_wages_cents": 0,
            "box2_fed_tax_cents": 0,
            "box4_social_security_tax_cents": 0,
            "box6_medicare_tax_cents": 0,
        }
    if "w2_sources" not in filer_report:
        filer_report["w2_sources"] = []
    if "w2_source_count" not in filer_report:
        filer_report["w2_source_count"] = 0

    return {
        "public": filer_report,
        "internal": {
            "report": filer_report,  # Legacy prop for single-return compat
            "ledger": ledger,
            "raw_ledger": raw_ledger,
            "meta": {
                "tax_year": tax_year,
                "paystub_count_raw": len(snapshots),
                "paystub_count_canonical": len(canonical_snapshots),
                "latest_pay_date": final_snapshot.pay_date,
                "latest_paystub_file": final_snapshot.file,
                "extracted": effective_extracted,
                "authenticity_score": assessment["score"],
                "filing_safety": filing_safety._asdict(),
                "consistency_issues": [issue.__dict__ for issue in issues],
                "comparisons": comparisons,
                "comparison_summary": comparison_summary,
            },
        },
    }


def build_household_package(
    household_config: dict[str, Any],
    tax_year: int,
    snapshot_loader: Callable[[dict[str, Any]], list[PaystubSnapshot]],
    w2_loader: Callable[[dict[str, Any]], dict[str, Any] | None],
    tolerance: Decimal,
    corrections: dict[str, Any] | None = None,
    pay_date_overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Orchestrate household analysis.
    snapshot_loader: fn(source_config) -> list[snapshots]
    w2_loader: fn(source_config) -> w2_data OR None
    """
    filers = household_config["filers"]
    corrections = corrections or {}
    pay_date_overrides = pay_date_overrides or {}

    # 1. Validation: Cardinality
    roles = [f["role"] for f in filers]
    if roles.count("PRIMARY") != 1:
        raise ValueError("Household must have exactly one PRIMARY filer.")
    if roles.count("SPOUSE") > 1:
        raise ValueError("Household can have at most one SPOUSE filer.")

    ids = [f["id"] for f in filers]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate filer IDs found: {ids}")

    # 2. Duplicate Source Detection (Global)
    # This requires looking at the loaded snapshots or paths BEFORE processing?
    # Or we trust the loader to give us paths.
    # The loader is called per filer. We can track paths seen.
    seen_paths: dict[str, str] = {}  # path -> filer_id

    results = []

    total_gross = 0
    total_fed = 0
    all_ready = True

    for filer in filers:
        filer_id = filer["id"]
        role = filer["role"]
        sources = filer["sources"]

        # Load data
        snapshots = snapshot_loader(sources)
        w2_data = w2_loader(sources)

        # 3. Check for shared files
        for s in snapshots:
            if s.file in seen_paths:
                other = seen_paths[s.file]
                raise ValueError(f"File '{s.file}' is claimed by both '{other}' and '{filer_id}'.")
            seen_paths[s.file] = filer_id

        # Analyze
        analysis = analyze_filer(
            tax_year=tax_year,
            snapshots=snapshots,
            tolerance=tolerance,
            w2_data=w2_data,
            filer_id=filer_id,
            role=role,
            corrections=corrections.get(filer_id),
            pay_date_overrides=pay_date_overrides.get(filer_id),
        )

        filer_public = analysis["public"]
        results.append(analysis)

        # Aggregation
        total_gross += filer_public["gross_pay_cents"]
        total_fed += filer_public["fed_tax_cents"]

        status = filer_public["status"]
        if status != "MATCH":
            all_ready = False

    household_summary = {
        "total_gross_pay_cents": total_gross,
        "total_fed_tax_cents": total_fed,
        "ready_to_file": all_ready,
    }

    public_report = {
        "schema_version": "0.3.0",
        "household_summary": household_summary,
        "filers": [r["public"] for r in results],
    }

    # Validate Contract
    from paystub_analyzer.utils.contracts import validate_output

    validate_output(public_report, "v0_3_0_contract", mode="FILING")

    # Composite return (list of internal results + aggregate report)
    return {
        "report": public_report,
        "filers_analysis": results,
    }


# Legacy wrapper for backward compatibility
def build_tax_filing_package(
    tax_year: int,
    snapshots: list[PaystubSnapshot],
    tolerance: Decimal,
    w2_data: dict[str, Any] | None,
    pay_date_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Detailed single-filer analysis (Legacy Entry Point).
    Wraps analyze_filer but formats return to match old contract expected by CLI currently.
    """
    analysis = analyze_filer(
        tax_year=tax_year,
        snapshots=snapshots,
        tolerance=tolerance,
        w2_data=w2_data,
        filer_id="primary",
        role="PRIMARY",
        pay_date_overrides=pay_date_overrides,
    )

    # Re-construct the legacy composite package structure
    # The new analyze_filer returns {'public': ..., 'internal': ...}
    # The old build_tax_filing_package returned the internal dict directly + report embedded?
    # Actually, look at the old code: it returned:
    # { "report": public_report, "ledger": ledger, "meta": meta }
    # My new analyze_filer 'internal' key contains exactly this structure!

    internal = analysis["internal"]

    # But wait, 'public_report' inside analyze_filer is just the filer report (dict),
    # whereas 'report' in the old return was the full {household_summary, filers: []} structure
    # constructed at the end.

    # We need to wrap the single filer report into a household report to match v0.2.0 output requirement
    filer_report = analysis["public"]

    public_report = {
        "schema_version": "0.3.0",
        "household_summary": {
            "total_gross_pay_cents": filer_report["gross_pay_cents"],
            "total_fed_tax_cents": filer_report["fed_tax_cents"],
            "ready_to_file": filer_report["status"] == "MATCH",
        },
        "filers": [filer_report],
    }

    # Validate Contract
    from paystub_analyzer.utils.contracts import validate_output

    validate_output(public_report, "v0_3_0_contract", mode="FILING")

    return {
        "report": public_report,
        "ledger": internal["ledger"],
        "raw_ledger": internal.get("raw_ledger", internal["ledger"]),
        "meta": internal["meta"],
    }


STATE_TAX_MATCH_TOLERANCE_CENTS = 100


def package_to_markdown(package: dict[str, Any]) -> str:
    household = package["household_summary"]

    lines: list[str] = []

    lines.append("# Tax Filing Packet (v0.3.0)")
    lines.append("")
    lines.append(f"- Schema Version: {package['schema_version']}")
    lines.append(f"- Ready to file: `{household['ready_to_file']}`")
    lines.append("")

    lines.append("## Household Summary")
    lines.append(f"- Total Gross Pay: ${household['total_gross_pay_cents'] / 100:,.2f}")
    lines.append(f"- Total Fed Tax: ${household['total_fed_tax_cents'] / 100:,.2f}")
    lines.append("")

    for filer in package["filers"]:
        # Capitalize role or name
        header_title = filer.get("id", "Filer").title()
        if filer.get("role"):
            header_title += f" ({filer['role']})"

        lines.append(f"## {header_title}")
        lines.append(f"- Gross Pay: ${filer['gross_pay_cents'] / 100:,.2f}")
        lines.append(f"- Fed Tax: ${filer['fed_tax_cents'] / 100:,.2f}")
        lines.append(f"- Status: {filer['status']}")

        # W-2 Summary if present
        if filer.get("w2_source_count", 0) > 0:
            lines.append(f"- W-2 Sources: {filer['w2_source_count']}")
            agg = filer.get("w2_aggregate", {})
            if agg:
                w2_wages = agg.get("box1_wages_cents", 0) / 100
                lines.append(f"- W-2 Wages (Box 1): ${w2_wages:,.2f}")

        if filer.get("audit_flags"):
            lines.append("### Audit Flags")
            for flag in filer["audit_flags"]:
                lines.append(f"- {flag}")

        correction_trace = filer.get("correction_trace", [])
        if correction_trace:
            lines.append("### Corrections & Overrides")
            lines.append("| Field | Original | Corrected | Reason |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for c in correction_trace:
                field = c.get("corrected_field", "")
                orig = c.get("original_value")
                new_val = c.get("corrected_value")
                reason = c.get("reason", "")

                orig_str = f"${float(orig):,.2f}" if orig is not None else "—"
                new_str = f"${float(new_val):,.2f}" if new_val is not None else "—"

                lines.append(f"| `{field}` | {orig_str} | {new_str} | {reason} |")

        # State Tax Verification (v0.3.0 Phase 2)
        # Compare Paystub YTD vs W-2 Box 17
        paystub_states = filer.get("state_tax_by_state_cents", {})

        # W-2 data structure is complex. w2_aggregate -> state_boxes (list of dicts)
        w2_aggregate = filer.get("w2_aggregate", {})
        w2_state_map = {}
        if w2_aggregate and "state_boxes" in w2_aggregate:
            for sbox in w2_aggregate["state_boxes"]:
                st_code = sbox.get("state", "??")
                # W-2 aggregator returns floats. Convert to cents for comparison.
                tax_float = sbox.get("box_17_state_income_tax", 0.0)
                w2_state_map[st_code] = int(round(tax_float * 100))

        all_states = sorted(set(paystub_states.keys()) | set(w2_state_map.keys()))

        if all_states:
            lines.append("")
            lines.append("### State Tax Verification")
            lines.append("| State | Paystub YTD | W-2 Box 17 | Difference | Status |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")

            for st in all_states:
                ps_cents = paystub_states.get(st, 0)
                w2_cents = w2_state_map.get(st, 0)
                diff = ps_cents - w2_cents

                if st not in paystub_states:
                    status = "MISSING (PAYSTUB)"
                elif st not in w2_state_map:
                    status = "MISSING (W-2)"
                else:
                    status = "MATCH" if abs(diff) <= STATE_TAX_MATCH_TOLERANCE_CENTS else "MISMATCH"
                # Contracts say cents-based. Let's start with strict 0 or small epsilon.
                # Actually, rounding issues might exist. $1.00 is reasonable for visual flag?
                # User asked for "State Tax Verification".

                # Format money
                ps_str = f"${ps_cents / 100:,.2f}" if st in paystub_states else "—"
                w2_str = f"${w2_cents / 100:,.2f}" if st in w2_state_map else "—"
                diff_str = f"${diff / 100:,.2f}"

                lines.append(f"| {st} | {ps_str} | {w2_str} | {diff_str} | {status} |")

        lines.append("")

    return "\n".join(lines)
