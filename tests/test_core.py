import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from paystub_analyzer.core import (
    extract_paystub_snapshot,
    extract_money_values_with_anomalies,
    extract_state_tax_pairs,
    list_paystub_files,
    parse_amount_pair_from_line,
    parse_pay_date_from_filename,
    parse_pay_date_from_text,
    select_latest_paystub,
)


@pytest.mark.unit
class CoreParsingTests(unittest.TestCase):
    def test_amount_pair_standard_this_period_and_ytd(self) -> None:
        line = "Federal Income Tax -1,518.02 1,518.02"
        pair = parse_amount_pair_from_line(line)
        self.assertEqual(pair.this_period, Decimal("1518.02"))
        self.assertEqual(pair.ytd, Decimal("1518.02"))

    def test_amount_pair_ignores_right_column_spillover(self) -> None:
        line = "AZ State Income Tax 498.26 Core Ltd 18.28"
        pair = parse_amount_pair_from_line(line)
        self.assertEqual(pair.this_period, Decimal("498.26"))
        self.assertIsNone(pair.ytd)

    def test_amount_pair_handles_gross_pay_line(self) -> None:
        line = "Gross Pay $0.00 50,000.00 ."
        pair = parse_amount_pair_from_line(line)
        self.assertEqual(pair.this_period, Decimal("0.00"))
        self.assertEqual(pair.ytd, Decimal("50000.00"))

    def test_filename_pay_date_with_suffix(self) -> None:
        file_path = Path("pay_statements/Pay Date 2025-09-30_01.pdf")
        pay_date = parse_pay_date_from_filename(file_path)
        self.assertIsNotNone(pay_date)
        self.assertEqual(pay_date.isoformat(), "2025-09-30")

    def test_filename_pay_date_ukg_format(self) -> None:
        file_path = Path("pay_statements/spouse/EEPayrollPayCheckDetail_01102025.pdf")
        pay_date = parse_pay_date_from_filename(file_path)
        self.assertIsNotNone(pay_date)
        self.assertEqual(pay_date.isoformat(), "2025-01-10")

    def test_text_pay_date_variants(self) -> None:
        variants = [
            "Pay Date 01/10/2025",
            "Pay Date: 01/10/2025",
            "Pay Date - 01/10/2025",
            "Pay Period End 01/10/2025",
            "Period Ending: 01/10/2025",
        ]
        for text in variants:
            with self.subTest(text=text):
                parsed = parse_pay_date_from_text(text)
                self.assertIsNotNone(parsed)
                assert parsed is not None
                self.assertEqual(parsed.isoformat(), "2025-01-10")

    def test_text_pay_date_prefers_pay_date_over_period_ending(self) -> None:
        text = "\n".join(
            [
                "Period Ending: 08/16/2025",
                "Pay Date: 08/22/2025",
            ]
        )
        parsed = parse_pay_date_from_text(text)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.isoformat(), "2025-08-22")

    def test_text_pay_date_skips_invalid_ocr_candidate(self) -> None:
        text = "\n".join(
            [
                "Period Ending 41/08/2025",
                "Pay Date 01/10/2025",
            ]
        )
        parsed = parse_pay_date_from_text(text)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.isoformat(), "2025-01-10")

    def test_list_paystub_files_keeps_unresolved_with_year_filter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            adp_2025 = temp_path / "Pay Date 2025-12-15.pdf"
            ukg_2025 = temp_path / "EEPayrollPayCheckDetail_01102025.pdf"
            adp_2024 = temp_path / "Pay Date 2024-12-31.pdf"
            unknown = temp_path / "PayrollStatementUnknown.pdf"
            for path in [adp_2025, ukg_2025, adp_2024, unknown]:
                path.write_bytes(b"")

            filtered = list_paystub_files(temp_path, year=2025)
            filtered_names = [path.name for path in filtered]
            self.assertIn(adp_2025.name, filtered_names)
            self.assertIn(ukg_2025.name, filtered_names)
            self.assertIn(unknown.name, filtered_names)
            self.assertNotIn(adp_2024.name, filtered_names)

    def test_select_latest_paystub_mixed_providers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            jan_ukg = temp_path / "EEPayrollPayCheckDetail_01102025.pdf"
            dec_adp = temp_path / "Pay Date 2025-12-26.pdf"
            unknown = temp_path / "PayrollStatementUnknown.pdf"
            for path in [jan_ukg, dec_adp, unknown]:
                path.write_bytes(b"")

            latest_file, latest_date = select_latest_paystub([jan_ukg, unknown, dec_adp])
            self.assertEqual(latest_file.name, dec_adp.name)
            self.assertEqual(latest_date.isoformat(), "2025-12-26")

    def test_money_regex_blocks_fragment_fusion(self) -> None:
        line = "-658 80 6,531.67"
        values, anomalies = extract_money_values_with_anomalies(line)
        self.assertEqual(values, [Decimal("6531.67")])
        self.assertEqual(anomalies, [])

    def test_money_regex_keeps_spaced_thousands_group(self) -> None:
        line = "Federal Income Tax 5, 000.00"
        values, anomalies = extract_money_values_with_anomalies(line)
        self.assertEqual(values, [Decimal("5000.00")])
        self.assertEqual(anomalies, [])

    def test_magnitude_guard_emits_structured_anomaly(self) -> None:
        line = "Federal Income Tax 658,806,531.67"
        values, anomalies = extract_money_values_with_anomalies(line)
        self.assertEqual(values, [])
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["code"], "implausible_amount_filtered")

    def test_state_tax_single_value_not_promoted_in_core(self) -> None:
        pairs = extract_state_tax_pairs(["AZ State Income Tax 498.26 Core Ltd 18.28"])
        self.assertIn("AZ", pairs)
        self.assertEqual(pairs["AZ"].this_period, Decimal("498.26"))
        self.assertIsNone(pairs["AZ"].ytd)

    def test_parse_anomaly_includes_field_guess_and_line_index(self) -> None:
        text = "\n".join(
            [
                "Pay Date: 12/31/2025",
                "Federal Income Tax 658,806,531.67",
            ]
        )
        snapshot = extract_paystub_snapshot(
            Path("pay_statements/Pay Date 2025-12-31.pdf"),
            ocr_text_provider=lambda *_: text,
        )
        self.assertEqual(len(snapshot.parse_anomalies), 1)
        anomaly = snapshot.parse_anomalies[0]
        self.assertEqual(anomaly["code"], "implausible_amount_filtered")
        self.assertEqual(anomaly["field_guess"], "federal_income_tax")
        self.assertEqual(anomaly["line_index"], "2")

    def test_ukg_pay_summary_gross_precedence(self) -> None:
        text = "\n".join(
            [
                "Pay Statement",
                "Period End Date 01/04/2025",
                "Pay Date 01/10/2025",
                "Earnings",
                "Pay Type Hours Current YTD",
                "Regular Earning 32.000000 $618.88 $618.88",
                "Taxes",
                "Federal Income Tax $81.83 $81.83",
                "Social Security Employee Tax $96.22 $96.22",
                "Employee Medicare $22.50 $22.50",
                "VA State Income Tax $46.02 $46.02",
                "Pay Summary",
                "Gross FIT Taxable Wages Taxes Deductions Net Pay",
                "Current $1,551.92 $1,335.31 $246.57 $221.33 $1,084.02",
                "YTD $1,551.92 $1,335.31 $246.57 $221.33 $1,084.02",
            ]
        )
        snapshot = extract_paystub_snapshot(
            Path("pay_statements/spouse/EEPayrollPayCheckDetail_01102025.pdf"),
            ocr_text_provider=lambda *_: text,
        )
        self.assertEqual(snapshot.pay_date, "2025-01-10")
        self.assertEqual(snapshot.gross_pay.this_period, Decimal("1551.92"))
        self.assertEqual(snapshot.gross_pay.ytd, Decimal("1551.92"))
        self.assertEqual(snapshot.federal_income_tax.ytd, Decimal("81.83"))
        self.assertEqual(snapshot.social_security_tax.ytd, Decimal("96.22"))
        self.assertEqual(snapshot.medicare_tax.ytd, Decimal("22.50"))

    def test_adp_gross_collision_uses_second_amount_as_ytd(self) -> None:
        text = "\n".join(
            [
                "Period Ending: 08/16/2025",
                "Pay Date: 08/22/2025",
                "Regular 23.5000 64.03 1,504.71 22,889.41",
                "Gross Pay 81,704.78 27,788.98 Wellness Admin 1.99 3.98",
                "Federal Income Tax -97.59 1,634.31",
                "VA State Income Tax -53.03 356.45",
            ]
        )
        snapshot = extract_paystub_snapshot(
            Path("pay_statements/spouse/Pay Date 2025-08-22.pdf"),
            ocr_text_provider=lambda *_: text,
        )
        self.assertEqual(snapshot.pay_date, "2025-08-22")
        self.assertEqual(snapshot.gross_pay.this_period, Decimal("1504.71"))
        self.assertEqual(snapshot.gross_pay.ytd, Decimal("27788.98"))


if __name__ == "__main__":
    unittest.main()
