from typing import Any


def merge_corrections(extracted_data: dict[str, Any], corrections: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Merge user corrections into extracted data.

    Args:
        extracted_data: Dictionary of extracted values (gross_pay, federal_income_tax, etc.)
        corrections: user overrides for this filer (e.g. {"box1": {"value": 5000, "audit_reason": "OCR Error"}})

    Returns:
        (effective_data, audit_log)
        effective_data: Copy of extracted_data with values overwritten.
        audit_log: List of strings describing the changes.
    """
    effective = extracted_data.copy()
    audit_log: list[str] = []

    if not corrections:
        return effective, audit_log

    # Mapping of simple keys (box1) to extracted structure keys
    # Let's support Paystub corrections first as that's the primary "source of truth" for the filer's YTD.

    # Map strict schema keys to internal keys.
    # schema "box1" -> internal "gross_pay"
    # schema "box2" -> internal "federal_income_tax"
    # schema "box4" -> internal "social_security_tax"
    # schema "box6" -> internal "medicare_tax"

    box_map: dict[str, str | tuple[str, str]] = {
        "box1": "gross_pay",
        "box2": "federal_income_tax",
        "box3": "social_security_wages",  # For mapping to w2 equivalent if we tracked wages,
        # but currently extracted summary only has the tax parts.
        # Since the schema allows it, we'll map them so they don't break.
        "box4": "social_security_tax",
        "box5": "medicare_wages",
        "box6": "medicare_tax",
    }

    for key, correction in corrections.items():
        if not isinstance(correction, dict):
            continue

        target_info = box_map.get(key, key)
        target_key = target_info if isinstance(target_info, str) else target_info[0]

        # Determine if this is a state tax correction
        # Schema convention: "state_income_tax_VA" -> {"value": 500}
        state_code = None

        if target_key == "state_income_tax":
            audit_log.append(
                "WARNING: Cannot override bare 'state_income_tax'. Use 'state_income_tax_XY' (e.g. state_income_tax_VA). Skipping."
            )
            continue

        if target_key.startswith("state_income_tax_") and len(target_key) == 19:
            # 17 chars for 'state_income_tax_' + 2 for state code
            state_code = target_key.split("_")[-1]
            target_key = "state_income_tax"

        # Explicitly initialize mapping keys that are not natively extracted from paystubs
        if target_key not in effective and target_key in ["social_security_wages", "medicare_wages"]:
            effective[target_key] = {"ytd": None}

        if target_key in effective:
            new_val = correction.get("value")
            reason = correction.get("audit_reason", "Manual Correction")

            if target_key == "state_income_tax" and state_code:
                # Handle nested dict for state taxes
                effective[target_key] = effective[target_key].copy()
                if state_code in effective[target_key]:
                    effective[target_key][state_code] = effective[target_key][state_code].copy()
                else:
                    effective[target_key][state_code] = {"this_period": None}

                old_val = effective[target_key][state_code].get("ytd")
                effective[target_key][state_code]["ytd"] = new_val
                effective[target_key][state_code]["is_corrected"] = True
                effective[target_key][state_code]["correction_reason"] = reason

                audit_log.append(
                    f"CORRECTION: state_income_tax ({state_code}) YTD changed from {old_val} to {new_val} ({reason})"
                )
            elif isinstance(effective[target_key], dict) and "ytd" in effective[target_key]:
                old_val = effective[target_key].get("ytd")
                # Ensure we keep the structure
                effective[target_key] = effective[target_key].copy()
                effective[target_key]["ytd"] = new_val
                # Add metadata tag?
                effective[target_key]["is_corrected"] = True
                effective[target_key]["correction_reason"] = reason

                audit_log.append(f"CORRECTION: {target_key} YTD changed from {old_val} to {new_val} ({reason})")
            else:
                # If it's a flat value (unlikely for current extracted_data structure but possible)
                effective[target_key] = new_val
                audit_log.append(f"CORRECTION: {target_key} changed to {new_val} ({reason})")

    return effective, audit_log
