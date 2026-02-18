import unittest

from paystub_analyzer.w2_pdf import extract_w2_from_lines


class W2PdfParsingTests(unittest.TestCase):
    def test_extract_core_boxes_from_lines(self) -> None:
        lines = [
            "1 Wages, tips, other compensation 110,235.05",
            "2 Federal income tax withheld 14,716.86",
            "3 Social security wages 110,235.05",
            "4 Social security tax withheld 6,468.43",
            "5 Medicare wages and tips 110,235.05",
            "6 Medicare tax withheld 1,512.78",
            "15 State 16 State wages, tips, etc. 17 State income tax",
            "VA 110,235.05 4,131.66",
            "AZ 10,000.00 498.26",
            "Form W-2 Wage and Tax Statement 2025",
        ]

        payload = extract_w2_from_lines(lines, fallback_year=2025)

        self.assertEqual(payload["tax_year"], 2025)
        self.assertEqual(payload["box_1_wages_tips_other_comp"], 110235.05)
        self.assertEqual(payload["box_2_federal_income_tax_withheld"], 14716.86)
        self.assertEqual(payload["box_4_social_security_tax_withheld"], 6468.43)
        self.assertEqual(payload["box_6_medicare_tax_withheld"], 1512.78)

        states = {entry["state"]: entry for entry in payload["state_boxes"]}
        self.assertIn("VA", states)
        self.assertIn("AZ", states)
        self.assertEqual(states["VA"]["box_17_state_income_tax"], 4131.66)

    def test_repeated_box_line_chooses_correct_index(self) -> None:
        lines = [
            "1 Wages, tips, other comp. 2 Federal income tax withheld",
            "92863.71 14716.86 92863.71 14716.86",
            "3 Social security wages 4 Social security tax withheld",
            "104329.56 6468.43",
            "5 Medicare wages and tips 6 Medicare tax withheld",
            "104329.56 1512.78",
            "Form W-2 Wage and Tax Statement 2025",
        ]
        payload = extract_w2_from_lines(lines, fallback_year=2025)
        self.assertEqual(payload["box_1_wages_tips_other_comp"], 92863.71)
        self.assertEqual(payload["box_2_federal_income_tax_withheld"], 14716.86)
        self.assertEqual(payload["box_4_social_security_tax_withheld"], 6468.43)
        self.assertEqual(payload["box_6_medicare_tax_withheld"], 1512.78)


if __name__ == "__main__":
    unittest.main()
