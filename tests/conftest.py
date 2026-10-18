import pytest
from fraud_detector.engine import Transaction


def make_txn(**overrides):
    """A benign baseline transaction; tests override only what they exercise."""
    base = dict(amount=1500.0, hour=14, txn_last_hour=1, is_foreign=False,
                is_new_device=False, account_age_days=400,
                is_blacklisted_merchant=False, recent_amounts=[])
    base.update(overrides)
    return Transaction(**base)


@pytest.fixture
def txn():
    return make_txn


def cases(rows):
    """Use the first element of each row (e.g. 'R5 night + medium amount') as the pytest id."""
    return dict(argvalues=rows, ids=[r[0] for r in rows])
