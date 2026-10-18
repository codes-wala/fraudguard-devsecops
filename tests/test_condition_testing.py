"""CONDITION TESTING - MC/DC for compound decisions + boundary values.

For a decision with n atomic conditions, MC/DC needs n+1 tests: each atomic
condition is shown to independently change the outcome of the decision.
"""
import pytest
from fraud_detector import engine as e
from tests.conftest import make_txn

HIGH, MED = e.HIGH_AMOUNT, e.MEDIUM_AMOUNT


def _cond1(amount_high, foreign, new_dev):
    t = make_txn(amount=HIGH if amount_high else HIGH - 1,
                 is_foreign=foreign, is_new_device=new_dev)
    return e.rule_risk_score(t)[0] >= 2


# Decision D1:  A and (B or C)   A = amount>=HIGH, B = foreign, C = new device
@pytest.mark.parametrize("A,B,C,out,shows", [
    (True,  True,  False, True,  "baseline (T,T,F)"),
    (True,  False, False, False, "B flips outcome vs (T,T,F)"),
    (True,  False, True,  True,  "C flips outcome vs (T,F,F)"),
    (False, True,  False, False, "A flips outcome vs (T,T,F)"),
])
def test_mcdc_D1_high_amount_with_foreign_or_new_device(A, B, C, out, shows):
    assert _cond1(A, B, C) is out


def _hard(very_high, new_dev, new_acct):
    t = make_txn(amount=e.VERY_HIGH_AMOUNT if very_high else e.VERY_HIGH_AMOUNT - 1,
                 is_new_device=new_dev,
                 account_age_days=e.NEW_ACCOUNT_DAYS - 1 if new_acct else e.NEW_ACCOUNT_DAYS)
    return e.hard_block_reason(t) is not None


# Decision D2:  A and (B or C)   A = amount>=VERY_HIGH, B = new device, C = new account
@pytest.mark.parametrize("A,B,C,out", [
    (True, True, False, True), (True, False, False, False),
    (True, False, True, True), (False, True, False, False),
])
def test_mcdc_D2_hard_block_very_high_amount(A, B, C, out):
    assert _hard(A, B, C) is out


# Decision D3:  night_hour and amount>=MEDIUM
def _night(in_night, med):
    t = make_txn(hour=1 if in_night else 12, amount=MED if med else MED - 0.01)
    return e.rule_risk_score(t)[0] == 1


@pytest.mark.parametrize("A,B,out", [(True, True, True), (False, True, False), (True, False, False)])
def test_mcdc_D3_night_and_medium_amount(A, B, out):
    assert _night(A, B) is out


# Decision D4:  new_account and amount>=MEDIUM
def _newacct(new, med):
    t = make_txn(account_age_days=e.NEW_ACCOUNT_DAYS - 1 if new else e.NEW_ACCOUNT_DAYS,
                 amount=MED if med else MED - 0.01)
    return e.rule_risk_score(t)[0] == 1


@pytest.mark.parametrize("A,B,out", [(True, True, True), (False, True, False), (True, False, False)])
def test_mcdc_D4_new_account_and_medium_amount(A, B, out):
    assert _newacct(A, B) is out


# Decision D5/D6:  X or Y  (validation)
@pytest.mark.parametrize("amount,expect_err", [(100, False), (0, True), (e.MAX_ALLOWED_AMOUNT + 1, True)])
def test_mcdc_D5_amount_range(amount, expect_err):
    assert bool(e.validate_transaction(make_txn(amount=amount))) is expect_err


@pytest.mark.parametrize("hour,expect_err", [(12, False), (-1, True), (24, True)])
def test_mcdc_D6_hour_range(hour, expect_err):
    assert bool(e.validate_transaction(make_txn(hour=hour))) is expect_err


# Decision D7/D8:  ml>=T or risk>=R  (final verdict)
@pytest.mark.parametrize("ml,risk,expected", [
    (0.0, 0, "APPROVE"), (e.BLOCK_THRESHOLD, 0, "BLOCK"), (0.0, e.BLOCK_RISK, "BLOCK"),
    (e.REVIEW_THRESHOLD, 0, "REVIEW"), (0.0, e.REVIEW_RISK, "REVIEW"),
])
def test_mcdc_D7_D8_final_decision(ml, risk, expected):
    assert e.final_decision(risk, ml) == expected


# ---- Boundary-value checks on every threshold ---------------------------------
@pytest.mark.parametrize("kw,risk", [
    ({"amount": HIGH - 0.01, "is_foreign": True}, 0),
    ({"amount": HIGH, "is_foreign": True}, 2),
    ({"hour": 0, "amount": MED}, 1),          # first night hour
    ({"hour": 4, "amount": MED}, 1),          # last night hour
    ({"hour": 5, "amount": MED}, 0),          # first non-night hour
    ({"txn_last_hour": e.MAX_VELOCITY}, 0),   # equal -> not above
    ({"txn_last_hour": e.MAX_VELOCITY + 1}, 2),
    ({"recent_amounts": [45_000, 45_000]}, 0),               # count 2 < 3
    ({"recent_amounts": [45_000, 45_000, 45_000]}, 2),       # lower band edge included
    ({"recent_amounts": [44_999.99] * 3}, 0),                # just under the band
    ({"recent_amounts": [HIGH] * 3}, 0),                     # upper edge excluded
])
def test_boundary_values_rule_risk(kw, risk):
    assert e.rule_risk_score(make_txn(**kw))[0] == risk


def test_boundary_ml_score_limits_accepted():
    assert e.assess(make_txn(), 0.0).verdict == "APPROVE"
    assert e.assess(make_txn(), 1.0).verdict == "BLOCK"
