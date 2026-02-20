import unittest

import pytest

from paystub_analyzer.w2_pdf import extract_w2_from_lines


@pytest.mark.unit
class W2PdfParsingTests(unittest.TestCase):
    def test_extract_core_boxes_from_lines(self) -> None:
        lines = [
            "1 Wages, tips, other compensation 50,000.00",
            "2 Federal income tax withheld 5,000.00",
            "3 Social security wages 50,000.00",
            "4 Social security tax withheld 3,100.00",
            "5 Medicare wages and tips 50,000.00",
            "6 Medicare tax withheld 725.00",
            "15 State 16 State wages, tips, etc. 17 State income tax",
            "VA 50,000.00 2,500.00",
            "AZ 20,000.00 500.00",
            "Form W-2 Wage and Tax Statement 2025",
        ]

        payload = extract_w2_from_lines(lines, fallback_year=2025)

        self.assertEqual(payload["tax_year"], 2025)
        self.assertEqual(payload["box_1_wages_tips_other_comp"], 50000.00)
        self.assertEqual(payload["box_2_federal_income_tax_withheld"], 5000.00)
        self.assertEqual(payload["box_4_social_security_tax_withheld"], 3100.00)
        self.assertEqual(payload["box_6_medicare_tax_withheld"], 725.00)

        states = {entry["state"]: entry for entry in payload["state_boxes"]}
        self.assertIn("VA", states)
        self.assertIn("AZ", states)
        self.assertEqual(states["VA"]["box_17_state_income_tax"], 2500.00)

    def test_repeated_box_line_chooses_correct_index(self) -> None:
        lines = [
            "1 Wages, tips, other comp. 2 Federal income tax withheld",
            "50000.00 5000.00 50000.00 5000.00",
            "3 Social security wages 4 Social security tax withheld",
            "50000.00 3100.00",
            "5 Medicare wages and tips 6 Medicare tax withheld",
            "50000.00 725.00",
            "Form W-2 Wage and Tax Statement 2025",
        ]
        payload = extract_w2_from_lines(lines, fallback_year=2025)
        self.assertEqual(payload["box_1_wages_tips_other_comp"], 50000.00)
        self.assertEqual(payload["box_2_federal_income_tax_withheld"], 5000.00)
        self.assertEqual(payload["box_4_social_security_tax_withheld"], 3100.00)
        self.assertEqual(payload["box_6_medicare_tax_withheld"], 725.00)


if __name__ == "__main__":
    unittest.main()
