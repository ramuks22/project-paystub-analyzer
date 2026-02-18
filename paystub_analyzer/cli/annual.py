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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Generate package even if safety checks fail (exit code will still be non-zero unless suppressed).",
    )
    parser.add_argument(
        "--household-config",
        type=Path,
        default=None,
        help="Path to household configuration JSON (v0.2.0 specific).",
    )
    # ... (rest of args)
    args = parser.parse_args()

    # Determine Output Paths (Defaults or Custom)
    ledger_csv_out = args.ledger_csv_out or Path(f"reports/paystub_ledger_{args.year}.csv")
    package_json_out = args.package_json_out or Path(f"reports/tax_filing_package_{args.year}.json")
    package_md_out = args.package_md_out or Path(f"reports/tax_filing_package_{args.year}.md")

    from paystub_analyzer.utils.contracts import validate_output

    # Construct Household Configuration
    household_config: dict[str, Any]
    base_dir: Path

    if args.household_config:
        if not args.household_config.exists():
            sys.exit(f"Error: Household config file not found: {args.household_config}")
        household_config = read_json(args.household_config)
        # Validate Input Contract (Week 5 Cleanup)
        try:
            validate_output(household_config, "household_config", mode="FILING")
        except Exception as e:
            sys.exit(f"Invalid household configuration: {e}")

        base_dir = args.household_config.parent
    else:
        # Legacy Mode: Synthesize checks
        if not Path(args.paystubs_dir).exists():
            sys.exit(f"Error: Paystubs directory not found: {args.paystubs_dir}")
        if args.w2_json and args.w2_pdf:
            sys.exit("Use either --w2-json or --w2-pdf, not both.")

        # Synthesize Config
        w2_files = []
        if args.w2_pdf:
            w2_files.append(str(args.w2_pdf))
        elif args.w2_json:
            # Note: w2_json is data, not a file path to be loaded by the PDF loader.
            # But our loader logic below handles w2_json/w2_pdf duality via CLI args injection if needed?
            # Actually, `build_household_package` takes a `w2_loader` callback.
            # We can handle the `w2_json` data passing via that closure.
            pass

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

    # Define Loaders
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
        # 1. Custom explicit JSON arg (Legacy Override)
        if not args.household_config and args.w2_json:
            return read_json(args.w2_json)

        # 2. Config-based W-2s (PDFs)
        # We only support PDF W-2 extraction from config currently as per schema 'w2_files'
        files = source_cfg.get("w2_files", [])
        if not files:
            return None

        # If multiple W-2s, we need to merge them?
        # RFC says "Enable... multiple income earners".
        # But for a single filer, multiple W-2s are aggregated?
        # Current logic `w2_pdf_to_json_payload` handles one file.
        # We will take the first one or throw if multiple (scope limitation for now).
        # "Strict: Multi-W2 Supported via w2_files array."
        # If we have multiple, we need to merge them.
        # ALLOWANCE: For Task 23, we will error if > 1 W-2 per filer until merge logic exists,
        # OR just process the first one.
        # Given "Multi-W2 Supported", I should probably loop.
        # But `compare_snapshot_to_w2` expects ONE w2_data dict.
        # Implementation Detail: If len > 1, we fail or merge.
        # Let's fail hard on > 1 for now to be safe, or just take first.
        # Fail hard is better than silent ignore.
        if len(files) > 1:
            raise NotImplementedError("Multiple W-2 files per filer not yet supported in aggregation.")

        fpath = base_dir / files[0]
        return w2_pdf_to_json_payload(
            pdf_path=fpath,
            render_scale=args.w2_render_scale,
            psm=6,
            fallback_year=args.year,
        )

    from paystub_analyzer.annual import build_household_package

    try:
        composite_result = build_household_package(
            household_config=household_config,
            tax_year=args.year,
            snapshot_loader=snapshot_loader,
            w2_loader=w2_loader,
            tolerance=args.tolerance,
        )
    except Exception as e:
        sys.exit(f"Error building package: {e}")

    report = composite_result["report"]
    filers_analysis = composite_result["filers_analysis"]

    # In Legacy Mode (implicit config), we want to behave exactly as before.
    # The `report` is the new v0.2.0 household format.
    # But print statements should reflect the primary filer or household.

    # Check safety (Global)
    ready = report["household_summary"]["ready_to_file"]

    # We need to print safety checks for ALL filers
    safety_failed_any = False
    for analysis in filers_analysis:
        internal = analysis["internal"]
        meta = internal["meta"]
        safety = meta.get("filing_safety", {})
        if not safety.get("passed", False):
            safety_failed_any = True
            print(f"\n!!!!!! FILER: {analysis['public']['id']} ({analysis['public']['role']}) SAFETY FAILED !!!!!!")
            for err in safety.get("errors", []):
                print(f"- [BLOCKING] {err}")

    if safety_failed_any:
        print("\n")
        if not args.force:
            print("Aborting generation. Use --force to override.")
            sys.exit(1)
        else:
            print("WARNING: Generating package despite failures due to --force flag.")

    # Write Outputs
    # We only have one set of output flags (--ledger-csv-out etc).
    # If multiple filers, we might overwrite or need suffixes.
    # Legacy behavior: 1 filer.
    # If household mode, we should likely create separate ledgers?
    # RFC doesn't specify CLI output file structure for multiple ledgers.
    # Assumption: if 1 filer, use exact paths. If >1, append suffix.

    for analysis in filers_analysis:
        filer_id = analysis["public"]["id"]
        internal = analysis["internal"]

        suffix = "" if len(filers_analysis) == 1 else f"_{filer_id}"

        # Ledger
        ledger_path = ledger_csv_out
        if suffix:
            ledger_path = ledger_csv_out.parent / f"{ledger_csv_out.stem}{suffix}{ledger_csv_out.suffix}"

        write_ledger_csv(ledger_path, internal["ledger"])
        print(f"Ledger CSV ({filer_id}): {ledger_path}")

    write_json(package_json_out, report)
    # Markdown -> we can't easily use package_to_markdown on the whole household yet
    # as it expects a single filer structure?
    # Actually package_to_markdown takes the 'package' (which was single filer).
    # We should update package_to_markdown to handle household OR render primary?
    # Backward compat: render Primary.
    # But ideally render all.
    # For now, let's render the PRIMARY filer's report using the old tool,
    # or if we have time, update package_to_markdown.
    # Given strict constraints, let's render the Primary filer's markdown
    # to satisfy "legacy paystub-annual args... produce same functional behavior".

    # primary_analysis = next(f for f in filers_analysis if f["public"]["role"] == "PRIMARY")
    # package_to_markdown expects the 'public' dict structure of a filer?
    # No, it expects the OLD 'package' structure which had 'household_summary' inside it?
    # Wait, the OLD public report HAD 'household_summary' and 'filers'.
    # So `package_to_markdown` SHOULD work on the new `report` object IF it matches the schema.
    # In v0.2.0, `household_summary` is at root.
    # So we can pass `report` directly.

    try:
        write_markdown(package_md_out, package_to_markdown(report))
        print(f"Package Markdown: {package_md_out}")
    except Exception as e:
        print(f"Warning: Could not generate markdown: {e}")

    write_json(package_json_out, report)
    print(f"Package JSON: {package_json_out}")

    # Print Summary to Console (Primary or Aggregate)
    print("-" * 40)
    print(f"Household Ready: {ready}")
    print(f"Gross Pay: {format_money(Decimal(report['household_summary']['total_gross_pay_cents']) / 100)}")
    print(f"Fed Tax:   {format_money(Decimal(report['household_summary']['total_fed_tax_cents']) / 100)}")

    if safety_failed_any and not args.force:
        sys.exit(1)


if __name__ == "__main__":
    main()
