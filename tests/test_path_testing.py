"""PATH TESTING - one test per independent (basis) path.

For every unit, the number of basis-path tests equals its cyclomatic
complexity V(G) (measured with radon), so each linearly independent path of
the control-flow graph is executed at least once.
"""
import pytest
from fraud_detector import engine as e
from tests.conftest import cases, make_txn


# ---- validate_transaction  V(G)=7 -------------------------------------------
@pytest.mark.parametrize("pid, kw, expected", **cases([
    ("V1 valid input",             {},                         []),
    ("V2 amount <= 0",             {"amount": 0},              ["amount out of allowed range"]),
    ("V3 amount > max only",       {"amount": 1_000_001},      ["amount out of allowed range"]),
    ("V4 hour < 0",                {"hour": -1},               ["hour must be 0-23"]),
    ("V5 hour > 23 only",          {"hour": 24},               ["hour must be 0-23"]),
    ("V6 negative velocity",       {"txn_last_hour": -1},      ["transaction count cannot be negative"]),
    ("V7 negative account age",    {"account_age_days": -5},   ["account age cannot be negative"]),
]))
def test_validate_paths(pid, kw, expected):
    assert e.validate_transaction(make_txn(**kw)) == expected


def test_validate_multiple_errors_accumulate():
    errs = e.validate_transaction(make_txn(amount=-1, hour=30, txn_last_hour=-2, account_age_days=-3))
    assert len(errs) == 4


# ---- count_structuring  V(G)=3  (loop testing: 0, 1, 2, many) -----------------
@pytest.mark.parametrize("pid, amounts, expected", **cases([
    ("S1 loop skipped (0 iterations)",        [],                              0),
    ("S2 one iteration, condition true",      [47_000],                        1),
    ("S3 one iteration, condition false",     [20_000],                        0),
    ("S4 two iterations, mixed",              [47_000, 10_000],                1),
    ("S5 many iterations, all in band",       [45_000, 46_000, 47_000, 49_999], 4),
]))
def test_count_structuring_paths(pid, amounts, expected):
    assert e.count_structuring(amounts) == expected


# ---- hard_block_reason  V(G)=5 ----------------------------------------------
@pytest.mark.parametrize("pid, kw, expected", **cases([
    ("H1 blacklisted merchant",                  {"is_blacklisted_merchant": True}, "Merchant is blacklisted"),
    ("H2 very high + new device",                {"amount": 250_000, "is_new_device": True},
                                                 "Very high amount from new device / new account"),
    ("H3 very high + new account (old device)",  {"amount": 250_000, "account_age_days": 10},
                                                 "Very high amount from new device / new account"),
    ("H4 very high but established customer",    {"amount": 250_000}, None),
    ("H5 normal amount",                         {}, None),
]))
def test_hard_block_paths(pid, kw, expected):
    assert e.hard_block_reason(make_txn(**kw)) == expected


# ---- rule_risk_score  V(G)=10 -----------------------------------------------
@pytest.mark.parametrize("pid, kw, risk", **cases([
    ("R1 baseline - nothing fires",              {}, 0),
    ("R2 high amount + foreign",                 {"amount": 60_000, "is_foreign": True}, 2),
    ("R3 high amount + new device only",         {"amount": 60_000, "is_new_device": True}, 2),
    ("R4 high amount, neither foreign nor new",  {"amount": 60_000}, 0),
    ("R5 night + medium amount",                 {"hour": 2, "amount": 12_000}, 1),
    ("R6 night but low amount",                  {"hour": 2, "amount": 500}, 0),
    ("R7 velocity above max",                    {"txn_last_hour": 6}, 2),
    ("R8 new account + medium amount",           {"account_age_days": 5, "amount": 12_000}, 1),
    ("R9 new account but low amount",            {"account_age_days": 5, "amount": 500}, 0),
    ("R10 structuring (3 amounts below limit)",  {"recent_amounts": [46_000, 47_000, 48_000]}, 2),
]))
def test_rule_risk_paths(pid, kw, risk):
    points, reasons = e.rule_risk_score(make_txn(**kw))
    assert points == risk
    assert len(reasons) == (1 if risk else 0)


def test_rule_risk_all_rules_fire_together():
    t = make_txn(amount=60_000, hour=3, txn_last_hour=9, is_foreign=True,
                 account_age_days=2, recent_amounts=[46_000, 47_000, 48_000])
    points, reasons = e.rule_risk_score(t)
    assert points == 2 + 1 + 2 + 1 + 2 and len(reasons) == 5


# ---- final_decision  V(G)=5 -------------------------------------------------
@pytest.mark.parametrize("pid, risk, ml, verdict", **cases([
    ("F1 ML >= block threshold",   0, 0.80, "BLOCK"),
    ("F2 risk >= block risk",      4, 0.10, "BLOCK"),
    ("F3 ML >= review threshold",  0, 0.50, "REVIEW"),
    ("F4 risk >= review risk",     2, 0.10, "REVIEW"),
    ("F5 everything low",          0, 0.10, "APPROVE"),
]))
def test_final_decision_paths(pid, risk, ml, verdict):
    assert e.final_decision(risk, ml) == verdict


# ---- assess  V(G)=4 and evaluate  V(G)=2 ------------------------------------
@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_assess_A1_invalid_ml_score(bad):
    with pytest.raises(ValueError):
        e.assess(make_txn(), bad)


def test_assess_A2_hard_block_short_circuits_rules():
    d = e.assess(make_txn(is_blacklisted_merchant=True), 0.0)
    assert d.verdict == "BLOCK" and d.reasons == ["Merchant is blacklisted"]


def test_assess_A3_clean_transaction_approved_without_ml_reason():
    d = e.assess(make_txn(), 0.05)
    assert d.verdict == "APPROVE" and d.reasons == []


def test_assess_A4_ml_reason_appended_when_score_high():
    d = e.assess(make_txn(), 0.55)
    assert d.verdict == "REVIEW" and any("ML model" in r for r in d.reasons)


def test_evaluate_E1_invalid_input_rejected_and_scorer_not_called():
    called = []
    d = e.evaluate(make_txn(amount=-5), lambda t: called.append(1) or 0.0)
    assert d.verdict == "REJECTED" and d.ml_score is None and not called


def test_evaluate_E2_valid_input_uses_scorer():
    d = e.evaluate(make_txn(), lambda t: 0.9)
    assert d.verdict == "BLOCK" and d.ml_score == 0.9
