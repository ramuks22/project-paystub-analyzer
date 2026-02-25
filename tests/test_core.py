import unittest
from decimal import Decimal
from pathlib import Path

import pytest

from paystub_analyzer.core import (
    extract_paystub_snapshot,
    extract_money_values_with_anomalies,
    extract_state_tax_pairs,
    parse_amount_pair_from_line,
    parse_pay_date_from_filename,
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


if __name__ == "__main__":
    unittest.main()
