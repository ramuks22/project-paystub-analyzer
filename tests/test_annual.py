import unittest
from decimal import Decimal

import pytest

from paystub_analyzer.annual import build_tax_filing_package, run_consistency_checks
from paystub_analyzer.core import AmountPair, PaystubSnapshot


def pair(this_period: str | None, ytd: str | None) -> AmountPair:
    this_value = Decimal(this_period) if this_period is not None else None
    ytd_value = Decimal(ytd) if ytd is not None else None
    return AmountPair(this_value, ytd_value, "evidence")


def snapshot(
    pay_date: str, gross: tuple[str | None, str | None], fed: tuple[str | None, str | None]
) -> PaystubSnapshot:
    return PaystubSnapshot(
        file=f"pay_statements/Pay Date {pay_date}.pdf",
        pay_date=pay_date,
        gross_pay=pair(*gross),
        federal_income_tax=pair(*fed),
        social_security_tax=pair("10.00", "10.00" if pay_date.endswith("15") else "20.00"),
        medicare_tax=pair("5.00", "5.00" if pay_date.endswith("15") else "10.00"),
        k401_contrib=pair("0.00", "0.00"),
        state_income_tax={"VA": pair("20.00", "20.00" if pay_date.endswith("15") else "40.00")},
        normalized_lines=[],
    )


