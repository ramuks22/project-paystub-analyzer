from decimal import Decimal
import unittest

from paystub_analyzer.annual import build_tax_filing_package, run_consistency_checks
from paystub_analyzer.core import AmountPair, PaystubSnapshot


def pair(this_period: str | None, ytd: str | None) -> AmountPair:
    this_value = Decimal(this_period) if this_period is not None else None
    ytd_value = Decimal(ytd) if ytd is not None else None
    return AmountPair(this_value, ytd_value, "evidence")


def snapshot(pay_date: str, gross: tuple[str | None, str | None], fed: tuple[str | None, str | None]) -> PaystubSnapshot:
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
        package = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2],
            tolerance=Decimal("0.01"),
            w2_data=w2,
        )
        self.assertTrue(package["ready_to_file"])

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

        package = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )
        first_row = next(row for row in package["ledger"] if row["pay_date"] == "2025-04-15")
        self.assertEqual(first_row["state_tax_ytd_by_state"]["AZ"], 84.61)
        self.assertIn("AZ:", first_row["ytd_verification"])
        self.assertTrue(
            any(issue["code"] == "state_ytd_outlier_corrected" for issue in package["consistency_issues"])
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

        package = build_tax_filing_package(
            tax_year=2025,
            snapshots=[s1, s2, s3],
            tolerance=Decimal("0.01"),
            w2_data=None,
        )
        target_row = next(row for row in package["ledger"] if row["pay_date"] == "2025-11-28")
        self.assertEqual(target_row["state_tax_ytd_by_state"]["AZ"], 498.26)
        self.assertIsNone(target_row["state_tax_this_period_by_state"]["AZ"])
        self.assertEqual(target_row["state_tax_this_period_total"], 297.35)
        self.assertEqual(target_row["state_tax_ytd_total"], 4629.92)
        self.assertIn("AZ:", target_row["ytd_verification"])
        self.assertTrue(
            any(issue["code"] == "state_ytd_outlier_corrected" for issue in package["consistency_issues"])
        )


if __name__ == "__main__":
    unittest.main()
