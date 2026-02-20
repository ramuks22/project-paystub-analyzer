from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

from paystub_analyzer.w2_pdf import w2_pdf_to_json_payload


class W2Identity(NamedTuple):
    tax_year: int
    employer_ein: str
    control_number: str | None
    # Fallback fields for when EIN/Control are unknown
    box1_wages: Decimal
    box2_tax: Decimal


def as_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0.00")
    return Decimal(str(val))


def load_and_aggregate_w2s(
    files: list[str],
    base_dir: Path,
    year: int,
    pdf_render_scale: float = 3.0,
) -> dict[str, Any] | None:
    if not files:
        return None

    sources: list[dict[str, Any]] = []
    seen_strong_ids: set[tuple[int, str, str]] = set()
    # Weak ID: Year + 6 boxes
    seen_weak_ids: set[tuple[int, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]] = set()

    # Aggregators
    total_box1 = Decimal("0.00")
    total_box2 = Decimal("0.00")
    total_box3 = Decimal("0.00")
    total_box4 = Decimal("0.00")
    total_box5 = Decimal("0.00")
    total_box6 = Decimal("0.00")

    # State tax aggregation: State -> {"wages": D, "tax": D}
    state_totals: dict[str, dict[str, Decimal]] = {}

    for file_path in files:
        full_path = base_dir / file_path
        if not full_path.exists():
            raise FileNotFoundError(f"W-2 file not found: {file_path}")

        # Load Data
        if full_path.suffix.lower() == ".json":
            with full_path.open("r") as f:
                data = json.load(f)
        else:
            data = w2_pdf_to_json_payload(full_path, render_scale=pdf_render_scale, fallback_year=year)

        # 1. Identity Check (Two-Tier)
        raw_ein = data.get("employer_ein")
        raw_control = data.get("control_number")

        extracted_ein = str(raw_ein).strip() if raw_ein is not None else ""
        extracted_control = str(raw_control).strip() if raw_control is not None else ""

        # Use placeholders if empty
        is_weak_ein = not extracted_ein or extracted_ein in ("UNKNOWN_OCR", "None", "null")
        is_weak_control = not extracted_control or extracted_control in ("UNKNOWN_OCR", "None", "null")

        box1_val = as_decimal(data.get("box_1_wages_tips_other_comp"))
        box2_val = as_decimal(data.get("box_2_federal_income_tax_withheld"))

        processing_warnings: list[str] = []

        if not is_weak_ein and not is_weak_control:
            # Strong Identity: (Year, EIN, Control)
            strong_id = (year, extracted_ein, extracted_control)
            if strong_id in seen_strong_ids:
                raise ValueError(
                    f"Duplicate W-2 source detected (Strong ID): {file_path}. "
                    f"CIN={extracted_control}, EIN={extracted_ein} already processed."
                )
            seen_strong_ids.add(strong_id)
        else:
            # Weak Fallback: Strengthened with all tax boxes
            # (Year, Box1, Box2, Box3, Box4, Box5, Box6)
            weak_id = (
                year,
                box1_val,
                box2_val,
                as_decimal(data.get("box_3_social_security_wages")),
                as_decimal(data.get("box_4_social_security_tax_withheld")),
                as_decimal(data.get("box_5_medicare_wages_and_tips")),
                as_decimal(data.get("box_6_medicare_tax_withheld")),
            )

            if weak_id in seen_weak_ids:
                msg = f"Potential duplicate W-2 detected (Weak ID) in {file_path}. Review output."
                print(f"WARNING: {msg}")
                processing_warnings.append(msg)

            seen_weak_ids.add(weak_id)

        # Proceeding with Box Summation first.

        box1 = as_decimal(data.get("box_1_wages_tips_other_comp"))
        box2 = as_decimal(data.get("box_2_federal_income_tax_withheld"))
        total_box1 += box1
        total_box2 += box2
        total_box3 += as_decimal(data.get("box_3_social_security_wages"))
        total_box4 += as_decimal(data.get("box_4_social_security_tax_withheld"))
        total_box5 += as_decimal(data.get("box_5_medicare_wages_and_tips"))
        total_box6 += as_decimal(data.get("box_6_medicare_tax_withheld"))

        # State Aggregation
        for sbox in data.get("state_boxes", []):
            st = sbox["state"]
            if st not in state_totals:
                state_totals[st] = {"wages": Decimal(0), "tax": Decimal(0)}

            state_totals[st]["wages"] += as_decimal(sbox.get("box_16_state_wages_tips"))
            state_totals[st]["tax"] += as_decimal(sbox.get("box_17_state_income_tax"))

        # Source Metadata
        sources.append(
            {
                "filename": str(file_path),
                "control_number": extracted_control if not is_weak_control else "UNKNOWN_OCR",
                "employer_ein": extracted_ein if not is_weak_ein else "UNKNOWN_OCR",
                "box1_wages_contribution_cents": int(box1 * 100),
                "warnings": processing_warnings,
            }
        )

    # Collect all warnings from sources to surface at aggregate level if needed,
    # but currently we attached them to sources.
    # Let's also add a top-level warnings list.
    all_warnings = [w for s in sources for w in s.get("warnings", [])]

    # Construct Output
    # 1. Flattened keys for backward compatibility (used by compare_snapshot_to_w2)
    aggregated = {
        "tax_year": year,
        "box_1_wages_tips_other_comp": float(total_box1),
        "box_2_federal_income_tax_withheld": float(total_box2),
        "box_3_social_security_wages": float(total_box3),
        "box_4_social_security_tax_withheld": float(total_box4),
        "box_5_medicare_wages_and_tips": float(total_box5),
        "box_6_medicare_tax_withheld": float(total_box6),
        "state_boxes": [
            {
                "state": st,
                "box_16_state_wages_tips": float(vals["wages"]),
                "box_17_state_income_tax": float(vals["tax"]),
            }
            for st, vals in sorted(state_totals.items())
        ],
        # 2. v0.3.0 Metadata extensions
        "w2_source_count": len(files),
        "w2_sources": sources,
        "w2_aggregate": {
            "box1_wages_cents": int(total_box1 * 100),
            "box2_fed_tax_cents": int(total_box2 * 100),
            "box4_social_security_tax_cents": int(total_box4 * 100),
            "box6_medicare_tax_cents": int(total_box6 * 100),
        },
        "processing_warnings": all_warnings,
    }

    return aggregated
