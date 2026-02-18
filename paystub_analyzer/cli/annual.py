"""
CLI Entry Point: paystub-annual

Build annual paystub ledger, W-2 authenticity check, and filing packet.
Ported from scripts/build_tax_filing_package.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from paystub_analyzer.annual import (
    collect_annual_snapshots,
    package_to_markdown,
)
from paystub_analyzer.core import format_money
from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
        return data


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
            to_write["state_tax_this_period_by_state"] = json.dumps(
                row["state_tax_this_period_by_state"], sort_keys=True
            )
            to_write["state_tax_ytd_by_state"] = json.dumps(row["state_tax_ytd_by_state"], sort_keys=True)
            writer.writerow(to_write)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build annual paystub ledger, W-2 authenticity check, and filing packet."
    )
    parser.add_argument("--paystubs-dir", default="pay_statements", help="Directory with paystub PDFs.")
    parser.add_argument("--year", type=int, help="Tax year to analyze (prompted if interactive).")
    parser.add_argument("--w2-json", type=Path, default=None, help="Optional W-2 JSON for cross-verification.")
    parser.add_argument("--w2-pdf", type=Path, default=None, help="Optional W-2 PDF for cross-verification.")
    parser.add_argument("--render-scale", type=float, default=2.8, help="OCR render scale.")
    parser.add_argument("--w2-render-scale", type=float, default=3.0, help="W-2 OCR render scale.")
    parser.add_argument("--tolerance", type=Decimal, default=Decimal("0.01"), help="Comparison tolerance.")
    parser.add_argument("--ledger-csv-out", type=Path, default=None, help="CSV output path.")
    parser.add_argument("--package-json-out", type=Path, default=None, help="JSON output path.")
    parser.add_argument("--package-md-out", type=Path, default=None, help="Markdown output path.")
    parser.add_argument("--force", action="store_true", help="Generate even if checks fail.")
    parser.add_argument("--household-config", type=Path, default=None, help="Household config JSON.")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive prompts.")

    args = parser.parse_args()

    # Interactive Prompts
    from paystub_analyzer.utils import console

    if args.interactive:
        if not console.is_interactive():
            console.print_warning("Interactive mode requested but not in TTY. Proceeding with defaults.")
        else:
            if not args.year:
                try:
                    val = console.ask_input("Tax Year", required=True)
                    args.year = int(val)
                except ValueError:
                    console.print_error("Year must be an integer.", exit_code=1)

            if not args.household_config:
                # Check if user wants to use config or legacy
                use_config = console.ask_confirm("Use Household Config file?", default=True)
                if use_config:
                    path_str = console.ask_input("Household Config Path", default="household_config.json")
                    args.household_config = Path(path_str)
                # Else fall through to legacy legacy logic

    # Validation
    if not args.year:
        console.print_error("argument --year is required", exit_code=2)

    # Determine Output Paths
    ledger_csv_out = args.ledger_csv_out or Path(f"reports/paystub_ledger_{args.year}.csv")
    package_json_out = args.package_json_out or Path(f"reports/tax_filing_package_{args.year}.json")
    package_md_out = args.package_md_out or Path(f"reports/tax_filing_package_{args.year}.md")

    from paystub_analyzer.utils.contracts import validate_output

    # Construct Household Configuration
    household_config: dict[str, Any]
    base_dir: Path

    console.print_step("Configuration")

    if args.household_config:
        if not args.household_config.exists():
            console.print_error(f"Household config file not found: {args.household_config}", exit_code=1)
        household_config = read_json(args.household_config)
        # Validate Input Contract
        try:
            validate_output(household_config, "household_config", mode="FILING")
        except Exception as e:
            console.print_error(f"Invalid household configuration: {e}", exit_code=1)

        base_dir = args.household_config.parent
        console.print_success(f"Loaded config: {args.household_config}")
    else:
        # Legacy Mode
        if not Path(args.paystubs_dir).exists():
            console.print_error(f"Paystubs directory not found: {args.paystubs_dir}", exit_code=1)
        if args.w2_json and args.w2_pdf:
            console.print_error("Use either --w2-json or --w2-pdf, not both.", exit_code=1)

        w2_files = [str(args.w2_pdf)] if args.w2_pdf else []
        household_config = {
            "version": "0.2.0",
            "household_id": "legacy_implicit",
            "filers": [
                {
                    "id": "primary",
                    "role": "PRIMARY",
                    "sources": {
                        "paystubs_dir": str(args.paystubs_dir),
                        "w2_files": w2_files,
                    },
                }
            ],
        }
        base_dir = Path.cwd()
        console.print_success("Using legacy implicit configuration.")

    # Define Loaders (omitted changes here as they are internal logic)
    def snapshot_loader(source_cfg: dict[str, Any]) -> list[Any]:
        d = base_dir / source_cfg["paystubs_dir"]
        if not d.exists():
            raise ValueError(f"Paystubs directory {d} does not exist.")
        return collect_annual_snapshots(
            paystubs_dir=d,
            year=args.year,
            render_scale=args.render_scale,
            psm=6,
        )

    def w2_loader(source_cfg: dict[str, Any]) -> dict[str, Any] | None:
        if not args.household_config and args.w2_json:
            return read_json(args.w2_json)
        files = source_cfg.get("w2_files", [])
        if not files:
            return None
        if len(files) > 1:
            raise NotImplementedError("Multiple W-2 files per filer not supported.")
        fpath = base_dir / files[0]
        return w2_pdf_to_json_payload(fpath, args.w2_render_scale, 6, args.year)

    from paystub_analyzer.annual import build_household_package

    console.print_step("Analysis")
    try:
        composite_result = build_household_package(
            household_config=household_config,
            tax_year=args.year,
            snapshot_loader=snapshot_loader,
            w2_loader=w2_loader,
            tolerance=args.tolerance,
        )
    except Exception as e:
        console.print_error(f"Error building package: {e}", exit_code=1)

    report = composite_result["report"]
    filers_analysis = composite_result["filers_analysis"]

    # Check Safety
    ready = report["household_summary"]["ready_to_file"]
    safety_failed_any = False

    for analysis in filers_analysis:
        internal = analysis["internal"]
        meta = internal["meta"]
        safety = meta.get("filing_safety", {})
        if not safety.get("passed", False):
            safety_failed_any = True
            fid = f"{analysis['public']['id']} ({analysis['public']['role']})"
            console.print_error(f"FILER: {fid} SAFETY FAILED")
            for err in safety.get("errors", []):
                print(f"- [BLOCKING] {err}")

    if safety_failed_any:
        print("")
        if not args.force:
            console.print_error("Aborting generation. Use --force to override.", exit_code=1)
        else:
            console.print_warning("Generating package despite failures due to --force flag.")

    # Write Outputs
    for analysis in filers_analysis:
        filer_id = analysis["public"]["id"]
        internal = analysis["internal"]
        suffix = "" if len(filers_analysis) == 1 else f"_{filer_id}"
        ledger_path = ledger_csv_out
        if suffix:
            ledger_path = ledger_csv_out.parent / f"{ledger_csv_out.stem}{suffix}{ledger_csv_out.suffix}"
        write_ledger_csv(ledger_path, internal["ledger"])

    # Write JSON/MD
    write_json(package_json_out, report)
    try:
        write_markdown(package_md_out, package_to_markdown(report))
    except Exception as e:
        console.print_warning(f"Could not generate markdown: {e}")

    # Final Summary Table
    console.print_step("Summary")

    summary_rows = [
        ["Household Ready", str(ready)],
        ["Gross Pay", format_money(Decimal(report["household_summary"]["total_gross_pay_cents"]) / 100)],
        ["Fed Tax", format_money(Decimal(report["household_summary"]["total_fed_tax_cents"]) / 100)],
    ]
    console.print_table("Household Totals", ["Metric", "Value"], summary_rows)

    # Outputs List
    console.print_table(
        "Generated Artifacts",
        ["Type", "Path"],
        [
            ["Package JSON", str(package_json_out)],
            ["Package Markdown", str(package_md_out)],
            ["Ledger CSV(s)", str(ledger_csv_out.parent)],
        ],
    )

    if safety_failed_any and not args.force:
        sys.exit(1)


if __name__ == "__main__":
    main()
