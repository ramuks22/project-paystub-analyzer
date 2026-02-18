#!/usr/bin/env python3

from __future__ import annotations

from decimal import Decimal
from typing import Any

from paystub_analyzer.core import AmountPair, PaystubSnapshot, as_float


def as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def build_w2_template(states: list[str] | None = None) -> dict[str, Any]:
    state_list = states or ["VA"]
    return {
        "tax_year": 2025,
        "box_1_wages_tips_other_comp": 0.00,
        "box_2_federal_income_tax_withheld": 0.00,
        "box_3_social_security_wages": 0.00,
        "box_4_social_security_tax_withheld": 0.00,
        "box_5_medicare_wages_and_tips": 0.00,
        "box_6_medicare_tax_withheld": 0.00,
        "state_boxes": [
            {
                "state": state,
                "box_16_state_wages_tips": 0.00,
                "box_17_state_income_tax": 0.00,
            }
            for state in state_list
        ],
    }


def compare_amounts(
    field: str,
    paystub_value: Decimal | None,
    w2_value: Decimal | None,
    tolerance: Decimal,
    mode: str = "strict",
) -> dict[str, Any]:
    if paystub_value is None:
        return {
            "field": field,
            "paystub": None,
            "w2": as_float(w2_value),
            "difference": None,
            "status": "missing_paystub_value",
        }
    if w2_value is None:
        return {
            "field": field,
            "paystub": as_float(paystub_value),
            "w2": None,
            "difference": None,
            "status": "missing_w2_value",
        }

    diff = paystub_value - w2_value
    if abs(diff) <= tolerance:
        status = "match"
    elif mode == "informational":
        status = "review_needed"
    else:
        status = "mismatch"

    return {
        "field": field,
        "paystub": as_float(paystub_value),
        "w2": as_float(w2_value),
        "difference": as_float(diff),
        "status": status,
    }


def pair_ytd(pair: AmountPair) -> Decimal | None:
    return pair.ytd


def compare_snapshot_to_w2(
    snapshot: PaystubSnapshot,
    w2_data: dict[str, Any],
    tolerance: Decimal,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    state_boxes = {
        entry["state"].upper(): entry
        for entry in w2_data.get("state_boxes", [])
        if isinstance(entry, dict) and entry.get("state")
    }

    comparisons = [
        compare_amounts(
            "federal_income_tax_withheld",
            pair_ytd(snapshot.federal_income_tax),
            as_decimal(w2_data.get("box_2_federal_income_tax_withheld")),
            tolerance,
        ),
        compare_amounts(
            "social_security_tax_withheld",
            pair_ytd(snapshot.social_security_tax),
            as_decimal(w2_data.get("box_4_social_security_tax_withheld")),
            tolerance,
        ),
        compare_amounts(
            "medicare_tax_withheld",
            pair_ytd(snapshot.medicare_tax),
            as_decimal(w2_data.get("box_6_medicare_tax_withheld")),
            tolerance,
        ),
        compare_amounts(
            "gross_pay_vs_box1_informational",
            pair_ytd(snapshot.gross_pay),
            as_decimal(w2_data.get("box_1_wages_tips_other_comp")),
            tolerance,
            mode="informational",
        ),
    ]

    all_states = sorted(set(snapshot.state_income_tax) | set(state_boxes))
    for state in all_states:
        w2_state_tax = None
        if state in state_boxes:
            w2_state_tax = as_decimal(state_boxes[state].get("box_17_state_income_tax"))
        paystub_state = snapshot.state_income_tax.get(state)
        comparisons.append(
            compare_amounts(
                f"{state}_state_income_tax_withheld",
                pair_ytd(paystub_state) if paystub_state else None,
                w2_state_tax,
                tolerance,
            )
        )

    summary = {
        "match": 0,
        "mismatch": 0,
        "review_needed": 0,
        "missing_paystub_value": 0,
        "missing_w2_value": 0,
    }
    for row in comparisons:
        status = row["status"]
        if status in summary:
            summary[status] += 1

    return comparisons, summary
