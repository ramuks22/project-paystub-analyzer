from decimal import Decimal
from pathlib import Path
import unittest

from paystub_analyzer.core import parse_amount_pair_from_line, parse_pay_date_from_filename


class CoreParsingTests(unittest.TestCase):
    def test_amount_pair_standard_this_period_and_ytd(self) -> None:
        line = "Federal Income Tax -1,518.02 1,518.02"
        pair = parse_amount_pair_from_line(line)
        self.assertEqual(pair.this_period, Decimal("1518.02"))
        self.assertEqual(pair.ytd, Decimal("1518.02"))

    def test_amount_pair_ignores_right_column_spillover(self) -> None:
        line = "AZ State Income Tax 498.26 Core Ltd 18.28"
        pair = parse_amount_pair_from_line(line)
        self.assertIsNone(pair.this_period)
        self.assertEqual(pair.ytd, Decimal("498.26"))

    def test_amount_pair_handles_gross_pay_line(self) -> None:
        line = "Gross Pay $0.00 110,235.05 ."
        pair = parse_amount_pair_from_line(line)
        self.assertEqual(pair.this_period, Decimal("0.00"))
        self.assertEqual(pair.ytd, Decimal("110235.05"))

    def test_filename_pay_date_with_suffix(self) -> None:
        file_path = Path("pay_statements/Pay Date 2025-09-30_01.pdf")
        pay_date = parse_pay_date_from_filename(file_path)
        self.assertIsNotNone(pay_date)
        self.assertEqual(pay_date.isoformat(), "2025-09-30")


if __name__ == "__main__":
    unittest.main()
