import json
import pytest
import jsonschema
from pathlib import Path

# Load schema once
SCHEMA_PATH = Path(__file__).parent.parent / "paystub_analyzer" / "schemas" / "v0_3_0_contract.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())


@pytest.mark.unit
def test_valid_v0_3_0_output_conforms_to_schema():
    """
    Validates a sample v0.3.0 output object against the strict JSON schema.
    """
    sample_output = {
        "schema_version": "0.4.0",
        "household_summary": {"total_gross_pay_cents": 500000, "total_fed_tax_cents": 50000, "ready_to_file": True},
        "filers": [
            {
                "id": "primary",
                "role": "PRIMARY",
                "status": "MATCH",
                "gross_pay_cents": 500000,
                "fed_tax_cents": 50000,
                "state_tax_by_state_cents": {"VA": 25000},
                "audit_flags": ["Test Audit Log"],
                "correction_trace": [],
                "w2_source_count": 1,
                "w2_aggregate": {"box1_wages_cents": 500000, "box2_fed_tax_cents": 50000},
                "w2_sources": [
                    {"filename": "w2.pdf", "employer_ein": "12-3456789", "box1_wages_contribution_cents": 500000}
                ],
            }
        ],
    }

    # Should not raise Validation Error
    jsonschema.validate(instance=sample_output, schema=SCHEMA)


@pytest.mark.unit
def test_invalid_v0_3_0_output_fails_schema_missing_fields():
    """
    Validates that v0.3.0 output missing strict required fields fails validation.
    """
    malformed_output = {
        "schema_version": "0.4.0",
        "household_summary": {"total_gross_pay_cents": 500000, "total_fed_tax_cents": 50000, "ready_to_file": True},
        "filers": [
            {
                "id": "primary",
                "role": "PRIMARY",
                # Missing gross_pay_cents, fed_tax_cents, state_tax_by_state_cents, status, audit_flags, w2_source_count
                "w2_aggregate": {"box1_wages_cents": 500000, "box2_fed_tax_cents": 50000},
                "w2_sources": [],
            }
        ],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_output, schema=SCHEMA)


@pytest.mark.unit
def test_invalid_v0_2_0_output_fails_schema():
    """
    Validates that v0.2.0 style output (missing new fields) fails validation.
    """
    legacy_output = {
        "schema_version": "0.2.0",  # Wrong version
        "household_summary": {"total_gross_pay_cents": 500000, "total_fed_tax_cents": 50000, "ready_to_file": True},
        "filers": [
            {
                "id": "primary",
                "role": "PRIMARY",
                # Missing w2_aggregate, w2_sources
            }
        ],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=legacy_output, schema=SCHEMA)


