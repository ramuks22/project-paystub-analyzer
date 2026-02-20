from typing import Any
from datetime import datetime, timezone


def merge_corrections(
    extracted_data: dict[str, Any], corrections: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Merge user corrections into extracted data.

    Args:
        extracted_data: Dictionary of extracted values (gross_pay, federal_income_tax, etc.)
        corrections: user overrides for this filer (e.g. {"box1": {"value": 5000, "audit_reason": "OCR Error"}})

    Returns:
        (effective_data, correction_trace)
        effective_data: Copy of extracted_data with values overwritten.
        correction_trace: List of dicts describing the changes with metadata.
    """
    effective = extracted_data.copy()
    correction_trace: list[dict[str, Any]] = []

    if not corrections:
        return effective, correction_trace

    box_map: dict[str, str | tuple[str, str]] = {
        "box1": "gross_pay",
        "box2": "federal_income_tax",
        "box3": "social_security_wages",
        "box4": "social_security_tax",
        "box5": "medicare_wages",
        "box6": "medicare_tax",
    }

    for key, correction in corrections.items():
        if not isinstance(correction, dict):
            continue

        target_info = box_map.get(key, key)
        target_key = target_info if isinstance(target_info, str) else target_info[0]

        state_code = None

        if target_key == "state_income_tax":
            correction_trace.append(
                {
                    "corrected_field": target_key,
                    "original_value": None,
                    "corrected_value": None,
                    "reason": "WARNING: Cannot override bare 'state_income_tax'. Use 'state_income_tax_XY' (e.g. state_income_tax_VA). Skipping.",
                    "timestamp": correction.get("timestamp", datetime.now(timezone.utc).isoformat()),
                }
            )
            continue

        if target_key.startswith("state_income_tax_") and len(target_key) == 19:
            state_code = target_key.split("_")[-1]
            target_key = "state_income_tax"

        if target_key not in effective and target_key in ["social_security_wages", "medicare_wages"]:
            effective[target_key] = {"ytd": None}

        if target_key in effective:
            new_val = correction.get("value")
            reason = correction.get("audit_reason", "Manual Correction")
            timestamp = correction.get("timestamp", datetime.now(timezone.utc).isoformat())
            field_name = target_key

            if target_key == "state_income_tax" and state_code:
                effective[target_key] = effective[target_key].copy()
                if state_code in effective[target_key]:
                    effective[target_key][state_code] = effective[target_key][state_code].copy()
                else:
                    effective[target_key][state_code] = {"this_period": None}

                old_val = effective[target_key][state_code].get("ytd")
                effective[target_key][state_code]["ytd"] = new_val
                effective[target_key][state_code]["is_corrected"] = True
                effective[target_key][state_code]["correction_reason"] = reason

                field_name = f"state_income_tax_{state_code}"

                correction_trace.append(
                    {
                        "corrected_field": field_name,
                        "original_value": old_val,
                        "corrected_value": new_val,
                        "reason": reason,
                        "timestamp": timestamp,
                    }
                )
            elif isinstance(effective[target_key], dict) and "ytd" in effective[target_key]:
                old_val = effective[target_key].get("ytd")
                effective[target_key] = effective[target_key].copy()
                effective[target_key]["ytd"] = new_val
                effective[target_key]["is_corrected"] = True
                effective[target_key]["correction_reason"] = reason

                correction_trace.append(
                    {
                        "corrected_field": field_name,
                        "original_value": old_val,
                        "corrected_value": new_val,
                        "reason": reason,
                        "timestamp": timestamp,
                    }
                )
            else:
                old_val = effective[target_key]
                effective[target_key] = new_val
                correction_trace.append(
                    {
                        "corrected_field": field_name,
                        "original_value": old_val,
                        "corrected_value": new_val,
                        "reason": reason,
                        "timestamp": timestamp,
                    }
                )

    return effective, correction_trace
