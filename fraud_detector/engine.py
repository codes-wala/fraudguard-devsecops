"""Hybrid rule-based + ML decision engine for card/online-banking transactions.

The engine is deliberately written as small, single-purpose functions with
compound decision conditions, so that path testing and condition testing
(CO5) can be applied and measured on each unit.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

# ---- Business thresholds (all in INR / hours / counts) ----------------------
MAX_ALLOWED_AMOUNT = 1_000_000.0
HIGH_AMOUNT = 50_000.0
VERY_HIGH_AMOUNT = 200_000.0
STRUCTURING_BAND = 0.90          # amounts in [90%, 100%) of HIGH_AMOUNT
STRUCTURING_MIN_COUNT = 3
NIGHT_START = 0
NIGHT_END = 5                    # night = hours 0..4
MAX_VELOCITY = 5                 # transactions in the last hour
NEW_ACCOUNT_DAYS = 30
MEDIUM_AMOUNT = 10_000.0
REVIEW_THRESHOLD = 0.40          # ML probability
BLOCK_THRESHOLD = 0.75
REVIEW_RISK = 2                  # rule-risk points
BLOCK_RISK = 4


@dataclass
class Transaction:
    amount: float
    hour: int
    txn_last_hour: int
    is_foreign: bool
    is_new_device: bool
    account_age_days: int
    is_blacklisted_merchant: bool = False
    recent_amounts: List[float] = field(default_factory=list)


@dataclass
class Decision:
    verdict: str                      # APPROVE | REVIEW | BLOCK | REJECTED
    risk_points: int
    ml_score: Optional[float]
    reasons: List[str]


def validate_transaction(txn: Transaction) -> List[str]:
    """Return a list of input-validation errors (empty list = valid)."""
    errors = []
    if txn.amount <= 0 or txn.amount > MAX_ALLOWED_AMOUNT:
        errors.append("amount out of allowed range")
    if txn.hour < 0 or txn.hour > 23:
        errors.append("hour must be 0-23")
    if txn.txn_last_hour < 0:
        errors.append("transaction count cannot be negative")
    if txn.account_age_days < 0:
        errors.append("account age cannot be negative")
    return errors


def count_structuring(recent_amounts: List[float]) -> int:
    """Count recent amounts that sit just below the HIGH_AMOUNT limit."""
    count = 0
    lower = HIGH_AMOUNT * STRUCTURING_BAND
    for amount in recent_amounts:
        if lower <= amount < HIGH_AMOUNT:
            count += 1
    return count


def hard_block_reason(txn: Transaction) -> Optional[str]:
    """Rules that block a transaction outright, regardless of the ML score."""
    if txn.is_blacklisted_merchant:
        return "Merchant is blacklisted"
    if txn.amount >= VERY_HIGH_AMOUNT and (
        txn.is_new_device or txn.account_age_days < NEW_ACCOUNT_DAYS
    ):
        return "Very high amount from new device / new account"
    return None


def rule_risk_score(txn: Transaction) -> Tuple[int, List[str]]:
    """Accumulate rule-based risk points and human-readable reasons."""
    risk = 0
    reasons = []
    if txn.amount >= HIGH_AMOUNT and (txn.is_foreign or txn.is_new_device):
        risk += 2
        reasons.append("High amount with foreign location or new device")
    if NIGHT_START <= txn.hour < NIGHT_END and txn.amount >= MEDIUM_AMOUNT:
        risk += 1
        reasons.append("Medium/high amount during night hours")
    if txn.txn_last_hour > MAX_VELOCITY:
        risk += 2
        reasons.append("Unusually high transaction velocity")
    if txn.account_age_days < NEW_ACCOUNT_DAYS and txn.amount >= MEDIUM_AMOUNT:
        risk += 1
        reasons.append("New account with medium/high amount")
    if count_structuring(txn.recent_amounts) >= STRUCTURING_MIN_COUNT:
        risk += 2
        reasons.append("Repeated amounts just below the limit (structuring)")
    return risk, reasons


def final_decision(risk: int, ml_score: float) -> str:
    """Combine rule-risk points and ML probability into a verdict."""
    if ml_score >= BLOCK_THRESHOLD or risk >= BLOCK_RISK:
        return "BLOCK"
    if ml_score >= REVIEW_THRESHOLD or risk >= REVIEW_RISK:
        return "REVIEW"
    return "APPROVE"


def assess(txn: Transaction, ml_score: float) -> Decision:
    """Assess an already-validated transaction."""
    if not 0.0 <= ml_score <= 1.0:
        raise ValueError("ml_score must be between 0 and 1")
    blocked = hard_block_reason(txn)
    if blocked:
        return Decision("BLOCK", BLOCK_RISK, ml_score, [blocked])
    risk, reasons = rule_risk_score(txn)
    verdict = final_decision(risk, ml_score)
    if ml_score >= REVIEW_THRESHOLD:
        reasons.append(f"ML model fraud probability {ml_score:.2f}")
    return Decision(verdict, risk, ml_score, reasons)


def evaluate(txn: Transaction, scorer: Callable[[Transaction], float]) -> Decision:
    """Full pipeline: validate -> ML score -> rules -> verdict."""
    errors = validate_transaction(txn)
    if errors:
        return Decision("REJECTED", 0, None, errors)
    return assess(txn, scorer(txn))
