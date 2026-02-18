"""
CLI Entry Point: paystub-analyze

Analyzes federal and state taxes from paystub PDFs.
Ported from scripts/analyze_payslip_taxes.py.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from typing import Any

from paystub_analyzer.core import (
    as_float,
    extract_paystub_snapshot,
    format_money,
    list_paystub_files,
    sum_state_this_period,
    sum_state_ytd,
    PaystubSnapshot,
)


def money_or_none(value: Decimal | None) -> str:
    return format_money(value) if value is not None else "n/a"


def snapshot_to_json(snapshot: PaystubSnapshot) -> dict[str, Any]:
    states = {
        state: {
            "this_period": as_float(pair.this_period),
            "ytd": as_float(pair.ytd),
            "evidence": pair.source_line,
        }
        for state, pair in sorted(snapshot.state_income_tax.items())
    }
    federal_this = snapshot.federal_income_tax.this_period
    federal_ytd = snapshot.federal_income_tax.ytd
    state_this_total = sum_state_this_period(snapshot.state_income_tax)
    state_ytd_total = sum_state_ytd(snapshot.state_income_tax)

    return {
        "file": snapshot.file,
        "pay_date": snapshot.pay_date,
        "federal": {
            "this_period": as_float(federal_this),
            "ytd": as_float(federal_ytd),
            "evidence": snapshot.federal_income_tax.source_line,
        },
        "state_total": {
            "this_period": as_float(state_this_total),
            "ytd": as_float(state_ytd_total),
        },
        "federal_plus_state_total": {
            "this_period": as_float((federal_this or Decimal("0.00")) + state_this_total),
            "ytd": as_float((federal_ytd or Decimal("0.00")) + state_ytd_total),
        },
        "states": states,
        "schema_version": "1.0.0",
    }


def output_human(results: list[dict[str, Any]]) -> None:
    agg_this = Decimal("0.00")
    agg_ytd = Decimal("0.00")

    for row in results:
        federal_this = (
            Decimal(str(row["federal"]["this_period"])) if row["federal"]["this_period"] is not None else None
        )
        federal_ytd = Decimal(str(row["federal"]["ytd"])) if row["federal"]["ytd"] is not None else None
        state_this = (
            Decimal(str(row["state_total"]["this_period"]))
            if row["state_total"]["this_period"] is not None
            else Decimal("0.00")
        )
        state_ytd = (
            Decimal(str(row["state_total"]["ytd"])) if row["state_total"]["ytd"] is not None else Decimal("0.00")
        )

        if federal_this is not None:
            agg_this += federal_this + state_this
        if federal_ytd is not None:
            agg_ytd += federal_ytd + state_ytd

        print(f"File: {row['file']}")
        if row["pay_date"]:
            print(f"Pay Date: {row['pay_date']}")
        print(f"Federal Tax (This Period): {money_or_none(federal_this)}")
        print(f"State Tax Total (This Period): {format_money(state_this)}")
        if federal_this is not None:
            print(f"Total Federal + State (This Period): {format_money(federal_this + state_this)}")
        else:
            print("Total Federal + State (This Period): n/a")
        print(f"Federal Tax (YTD): {money_or_none(federal_ytd)}")
        print(f"State Tax Total (YTD): {format_money(state_ytd)}")
        if federal_ytd is not None:
            print(f"Total Federal + State (YTD): {format_money(federal_ytd + state_ytd)}")
        else:
            print("Total Federal + State (YTD): n/a")

        if row["states"]:
            print("State Breakdown (This Period / YTD):")
            for state, state_row in sorted(row["states"].items()):
                state_this_val = (
                    Decimal(str(state_row["this_period"])) if state_row["this_period"] is not None else None
                )
                state_ytd_val = Decimal(str(state_row["ytd"])) if state_row["ytd"] is not None else None
                print(f"  {state}: {money_or_none(state_this_val)} / {money_or_none(state_ytd_val)}")
        else:
            print("State Breakdown: none found")
        print()

    if len(results) > 1:
        print("Aggregate Across Files:")
        print(f"Total Federal + State (This Period): {format_money(agg_this)}")
        print(f"Total Federal + State (YTD): {format_money(agg_ytd)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze federal and state taxes from paystub PDFs.")
    parser.add_argument("pdfs", nargs="*", help="PDF files to analyze.")
    parser.add_argument("--default-folder", default="pay_statements", help="Default folder when no files are provided.")
    parser.add_argument("--render-scale", type=float, default=2.5, help="OCR render scale (default: 2.5).")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    args = parser.parse_args()

    files = [Path(path).expanduser() for path in args.pdfs]
    if not files:
        files = list_paystub_files(Path(args.default_folder), year=None)
    if not files:
        raise SystemExit("No paystub PDFs found.")

    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise SystemExit(f"File(s) not found: {', '.join(missing)}")

    results = []
    for file_path in files:
        snapshot = extract_paystub_snapshot(file_path, render_scale=args.render_scale)
        results.append(snapshot_to_json(snapshot))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        output_human(results)


if __name__ == "__main__":
    main()
