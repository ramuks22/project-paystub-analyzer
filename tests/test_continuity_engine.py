from decimal import Decimal
from paystub_analyzer.core import AmountPair, PaystubSnapshot
from paystub_analyzer.annual import (
    check_sequence_gaps,
    check_spike_anomalies,
    check_this_period_consistency,
    promote_ytd_candidates,
    run_consistency_checks,
)


def make_stub(pay_date: str, gross_period: Decimal, gross_ytd: Decimal) -> PaystubSnapshot:
    """Helper to create a snapshot for testing."""
    ap = AmountPair(gross_period, gross_ytd, "test line")
    empty_ap = AmountPair(None, None, None)
    return PaystubSnapshot(
        file="test.pdf",
        pay_date=pay_date,
        gross_pay=ap,
        federal_income_tax=empty_ap,
        social_security_tax=empty_ap,
        medicare_tax=empty_ap,
        k401_contrib=empty_ap,
        state_income_tax={},
        normalized_lines=[],
    )


def make_tax_stub(
    pay_date: str,
    gross_period: Decimal | None,
    gross_ytd: Decimal | None,
    fed_this: Decimal | None,
    fed_ytd: Decimal | None,
    ss_this: Decimal | None,
    ss_ytd: Decimal | None,
    med_this: Decimal | None,
    med_ytd: Decimal | None,
    state_this: Decimal | None,
    state_ytd: Decimal | None,
) -> PaystubSnapshot:
    return PaystubSnapshot(
        file=f"{pay_date}.pdf",
        pay_date=pay_date,
        gross_pay=AmountPair(gross_period, gross_ytd, "gross"),
        federal_income_tax=AmountPair(fed_this, fed_ytd, "fed"),
        social_security_tax=AmountPair(ss_this, ss_ytd, "ss"),
        medicare_tax=AmountPair(med_this, med_ytd, "med"),
        k401_contrib=AmountPair(None, None, None),
        state_income_tax={"AZ": AmountPair(state_this, state_ytd, "state_az")},
        normalized_lines=[],
    )


def test_ytd_calc_mismatch():
    s1 = make_stub("2025-01-01", Decimal("1000.00"), Decimal("1000.00"))
    s2 = make_stub("2025-01-15", Decimal("1000.00"), Decimal("2500.00"))  # Mismatch!

    issues = check_this_period_consistency([s1, s2], "gross_pay", tolerance=Decimal("0.05"))
    assert len(issues) == 1
    assert issues[0].code == "ytd_calc_mismatch"
    assert "2025-01-15" in issues[0].message


def test_sequence_gap():
    s1 = make_stub("2025-01-01", Decimal("1000.00"), Decimal("1000.00"))
    s2 = make_stub("2025-02-15", Decimal("1000.00"), Decimal("2000.00"))  # 45 days gap!

    issues = check_sequence_gaps([s1, s2], max_gap_days=20)
    assert len(issues) == 1
    assert issues[0].code == "SEQUENCE_GAP"
    assert "45 days" in issues[0].message


def test_spike_detection():
    snaps = [
        make_stub("2025-01-01", Decimal("1000.00"), Decimal("1000.00")),
        make_stub("2025-01-15", Decimal("1000.00"), Decimal("2000.00")),
        make_stub("2025-01-31", Decimal("6000.00"), Decimal("8000.00")),  # Spike!
    ]

    issues = check_spike_anomalies(snaps, multiplier=3)
    assert len(issues) == 1
    assert issues[0].code == "OUTLIER_EARNINGS"
    assert "6,000.00" in issues[0].message


def test_no_false_positives():
    snaps = [
        make_stub("2025-01-01", Decimal("1000.00"), Decimal("1000.00")),
        make_stub("2025-01-15", Decimal("1000.00"), Decimal("2000.00")),
    ]

    assert len(check_this_period_consistency(snaps, "gross_pay", tolerance=Decimal("0.05"))) == 0
    assert len(check_sequence_gaps(snaps)) == 0
    assert len(check_spike_anomalies(snaps)) == 0


def test_zero_period_ytd_promotion_accepts_monotonic_neighbors() -> None:
    snapshots = [
        make_tax_stub(
            "2025-11-28",
            Decimal("3000.00"),
            Decimal("100000.00"),
            Decimal("450.00"),
            Decimal("14000.00"),
            Decimal("120.00"),
            Decimal("6400.00"),
            Decimal("30.00"),
            Decimal("1500.00"),
            Decimal("50.00"),
            Decimal("450.00"),
        ),
        make_tax_stub(
            "2025-12-31",
            Decimal("0.00"),
            Decimal("100000.00"),
            Decimal("14716.86"),
            None,
            Decimal("6468.43"),
            None,
            Decimal("1512.78"),
            None,
            Decimal("498.26"),
            None,
        ),
    ]
    promoted, issues = promote_ytd_candidates(snapshots, tolerance=Decimal("0.01"))
    target = promoted[-1]
    assert target.federal_income_tax.this_period is None
    assert target.federal_income_tax.ytd == Decimal("14716.86")
    assert target.social_security_tax.this_period is None
    assert target.social_security_tax.ytd == Decimal("6468.43")
    assert target.medicare_tax.this_period is None
    assert target.medicare_tax.ytd == Decimal("1512.78")
    assert target.state_income_tax["AZ"].this_period is None
    assert target.state_income_tax["AZ"].ytd == Decimal("498.26")
    assert any(issue.code == "zero_period_ytd_promoted" for issue in issues)


def test_zero_period_ytd_promotion_rejects_non_monotonic_candidate() -> None:
    snapshots = [
        make_tax_stub(
            "2025-11-28",
            Decimal("3000.00"),
            Decimal("100000.00"),
            Decimal("450.00"),
            Decimal("1200.00"),
            Decimal("120.00"),
            Decimal("6400.00"),
            Decimal("30.00"),
            Decimal("1500.00"),
            Decimal("50.00"),
            Decimal("450.00"),
        ),
        make_tax_stub(
            "2025-12-31",
            Decimal("0.00"),
            Decimal("100000.00"),
            Decimal("800.00"),
            None,
            Decimal("6468.43"),
            None,
            Decimal("1512.78"),
            None,
            Decimal("498.26"),
            None,
        ),
    ]
    promoted, issues = promote_ytd_candidates(snapshots, tolerance=Decimal("0.01"))
    target = promoted[-1]
    assert target.federal_income_tax.this_period == Decimal("800.00")
    assert target.federal_income_tax.ytd is None
    assert any(issue.code == "zero_period_ytd_promotion_rejected" for issue in issues)


def test_promotion_runs_before_missing_final_values_check() -> None:
    snapshots = [
        make_tax_stub(
            "2025-11-28",
            Decimal("3000.00"),
            Decimal("100000.00"),
            Decimal("450.00"),
            Decimal("14000.00"),
            Decimal("120.00"),
            Decimal("6400.00"),
            Decimal("30.00"),
            Decimal("1500.00"),
            Decimal("50.00"),
            Decimal("450.00"),
        ),
        make_tax_stub(
            "2025-12-31",
            Decimal("0.00"),
            Decimal("100000.00"),
            Decimal("14716.86"),
            None,
            Decimal("6468.43"),
            None,
            Decimal("1512.78"),
            None,
            Decimal("498.26"),
            None,
        ),
    ]
    promoted, _ = promote_ytd_candidates(snapshots, tolerance=Decimal("0.01"))
    issues = run_consistency_checks(promoted, tolerance=Decimal("0.01"))
    assert not any(issue.code == "missing_final_values" for issue in issues)
