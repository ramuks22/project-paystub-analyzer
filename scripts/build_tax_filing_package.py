#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from paystub_analyzer.annual import (
    build_tax_filing_package,
    collect_annual_snapshots,
    package_to_markdown,
)
from paystub_analyzer.core import format_money
from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_ledger_csv(path: Path, ledger: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "pay_date",
            "file",
            "gross_pay_this_period",
            "gross_pay_ytd",
            "federal_tax_this_period",
            "federal_tax_ytd",
            "social_security_tax_this_period",
            "social_security_tax_ytd",
            "medicare_tax_this_period",
            "medicare_tax_ytd",
            "state_tax_this_period_total",
            "state_tax_ytd_total",
            "state_tax_this_period_by_state",
            "state_tax_ytd_by_state",
            "ytd_verification",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in ledger:
            to_write = dict(row)
            to_write["state_tax_this_period_by_state"] = json.dumps(row["state_tax_this_period_by_state"], sort_keys=True)
            to_write["state_tax_ytd_by_state"] = json.dumps(row["state_tax_ytd_by_state"], sort_keys=True)
            writer.writerow(to_write)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build annual paystub ledger, W-2 authenticity check, and filing packet."
    )
    parser.add_argument("--paystubs-dir", default="pay_statements", help="Directory with paystub PDFs.")
    parser.add_argument("--year", type=int, required=True, help="Tax year to analyze.")
    parser.add_argument("--w2-json", type=Path, default=None, help="Optional W-2 JSON for cross-verification.")
    parser.add_argument("--w2-pdf", type=Path, default=None, help="Optional W-2 PDF for OCR-based cross-verification.")
    parser.add_argument("--render-scale", type=float, default=2.8, help="OCR render scale.")
    parser.add_argument("--w2-render-scale", type=float, default=3.0, help="W-2 OCR render scale when using --w2-pdf.")
    parser.add_argument("--tolerance", type=Decimal, default=Decimal("0.01"), help="Comparison tolerance in dollars.")
    parser.add_argument(
        "--ledger-csv-out",
        type=Path,
        default=None,
        help="CSV output path for chronological ledger.",
    )
    parser.add_argument(
        "--package-json-out",
        type=Path,
        default=None,
        help="JSON output path for filing package.",
    )
    parser.add_argument(
        "--package-md-out",
        type=Path,
        default=None,
        help="Markdown output path for filing package.",
    )
    args = parser.parse_args()

    ledger_csv_out = args.ledger_csv_out or Path(f"reports/paystub_ledger_{args.year}.csv")
    package_json_out = args.package_json_out or Path(f"reports/tax_filing_package_{args.year}.json")
    package_md_out = args.package_md_out or Path(f"reports/tax_filing_package_{args.year}.md")

    snapshots = collect_annual_snapshots(
        paystubs_dir=Path(args.paystubs_dir),
        year=args.year,
        render_scale=args.render_scale,
        psm=6,
    )
    if not snapshots:
        raise SystemExit(f"No paystubs found in {args.paystubs_dir} for year {args.year}.")

    if args.w2_json and args.w2_pdf:
        raise SystemExit("Use either --w2-json or --w2-pdf, not both.")

    w2_data = None
    if args.w2_json:
        w2_data = read_json(args.w2_json)
    elif args.w2_pdf:
        w2_data = w2_pdf_to_json_payload(
            pdf_path=args.w2_pdf,
            render_scale=args.w2_render_scale,
            psm=6,
            fallback_year=args.year,
        )
    package = build_tax_filing_package(
        tax_year=args.year,
        snapshots=snapshots,
        tolerance=args.tolerance,
        w2_data=w2_data,
    )

    write_ledger_csv(ledger_csv_out, package["ledger"])
    write_json(package_json_out, package)
    write_markdown(package_md_out, package_to_markdown(package))

    extracted = package["extracted"]
    print(
        f"Analyzed paystubs: raw={package['paystub_count_raw']} canonical={package['paystub_count_canonical']}"
    )
    print(f"Latest paystub date: {package['latest_pay_date']}")
    print(f"Federal income tax YTD: {format_money(Decimal(str(extracted['federal_income_tax']['ytd'])) if extracted['federal_income_tax']['ytd'] is not None else None)}")
    state_sum = Decimal("0.00")
    for row in extracted.get("state_income_tax", {}).values():
        if row["ytd"] is not None:
            state_sum += Decimal(str(row["ytd"]))
    print(f"State income tax YTD total: {format_money(state_sum)}")
    print(f"Authenticity score: {package['authenticity_assessment']['score']}/100")
    print(f"Ready to file: {package['ready_to_file']}")
    print(f"Ledger CSV: {ledger_csv_out}")
    print(f"Package JSON: {package_json_out}")
    print(f"Package Markdown: {package_md_out}")


if __name__ == "__main__":
    main()
