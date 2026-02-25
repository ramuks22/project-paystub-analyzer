from __future__ import annotations

from decimal import Decimal

import pytest

from paystub_analyzer.core import AmountPair, PaystubSnapshot
from paystub_analyzer.cli import w2_validate


@pytest.mark.integration
def test_w2_cli_uses_latest_paystub_with_mixed_provider_filenames(tmp_path, monkeypatch) -> None:
    spouse_dir = tmp_path / "spouse"
    spouse_dir.mkdir()
    ukg_file = spouse_dir / "EEPayrollPayCheckDetail_01102025.pdf"
    adp_file = spouse_dir / "Pay Date 2025-12-26.pdf"
    unresolved = spouse_dir / "PayrollStatementUnknown.pdf"
    for file_path in (ukg_file, adp_file, unresolved):
        file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    extracted_paths: list[str] = []

    def fake_extract(snapshot_path, render_scale=2.5):  # type: ignore[no-untyped-def]
        extracted_paths.append(str(snapshot_path))
        return PaystubSnapshot(
            file=str(snapshot_path),
            pay_date="2025-12-26",
            gross_pay=AmountPair(Decimal("1000.00"), Decimal("20000.00"), "Gross Pay 1000.00 20000.00"),
            federal_income_tax=AmountPair(Decimal("100.00"), Decimal("2000.00"), "Federal Income Tax 100.00 2000.00"),
            social_security_tax=AmountPair(Decimal("62.00"), Decimal("1240.00"), "Social Security Tax 62.00 1240.00"),
            medicare_tax=AmountPair(Decimal("14.50"), Decimal("290.00"), "Medicare Tax 14.50 290.00"),
            k401_contrib=AmountPair(Decimal("50.00"), Decimal("1000.00"), "401k 50.00 1000.00"),
            state_income_tax={
                "VA": AmountPair(Decimal("40.00"), Decimal("800.00"), "VA State Income Tax 40.00 800.00")
            },
            normalized_lines=[],
            parse_anomalies=[],
        )

    monkeypatch.setattr("paystub_analyzer.cli.w2_validate.extract_paystub_snapshot", fake_extract)

    report_path = tmp_path / "out.md"
    json_path = tmp_path / "out.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "paystub-w2",
            "--paystubs-dir",
            str(spouse_dir),
            "--year",
            "2025",
            "--report-out",
            str(report_path),
            "--json-out",
            str(json_path),
        ],
    )

    w2_validate.main()

    assert extracted_paths == [str(adp_file)]
    report_text = report_path.read_text(encoding="utf-8")
    assert str(adp_file) in report_text
    assert "Latest payslip pay date: 2025-12-26" in report_text
