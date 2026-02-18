#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract W-2 box values from a W-2 PDF into JSON.")
    parser.add_argument("--w2-pdf", type=Path, required=True, help="Path to W-2 PDF file.")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON file path.")
    parser.add_argument("--year", type=int, default=None, help="Fallback tax year.")
    parser.add_argument("--render-scale", type=float, default=3.0, help="OCR render scale.")
    args = parser.parse_args()

    payload = w2_pdf_to_json_payload(
        pdf_path=args.w2_pdf,
        render_scale=args.render_scale,
        psm=6,
        fallback_year=args.year,
    )
    if payload.get("tax_year") is None and args.year is not None:
        payload["tax_year"] = args.year

    write_json(args.out, payload)

    print(f"Extracted W-2 JSON: {args.out}")
    print("Review extracted values and evidence before filing.")


if __name__ == "__main__":
    main()
