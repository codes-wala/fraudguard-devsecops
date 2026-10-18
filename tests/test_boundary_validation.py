"""Boundary tests added after mutation analysis (iteration 2) exposed that
valid edge values of validate_transaction / thresholds were never asserted."""
import pytest
from fraud_detector import engine as e
from tests.conftest import make_txn


@pytest.mark.parametrize("kw", [
    {"amount": 0.01},                       # smallest positive amount is valid
    {"amount": e.MAX_ALLOWED_AMOUNT},       # maximum allowed amount is valid
    {"hour": 0}, {"hour": 23},              # both hour edges valid
    {"txn_last_hour": 0},                   # zero velocity valid
    {"account_age_days": 0},                # brand-new account valid
], ids=lambda kw: str(kw))
def test_valid_edge_values_are_accepted(kw):
    assert e.validate_transaction(make_txn(**kw)) == []


def test_assess_reason_added_exactly_at_review_threshold():
    d = e.assess(make_txn(), e.REVIEW_THRESHOLD)
    assert d.verdict == "REVIEW" and any("ML model" in r for r in d.reasons)


def test_rejected_decision_carries_zero_risk_points():
    d = e.evaluate(make_txn(amount=0), lambda t: 0.0)
    assert d.risk_points == 0 and d.verdict == "REJECTED"
