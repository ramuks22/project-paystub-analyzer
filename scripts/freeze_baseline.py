#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from paystub_analyzer.annual import analyze_filer, collect_annual_snapshots
from paystub_analyzer.core import PaystubSnapshot, as_float

DEFAULT_FILES = [
    "Pay Date 2025-12-31.pdf",
    "Pay Date 2025-11-28.pdf",
    "Pay Date 2025-04-30.pdf",
]


def _ensure_safe_output(out_dir: Path, mode: str) -> None:
    resolved = out_dir.expanduser().resolve()
    if mode == "real" and "/tests/fixtures/" in ("/" + resolved.as_posix().strip("/") + "/"):
        raise SystemExit(
            "Refusing to write real-data baseline under tests/fixtures/. "
            "Use a private path such as private_notes/baseline_v0.5.0/."
        )


def _snapshot_to_json(snapshot: PaystubSnapshot) -> dict[str, Any]:
    return {
        "file": snapshot.file,
        "pay_date": snapshot.pay_date,
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
        "state_income_tax": {
            state: {
                "this_period": as_float(pair.this_period),
                "ytd": as_float(pair.ytd),
                "evidence": pair.source_line,
            }
            for state, pair in sorted(snapshot.state_income_tax.items())
        },
        "parse_anomalies": snapshot.parse_anomalies,
    }


def _select_snapshots(all_snapshots: list[PaystubSnapshot], selected_files: list[str]) -> list[PaystubSnapshot]:
    selected: list[PaystubSnapshot] = []
    wanted = {name.strip() for name in selected_files if name.strip()}
    for snapshot in all_snapshots:
        if Path(snapshot.file).name in wanted:
            selected.append(snapshot)
    selected.sort(key=lambda snap: (snap.pay_date or "", snap.file))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze local baseline snapshots/anomalies for regression checks.")
    parser.add_argument("--paystubs-dir", type=Path, default=Path("pay_statements"))
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--tolerance", type=Decimal, default=Decimal("0.01"))
    parser.add_argument("--out-dir", type=Path, default=Path("private_notes/baseline_v0.5.0"))
    parser.add_argument(
        "--files",
        nargs="*",
        default=DEFAULT_FILES,
        help="Specific paystub filenames to snapshot (defaults to known hotfix files).",
    )
    parser.add_argument(
        "--mode",
        choices=["real", "synthetic"],
        default="real",
        help="Use real mode for local private baselines; synthetic mode allows fixture destinations.",
    )
    args = parser.parse_args()

    _ensure_safe_output(args.out_dir, args.mode)

    all_snapshots = collect_annual_snapshots(
        paystubs_dir=args.paystubs_dir,
        year=args.year,
        render_scale=2.8,
        psm=6,
    )
    if not all_snapshots:
        raise SystemExit(f"No paystubs found in {args.paystubs_dir} for year {args.year}.")

    selected = _select_snapshots(all_snapshots, args.files)
    if not selected:
        raise SystemExit("None of the requested files were found in the selected year/paystubs directory.")

    analysis = analyze_filer(
        tax_year=args.year,
        snapshots=all_snapshots,
        tolerance=args.tolerance,
        w2_data=None,
        filer_id="primary",
        role="PRIMARY",
    )

    payload = {
        "schema_version": "v0.5.1-baseline",
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tax_year": args.year,
        "paystubs_dir": str(args.paystubs_dir),
        "selected_filenames": [Path(s.file).name for s in selected],
        "selected_snapshots": [_snapshot_to_json(s) for s in selected],
        "consistency_issues": analysis["internal"]["meta"].get("consistency_issues", []),
        "ledger_rows": analysis["internal"].get("ledger", []),
    }

    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"baseline_{args.year}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Baseline written: {out_path}")
    print(f"Selected snapshots: {len(selected)} | All snapshots analyzed: {len(all_snapshots)}")


if __name__ == "__main__":
    main()