@pytest.mark.unit
class AnnualTests(unittest.TestCase):
    def test_detects_ytd_decrease(self) -> None:
        s1 = snapshot("2025-01-15", gross=("100.00", "100.00"), fed=("20.00", "20.00"))
        s2 = snapshot("2025-01-31", gross=("100.00", "200.00"), fed=("15.00", "15.00"))
        issues = run_consistency_checks([s1, s2], tolerance=Decimal("0.01"))
        self.assertTrue(any(issue.code == "ytd_decrease" for issue in issues))

    def test_build_package_ready_to_file_true_on_match(self) -> None:
        s1 = snapshot("2025-01-15", gross=("100.00", "100.00"), fed=("20.00", "20.00"))
        s2 = snapshot("2025-01-31", gross=("100.00", "200.00"), fed=("20.00", "40.00"))
        w2 = {
            "box_1_wages_tips_other_comp": 200.00,
            "box_2_federal_income_tax_withheld": 40.00,
            "box_4_social_security_tax_withheld": 20.00,
            "box_6_medicare_tax_withheld": 10.00,
            "state_boxes": [{"state": "VA", "box_17_state_income_tax": 40.00}],
        }
        result = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2],
            tolerance=Decimal("0.01"),
            w2_data=w2,
        )
        self.assertTrue(result["report"]["household_summary"]["ready_to_file"])

    def test_repairs_state_ytd_underflow(self) -> None:
        s1 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-09-15.pdf",
            pay_date="2025-09-15",
            gross_pay=pair("5050.00", "93450.05"),
            federal_income_tax=pair("658.80", "12278.47"),
            social_security_tax=pair("296.72", "5436.90"),
            medicare_tax=pair("69.40", "1270.89"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("84.61", "498.26"),
                "VA": pair("127.21", "3193.41"),
            },
            normalized_lines=[],
        )
        s2 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-09-30.pdf",
            pay_date="2025-09-30",
            gross_pay=pair("5050.00", "98500.05"),
            federal_income_tax=pair("658.80", "12937.27"),
            social_security_tax=pair("296.73", "5733.63"),
            medicare_tax=pair("69.39", "1340.28"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("84.61", "582.87"),
                "VA": pair("127.21", "3320.62"),
            },
            normalized_lines=[],
        )
        s3 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-10-15.pdf",
            pay_date="2025-10-15",
            gross_pay=pair("5050.00", "103550.05"),
            federal_income_tax=pair("658.80", "13596.07"),
            social_security_tax=pair("296.72", "6030.35"),
            medicare_tax=pair("69.40", "1409.68"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("84.61", "667.48"),
                "VA": pair("127.21", "3447.83"),
            },
            normalized_lines=[],
        )
        # This snapshot has an underflow for VA.
        # The YTD for VA is 132.77, but the previous YTD was 3447.83.
        # This implies a negative "this period" amount, which is impossible.
        # The OCR likely misread the YTD as the "this period" amount.
        s4 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-10-31.pdf",
            pay_date="2025-10-31",
            gross_pay=pair("5050.00", "108600.05"),
            federal_income_tax=pair("658.80", "14254.87"),
            social_security_tax=pair("296.73", "6327.08"),
            medicare_tax=pair("69.39", "1479.07"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("84.61", "752.09"),
                "VA": pair(None, "132.77"),
            },
            normalized_lines=[],
        )

        package = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2, s3, s4],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )
        ledger = package["ledger"]
        row_1031 = next(r for r in ledger if r["pay_date"] == "2025-10-31")

        # Test the OCR Underflow Auto Heal!
        # The raw input s4 had VA: pair(None, 132.77)
        # Prev s3 had VA YTD: 3447.83
        # It should heal to This: 132.77 -> YTD = 3447.83 + 132.77 = 3580.60
        # AZ had None this period and 752.09 YTD, which carries over.
        # So Total YTD should be 3580.60 + 752.09 = 4332.69
        self.assertEqual(row_1031["state_tax_ytd_by_state"]["VA"], 3580.60)
        self.assertEqual(row_1031["state_tax_this_period_by_state"]["VA"], 132.77)
        self.assertEqual(row_1031["state_tax_ytd_by_state"]["AZ"], 752.09)
        self.assertEqual(row_1031["state_tax_ytd_total"], 4332.69)

        issues = package["meta"]["consistency_issues"]
        # Verify the warning was emitted
        self.assertTrue(any(iss["code"] == "state_ytd_underflow_corrected" for iss in issues))

        self.assertEqual(len(package["ledger"]), 4)

    def test_override_applied_before_underflow_repair(self) -> None:
        s1 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-09-15.pdf",
            pay_date="2025-09-15",
            gross_pay=pair("1836.36", "88336.41"),
            federal_income_tax=pair("121.77", "11923.84"),
            social_security_tax=pair("97.48", "5198.42"),
            medicare_tax=pair("22.80", "1215.76"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"VA": pair("46.76", "3240.17"), "AZ": pair(None, "498.26")},
            normalized_lines=[],
        )
        s2 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-09-30.pdf",
            pay_date="2025-09-30",
            gross_pay=pair("5050.00", "96600.05"),
            federal_income_tax=pair("658.80", "12941.30"),
            social_security_tax=pair("296.72", "5694.39"),
            medicare_tax=pair("69.39", "1331.75"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"VA": pair("211.22", "3584.16"), "AZ": pair(None, "498.26")},
            normalized_lines=[],
        )
        s3 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-09-30_01.pdf",
            pay_date="2025-09-30",
            gross_pay=pair("3213.64", "91550.05"),
            federal_income_tax=pair("358.66", "12282.50"),
            social_security_tax=pair("199.25", "5397.67"),
            medicare_tax=pair("46.60", "1262.36"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"VA": pair(None, "132.77"), "AZ": pair(None, "498.26")},
            normalized_lines=[],
        )

        package = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2, s3],
            tolerance=Decimal("0.01"),
            w2_data=None,
            pay_date_overrides={"Pay Date 2025-09-30_01.pdf": "2025-09-15"},
        )

        revised_row = next(
            row for row in package["raw_ledger"] if row["file"] == "pay_statements/Pay Date 2025-09-30_01.pdf"
        )
        original_row = next(
            row for row in package["raw_ledger"] if row["file"] == "pay_statements/Pay Date 2025-09-15.pdf"
        )

        # Expected from override-first chronology:
        # VA corrected YTD = 3240.17 + 132.77 = 3372.94
        self.assertEqual(revised_row["pay_date"], "2025-09-15")
        self.assertEqual(revised_row["state_tax_this_period_by_state"]["VA"], 132.77)
        self.assertEqual(revised_row["state_tax_ytd_by_state"]["VA"], 3372.94)
        self.assertEqual(revised_row["state_tax_ytd_total"], 3871.20)

        self.assertTrue(str(revised_row["calculation_status"]).startswith("Included"))
        self.assertTrue(str(original_row["calculation_status"]).startswith("Ignored"))
        self.assertEqual(original_row["canonical_file"], revised_row["file"])

        issues = package["meta"]["consistency_issues"]
        self.assertTrue(any(iss["code"] == "state_ytd_underflow_corrected" for iss in issues))
        self.assertTrue(
            any(
                "VA state tax YTD on 2025-09-15" in iss["message"] and iss["code"] == "state_ytd_underflow_corrected"
                for iss in issues
            )
        )

    def test_repairs_opening_state_ytd_outlier(self) -> None:
        s1 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-04-15.pdf",
            pay_date="2025-04-15",
            gross_pay=pair("5050.00", "41050.05"),
            federal_income_tax=pair("658.80", "5872.87"),
            social_security_tax=pair("296.72", "2430.43"),
            medicare_tax=pair("69.40", "568.41"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("84.61", "4224.42"),
                "VA": pair("127.21", "1727.77"),
            },
            normalized_lines=[],
        )
        s2 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-04-30.pdf",
            pay_date="2025-04-30",
            gross_pay=pair("5050.00", "46100.05"),
            federal_income_tax=pair("658.80", "6531.67"),
            social_security_tax=pair("296.73", "2727.16"),
            medicare_tax=pair("69.39", "637.80"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("84.61", "169.22"),
                "VA": pair("127.21", "1854.98"),
            },
            normalized_lines=[],
        )

        result = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )
        first_row = next(row for row in result["ledger"] if row["pay_date"] == "2025-04-15")
        self.assertEqual(first_row["state_tax_ytd_by_state"]["AZ"], 84.61)
        self.assertIn("AZ:", first_row["ytd_verification"])
        self.assertTrue(
            any(issue["code"] == "state_ytd_outlier_corrected" for issue in result["meta"]["consistency_issues"])
        )

    def test_repairs_state_ytd_delta_when_ocr_drops_leading_digit(self) -> None:
        s1 = PaystubSnapshot(
            file="pay_statements/spouse/Pay Date 2025-08-08.pdf",
            pay_date="2025-08-08",
            gross_pay=pair("1884.26", "26084.25"),
            federal_income_tax=pair("116.05", "1536.72"),
            social_security_tax=pair("116.82", "1617.22"),
            medicare_tax=pair("27.32", "378.22"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"VA": pair("61.87", "803.42")},
            normalized_lines=[],
        )
        s2 = PaystubSnapshot(
            file="pay_statements/spouse/Pay Date 2025-08-22.pdf",
            pay_date="2025-08-22",
            gross_pay=pair("1504.71", "27788.98"),
            federal_income_tax=pair("97.59", "1634.31"),
            social_security_tax=pair("105.70", "1722.92"),
            medicare_tax=pair("24.72", "402.94"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"VA": pair("53.03", "356.45")},  # OCR drop: should be 856.45
            normalized_lines=[],
        )
        s3 = PaystubSnapshot(
            file="pay_statements/spouse/Pay Date 2025-09-05.pdf",
            pay_date="2025-09-05",
            gross_pay=pair("1692.00", "29500.98"),
            federal_income_tax=pair("120.36", "1754.67"),
            social_security_tax=pair("119.19", "1842.11"),
            medicare_tax=pair("27.88", "430.82"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"VA": pair("63.94", "920.39")},
            normalized_lines=[],
        )

        result = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2, s3],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )
        row_0822 = next(row for row in result["ledger"] if row["pay_date"] == "2025-08-22")
        self.assertEqual(row_0822["state_tax_ytd_by_state"]["VA"], 856.45)
        self.assertEqual(row_0822["state_tax_this_period_by_state"]["VA"], 53.03)
        self.assertTrue(
            any(issue["code"] == "state_ytd_delta_repaired" for issue in result["meta"]["consistency_issues"])
        )

    def test_repairs_midyear_state_ytd_spike_and_this_period(self) -> None:
        s1 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-11-14.pdf",
            pay_date="2025-11-14",
            gross_pay=pair(None, "103333.38"),
            federal_income_tax=pair(None, "13705.53"),
            social_security_tax=pair(None, "6079.10"),
            medicare_tax=pair(None, "1421.73"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair(None, "498.26"),
                "VA": pair(None, "3834.31"),
            },
            normalized_lines=[],
        )
        s2 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-11-28.pdf",
            pay_date="2025-11-28",
            gross_pay=pair("6901.67", "110235.05"),
            federal_income_tax=pair("1011.33", "14716.86"),
            social_security_tax=pair("402.22", "6481.32"),
            medicare_tax=pair("94.06", "1515.79"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair("498.26", "5722.33"),
                "VA": pair("297.35", "4131.66"),
            },
            normalized_lines=[],
        )
        s3 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-12-15.pdf",
            pay_date="2025-12-15",
            gross_pay=pair(None, "110235.05"),
            federal_income_tax=pair(None, "14716.86"),
            social_security_tax=pair("12.89", "6468.43"),
            medicare_tax=pair("3.01", "1512.78"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={
                "AZ": pair(None, "498.26"),
                "VA": pair(None, "4131.66"),
            },
            normalized_lines=[],
        )

        result = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2, s3],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )
        target_row = next(row for row in result["ledger"] if row["pay_date"] == "2025-11-28")
        self.assertEqual(target_row["state_tax_ytd_by_state"]["AZ"], 498.26)
        self.assertIsNone(target_row["state_tax_this_period_by_state"]["AZ"])
        self.assertEqual(target_row["state_tax_this_period_total"], 297.35)
        self.assertEqual(target_row["state_tax_ytd_total"], 4629.92)
        self.assertIn("AZ:", target_row["ytd_verification"])
        self.assertTrue(
            any(issue["code"] == "state_ytd_outlier_corrected" for issue in result["meta"]["consistency_issues"])
        )

    def test_repairs_gross_this_period_from_ytd_delta(self) -> None:
        s1 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-11-28.pdf",
            pay_date="2025-11-28",
            gross_pay=pair("6901.67", "110235.05"),
            federal_income_tax=pair("1011.33", "14716.86"),
            social_security_tax=pair("402.22", "6481.32"),
            medicare_tax=pair("94.06", "1515.79"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"AZ": pair("0.00", "498.26"), "VA": pair("297.35", "4131.66")},
            normalized_lines=[],
        )
        s2 = PaystubSnapshot(
            file="pay_statements/Pay Date 2025-12-15.pdf",
            pay_date="2025-12-15",
            gross_pay=pair("104235.00", "110235.05"),
            federal_income_tax=pair(None, "14716.86"),
            social_security_tax=pair("12.89", "6468.43"),
            medicare_tax=pair("3.01", "1512.78"),
            k401_contrib=pair("0.00", "0.00"),
            state_income_tax={"AZ": pair(None, "498.26"), "VA": pair(None, "4131.66")},
            normalized_lines=[],
        )

        result = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )

        row_1215 = next(row for row in result["ledger"] if row["pay_date"] == "2025-12-15")
        self.assertEqual(row_1215["gross_pay_this_period"], 0.0)
        self.assertEqual(row_1215["gross_pay_ytd"], 110235.05)
        self.assertTrue(
            any(issue["code"] == "gross_this_period_repaired" for issue in result["meta"]["consistency_issues"])
        )

    def test_emits_single_federal_ytd_calc_mismatch_issue(self) -> None:
        s1 = snapshot("2025-01-15", gross=("100.00", "100.00"), fed=("20.00", "20.00"))
        s2 = snapshot("2025-01-31", gross=("100.00", "200.00"), fed=("20.00", "50.00"))

        result = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )

        fed_mismatch_issues = [
            issue
            for issue in result["meta"]["consistency_issues"]
            if issue["code"] == "ytd_calc_mismatch" and "federal_income_tax" in issue["message"]
        ]
        self.assertEqual(len(fed_mismatch_issues), 1)


if __name__ == "__main__":
    unittest.main()