@pytest.mark.integration
def test_cli_output_conforms_to_contract(tmp_path):
    """
    Integration: Call the library's official package builder and validate
    its output against the compiled schema.
    """
    from paystub_analyzer.annual import build_household_package
    from decimal import Decimal

    # Mock data source
    def mock_snapshot_loader(sources):
        from paystub_analyzer.core import PaystubSnapshot, AmountPair
        from decimal import Decimal

        # Helper to make simple pairs
        def pair(val):
            return AmountPair(val, val, "mock")

        def empty_pair():
            return AmountPair(None, None, None)

        return [
            PaystubSnapshot(
                file="mock_stub.pdf",
                pay_date="2025-01-15",
                gross_pay=pair(Decimal("5000.00")),
                federal_income_tax=pair(Decimal("500.00")),
                social_security_tax=empty_pair(),
                medicare_tax=empty_pair(),
                k401_contrib=empty_pair(),
                state_income_tax={},
                normalized_lines=[],
            )
        ]

    def mock_w2_loader(sources):
        return {
            "employer_ein": "12-3456789",
            "control_number": "CN123",
            "box_1_wages_tips_other_comp": 50000.00,
            "box_2_federal_income_tax_withheld": 5000.00,
            "w2_source_count": 1,
            "w2_aggregate": {
                "box1_wages_cents": 5000000,
                "box2_fed_tax_cents": 500000,
            },
            "w2_sources": [
                {"filename": "mock_w2.pdf", "employer_ein": "12-3456789", "box1_wages_contribution_cents": 5000000}
            ],
        }

    config = {
        "household_id": "test_household",
        "filers": [{"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "mock", "w2_files": ["mock"]}}],
    }

    # Execute
    # We pass tolerance
    package = build_household_package(
        household_config=config,
        tax_year=2025,
        snapshot_loader=mock_snapshot_loader,
        w2_loader=mock_w2_loader,
        tolerance=Decimal("0.05"),
    )

    # Save to file to test "written" contract if needed, or just validate dict
    output_dict = package["report"]

    # Validate
    # 1. Check version
    assert output_dict["schema_version"] == "0.4.0"
    assert "metadata" in output_dict
    assert output_dict["metadata"]["state"] == "UNKNOWN"  # From empty config in test

    # 2. Check Schema Compliance using the official validator
    from paystub_analyzer.utils.contracts import validate_output

    validate_output(output_dict, "v0_3_0_contract", mode="FILING")


@pytest.mark.integration
def test_corrections_integration_flow(tmp_path):
    """
    Integration: Verify that corrections passed to build_household_package
    are applied to the final output and result in valid schema with audit flags.
    """
    from paystub_analyzer.annual import build_household_package
    from decimal import Decimal

    # Mock data source (simplified)
    def mock_snapshot_loader(sources):
        from paystub_analyzer.core import PaystubSnapshot, AmountPair

        def pair(val):
            return AmountPair(val, val, "mock")

        def empty_pair():
            return AmountPair(None, None, None)

        return [
            PaystubSnapshot(
                file="mock_stub.pdf",
                pay_date="2025-01-15",
                gross_pay=pair(Decimal("5000.00")),  # Original: $5,000
                federal_income_tax=pair(Decimal("500.00")),
                social_security_tax=empty_pair(),
                medicare_tax=empty_pair(),
                k401_contrib=empty_pair(),
                state_income_tax={},
                normalized_lines=[],
            )
        ]

    def mock_w2_loader(sources):
        return None  # No W-2 for this test to focus on paystub override

    config = {
        # build_household_package takes household_config dict.
        # Inside it accesses config["filers"].
        # It doesn't seem to access household_id top level?
        # Let's check annual.py again. line 872: filers = household_config["filers"]
        # So "filers" key is needed.
        "filers": [{"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "mock"}}]
    }

    # Corrections: Override Gross Pay to $6,000
    corrections = {"primary": {"box1": {"value": 6000.00, "audit_reason": "Manual Override Integration Test"}}}

    # Execute
    package = build_household_package(
        household_config=config,
        tax_year=2025,
        snapshot_loader=mock_snapshot_loader,
        w2_loader=mock_w2_loader,
        tolerance=Decimal("0.05"),
        corrections=corrections,
    )

    output_dict = package["report"]
    filer = output_dict["filers"][0]

    # Assertions
    # 1. Check Value Override
    # Original 5000.00 -> Cents 500000
    # Corrected 6000.00 -> Cents 600000
    assert filer["gross_pay_cents"] == 600000

    # 2. Check Correction Trace
    correction_trace = filer.get("correction_trace", [])
    assert len(correction_trace) == 1
    trace = correction_trace[0]
    assert trace["corrected_field"] == "gross_pay"
    assert trace["corrected_value"] == 6000.00
    assert trace["reason"] == "Manual Override Integration Test"

    # 3. Check Schema Compliance
    from paystub_analyzer.utils.contracts import validate_output

    validate_output(output_dict, "v0_3_0_contract", mode="FILING")


def test_household_config_v0_4_schema_valid():
    from paystub_analyzer.utils.contracts import validate_output

    # Minimal v0.4 config
    config = {
        "version": "0.4.0",
        "household_id": "test_household_v4",
        "filing_year": 2025,
        "state": "CA",
        "filing_status": "MARRIED_JOINTLY",
        "filers": [{"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "mock"}}],
    }

    # Should not raise ContractError
    validate_output(config, "household_config")


def test_household_config_v0_4_schema_invalid():
    from paystub_analyzer.utils.contracts import validate_output, ContractError
    import pytest

    # Invalid v0.4 config (wrong state pattern)
    config = {
        "version": "0.4.0",
        "household_id": "test_household_v4",
        "filing_year": 2025,
        "state": "California",  # Invalid pattern, expecting 2 letters
        "filing_status": "MARRIED_JOINTLY",
        "filers": [{"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "mock"}}],
    }

    with pytest.raises(ContractError):
        validate_output(config, "household_config")


def test_household_config_v0_3_to_v0_4_migration():
    from paystub_analyzer.utils.migration import migrate_household_config

    v0_3_config = {
        "version": "0.3.0",
        "household_id": "test_household_v3",
        "filers": [{"id": "primary", "role": "PRIMARY", "sources": {"paystubs_dir": "mock", "w2_files": []}}],
    }

    migrated = migrate_household_config(v0_3_config)
    assert migrated["version"] == "0.4.0"

    from paystub_analyzer.utils.contracts import validate_output

    # Should still validate correctly without filing_year/state because they are optional metadata
    validate_output(migrated, "household_config")
