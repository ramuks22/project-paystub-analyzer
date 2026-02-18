#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from paystub_analyzer.core import (
    as_float,
    extract_paystub_snapshot,
    format_money,
    list_paystub_files,
    select_latest_paystub,
    sum_state_ytd,
)
from paystub_analyzer.w2 import build_w2_template, compare_snapshot_to_w2
from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def pair_to_dict(pair) -> dict[str, Any]:
    return {
        "this_period": as_float(pair.this_period),
        "ytd": as_float(pair.ytd),
        "evidence": pair.source_line,
    }


def report_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    extracted = payload["extracted"]

    lines.append("# Payslip vs W-2 Validation")
    lines.append("")
    lines.append(f"- Tax year: {payload['tax_year']}")
    lines.append(f"- Latest payslip used: `{payload['latest_paystub_file']}`")
    lines.append(f"- Latest payslip pay date: {payload['latest_pay_date']}")
    lines.append("")

    lines.append("## Extracted Values")
    lines.append(f"- Gross pay (YTD): {format_money(Decimal(str(extracted['gross_pay']['ytd'])) if extracted['gross_pay']['ytd'] is not None else None)}")
    lines.append(f"- Federal income tax (YTD): {format_money(Decimal(str(extracted['federal_income_tax']['ytd'])) if extracted['federal_income_tax']['ytd'] is not None else None)}")
    lines.append(f"- Social Security tax (YTD): {format_money(Decimal(str(extracted['social_security_tax']['ytd'])) if extracted['social_security_tax']['ytd'] is not None else None)}")
    lines.append(f"- Medicare tax (YTD): {format_money(Decimal(str(extracted['medicare_tax']['ytd'])) if extracted['medicare_tax']['ytd'] is not None else None)}")
    lines.append(f"- 401(k) contribution (YTD): {format_money(Decimal(str(extracted['k401_contrib']['ytd'])) if extracted['k401_contrib']['ytd'] is not None else None)}")

    state_rows = extracted.get("state_income_tax", {})
    if state_rows:
        for state in sorted(state_rows):
            lines.append(
                f"- {state} state income tax (YTD): {format_money(Decimal(str(state_rows[state]['ytd'])) if state_rows[state]['ytd'] is not None else None)}"
            )
    else:
        lines.append("- State income tax (YTD): n/a")
    lines.append("")

    lines.append("## Evidence Lines")
    for key in ["gross_pay", "federal_income_tax", "social_security_tax", "medicare_tax", "k401_contrib"]:
        evidence = extracted[key].get("evidence")
        if evidence:
            lines.append(f"- {key}: `{evidence}`")
    for state, row in sorted(state_rows.items()):
        if row.get("evidence"):
            lines.append(f"- state_{state}: `{row['evidence']}`")
    lines.append("")

    comparisons = payload.get("comparisons", [])
    if comparisons:
        summary = payload["comparison_summary"]
        lines.append("## W-2 Comparison Summary")
        lines.append(f"- match: {summary.get('match', 0)}")
        lines.append(f"- mismatch: {summary.get('mismatch', 0)}")
        lines.append(f"- review_needed: {summary.get('review_needed', 0)}")
        lines.append(f"- missing_paystub_value: {summary.get('missing_paystub_value', 0)}")
        lines.append(f"- missing_w2_value: {summary.get('missing_w2_value', 0)}")
        lines.append("")

        lines.append("## W-2 Comparison Details")
        for row in comparisons:
            lines.append(
                f"- {row['field']}: paystub={row['paystub']} w2={row['w2']} diff={row['difference']} status={row['status']}"
            )
    else:
        lines.append("## W-2 Comparison")
        lines.append("- No W-2 JSON provided. Add `--w2-json` to run matching.")

    return "\n".join(lines) + "\n"


