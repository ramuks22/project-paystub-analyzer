from paystub_analyzer.utils.corrections import merge_corrections


def test_merge_no_corrections():
    extracted = {"gross_pay": {"ytd": 100.0, "this_period": 10.0}}
    effective, logs = merge_corrections(extracted, {})
    assert effective == extracted
    assert logs == []


def test_merge_basic_override():
    extracted = {"gross_pay": {"ytd": 100.0}, "federal_income_tax": {"ytd": 20.0}}
    corrections = {"box1": {"value": 500.0, "audit_reason": "OCR Error"}}
    effective, logs = merge_corrections(extracted, corrections)

    assert effective["gross_pay"]["ytd"] == 500.0
    assert effective["federal_income_tax"]["ytd"] == 20.0
    assert len(logs) == 1
    assert logs[0]["corrected_field"] == "gross_pay"
    assert logs[0]["original_value"] == 100.0
    assert logs[0]["corrected_value"] == 500.0
    assert logs[0]["reason"] == "OCR Error"


def test_merge_multiple_overrides():
    extracted = {"gross_pay": {"ytd": 100.0}, "federal_income_tax": {"ytd": 20.0}}
    corrections = {
        "box1": {"value": 500.0, "audit_reason": "Fix 1"},  # Maps to gross_pay
        "box2": {"value": 50.0, "audit_reason": "Fix 2"},  # Maps to federal_income_tax
    }
    effective, logs = merge_corrections(extracted, corrections)

    assert effective["gross_pay"]["ytd"] == 500.0
    assert effective["federal_income_tax"]["ytd"] == 50.0
    assert len(logs) == 2


def test_merge_with_string_value():
    # Verify behavior if value is string (should pass through, type validation is later)
    extracted = {"gross_pay": {"ytd": 100.0}}
    corrections = {"box1": {"value": "500", "audit_reason": "Typo"}}
    effective, logs = merge_corrections(extracted, corrections)
    assert effective["gross_pay"]["ytd"] == "500"


def test_merge_non_dict_extracted_value():
    # If extraction structure changes to flat (hypothetically)
    extracted = {"some_flat_key": 123}
    corrections = {"some_flat_key": {"value": 456, "audit_reason": "Override"}}
    effective, logs = merge_corrections(extracted, corrections)
    assert effective["some_flat_key"] == 456
    assert logs[0]["corrected_field"] == "some_flat_key"
    assert logs[0]["corrected_value"] == 456


def test_merge_box3_box5_wages():
    # Tests that Box 3 and Box 5 overrides correctly map to SS Wages / Med Wages
    # even if those keys don't originally exist in the extracted paystub data
    extracted = {}
    corrections = {
        "box3": {"value": 11000.00, "audit_reason": "Corrected SS Wages"},
        "box5": {"value": 11000.00, "audit_reason": "Corrected Med Wages"},
    }
    effective, logs = merge_corrections(extracted, corrections)

    assert effective["social_security_wages"]["ytd"] == 11000.00
    assert effective["medicare_wages"]["ytd"] == 11000.00
    assert len(logs) == 2
    assert logs[0]["corrected_field"] == "social_security_wages"
    assert logs[0]["corrected_value"] == 11000.0
    assert logs[1]["corrected_field"] == "medicare_wages"
    assert logs[1]["corrected_value"] == 11000.0


def test_merge_state_tax_nested_override():
    # Tests that "state_income_tax_XX" correctly targets the nested dictionary
    extracted = {
        "state_income_tax": {"VA": {"this_period": 100.0, "ytd": 2000.0}, "MD": {"this_period": 50.0, "ytd": 1000.0}}
    }
    corrections = {
        "state_income_tax_VA": {"value": 2500.00, "audit_reason": "VA adjustment"},
        "state_income_tax_NY": {"value": 500.00, "audit_reason": "Added missing state"},
    }
    effective, logs = merge_corrections(extracted, corrections)

    assert effective["state_income_tax"]["VA"]["ytd"] == 2500.00
    assert effective["state_income_tax"]["MD"]["ytd"] == 1000.00  # untouched
    assert effective["state_income_tax"]["NY"]["ytd"] == 500.00  # newly added

    assert len(logs) == 2
    assert logs[0]["corrected_field"] == "state_income_tax_VA"
    assert logs[0]["corrected_value"] == 2500.0
    assert logs[1]["corrected_field"] == "state_income_tax_NY"
    assert logs[1]["corrected_value"] == 500.0


def test_merge_bare_state_tax_skips():
    # If the user tries to override "state_income_tax" instead of "state_income_tax_VA", it should safely skip
    extracted = {
        "state_income_tax": {
            "VA": {"this_period": 100.0, "ytd": 2000.0},
        }
    }
    corrections = {
        "state_income_tax": {"value": 2500.00, "audit_reason": "Vague state adjustment"},
    }
    effective, logs = merge_corrections(extracted, corrections)

    # Assert nothing was corrupted
    assert effective["state_income_tax"]["VA"]["ytd"] == 2000.00
    assert "WARNING: Cannot override bare" in logs[0]["reason"]
    assert logs[0]["corrected_field"] == "state_income_tax"
