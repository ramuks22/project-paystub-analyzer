from decimal import Decimal
from paystub_analyzer.core import PaystubSnapshot, AmountPair
from paystub_analyzer.annual import check_this_period_consistency, check_sequence_gaps, check_spike_anomalies


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