def snapshot_to_payload(snapshot) -> dict[str, Any]:
    return {
        "gross_pay": pair_to_dict(snapshot.gross_pay),
        "federal_income_tax": pair_to_dict(snapshot.federal_income_tax),
        "social_security_tax": pair_to_dict(snapshot.social_security_tax),
        "medicare_tax": pair_to_dict(snapshot.medicare_tax),
        "k401_contrib": pair_to_dict(snapshot.k401_contrib),
        "state_income_tax": {
            state: pair_to_dict(pair)
            for state, pair in sorted(snapshot.state_income_tax.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate latest paystub values against W-2 inputs.")
    parser.add_argument("--paystubs-dir", default="pay_statements", help="Directory containing paystub PDFs.")
    parser.add_argument("--year", type=int, default=None, help="Tax year filter based on paystub filename.")
    parser.add_argument("--w2-json", type=Path, default=None, help="Path to W-2 JSON data for matching.")
    parser.add_argument("--w2-pdf", type=Path, default=None, help="Path to W-2 PDF (OCR-extracted for matching).")
    parser.add_argument("--write-w2-template", type=Path, default=None, help="Write a W-2 template and exit.")
    parser.add_argument("--render-scale", type=float, default=2.5, help="OCR render scale (default: 2.5).")
    parser.add_argument("--w2-render-scale", type=float, default=3.0, help="W-2 OCR render scale when using --w2-pdf (default: 3.0).")
    parser.add_argument("--tolerance", type=Decimal, default=Decimal("0.01"), help="Match tolerance in dollars.")
    parser.add_argument("--json-out", type=Path, default=Path("reports/w2_validation.json"), help="Machine-readable output path.")
    parser.add_argument("--report-out", type=Path, default=Path("reports/w2_validation.md"), help="Markdown report output path.")
    args = parser.parse_args()

    if args.write_w2_template:
        states: list[str] | None = None
        if args.year is not None:
            template_files = list_paystub_files(Path(args.paystubs_dir), year=args.year)
            if template_files:
                latest_template_file, _ = select_latest_paystub(template_files)
                template_snapshot = extract_paystub_snapshot(
                    latest_template_file, render_scale=args.render_scale
                )
                states = sorted(template_snapshot.state_income_tax.keys()) or None

        template = build_w2_template(states=states)
        if args.year is not None:
            template["tax_year"] = args.year
        write_json(args.write_w2_template, template)
        print(f"W-2 template written: {args.write_w2_template}")
        return

    paystub_files = list_paystub_files(Path(args.paystubs_dir), year=args.year)
    if not paystub_files:
        raise SystemExit(f"No paystubs found in {args.paystubs_dir} for year={args.year}.")

    latest_file, latest_date = select_latest_paystub(paystub_files)
    snapshot = extract_paystub_snapshot(latest_file, render_scale=args.render_scale)

    extracted = snapshot_to_payload(snapshot)
    payload: dict[str, Any] = {
        "tax_year": args.year if args.year is not None else latest_date.year,
        "latest_paystub_file": str(latest_file),
        "latest_pay_date": latest_date.isoformat(),
        "extracted": extracted,
        "comparisons": [],
        "comparison_summary": {},
    }

    if args.w2_json and args.w2_pdf:
        raise SystemExit("Use either --w2-json or --w2-pdf, not both.")

    if args.w2_json:
        w2_data = read_json(args.w2_json)
        comparisons, summary = compare_snapshot_to_w2(snapshot, w2_data, args.tolerance)
        payload["w2_input"] = w2_data
        payload["comparisons"] = comparisons
        payload["comparison_summary"] = summary
    elif args.w2_pdf:
        w2_data = w2_pdf_to_json_payload(
            pdf_path=args.w2_pdf,
            render_scale=args.w2_render_scale,
            psm=6,
            fallback_year=args.year,
        )
        comparisons, summary = compare_snapshot_to_w2(snapshot, w2_data, args.tolerance)
        payload["w2_input"] = w2_data
        payload["comparisons"] = comparisons
        payload["comparison_summary"] = summary

    write_json(args.json_out, payload)
    write_text(args.report_out, report_markdown(payload))

    print(f"Latest paystub used: {latest_file} ({latest_date.isoformat()})")
    print(f"Federal income tax YTD: {format_money(snapshot.federal_income_tax.ytd)}")
    print(f"State income tax YTD total: {format_money(sum_state_ytd(snapshot.state_income_tax))}")
    for state in sorted(snapshot.state_income_tax):
        print(f"  {state}: {format_money(snapshot.state_income_tax[state].ytd)}")
    print(f"Report written: {args.report_out}")
    print(f"JSON written: {args.json_out}")


if __name__ == "__main__":
    main()
