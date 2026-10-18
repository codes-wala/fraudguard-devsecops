"""Logistic-regression fraud model trained on SYNTHETIC data.

No real customer data is used. Labels are generated from a hidden risk
function plus noise, which lets the prototype demonstrate an end-to-end ML
component without any privacy exposure.
"""
import math
from typing import List, Tuple

import numpy as np

try:  # scikit-learn is preferred, but its compiled files can be blocked (e.g. by Windows Application Control)
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    HAVE_SKLEARN = True
except (ImportError, OSError):  # pragma: no cover - depends on the machine
    HAVE_SKLEARN = False

from .engine import (HIGH_AMOUNT, NEW_ACCOUNT_DAYS, NIGHT_END, NIGHT_START,
                     Transaction, count_structuring)

FEATURE_NAMES = ["log_amount", "is_night", "txn_last_hour", "is_foreign",
                 "is_new_device", "is_new_account", "structuring_count"]


def features(txn: Transaction) -> List[float]:
    return [
        math.log10(max(txn.amount, 1.0)),
        1.0 if NIGHT_START <= txn.hour < NIGHT_END else 0.0,
        float(txn.txn_last_hour),
        1.0 if txn.is_foreign else 0.0,
        1.0 if txn.is_new_device else 0.0,
        1.0 if txn.account_age_days < NEW_ACCOUNT_DAYS else 0.0,
        float(count_structuring(txn.recent_amounts)),
    ]


def generate_synthetic(n: int = 20000, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    amount = np.exp(rng.normal(7.8, 1.3, n)).clip(50, 1_000_000)
    night = (rng.random(n) < 0.12).astype(float)
    velocity = rng.poisson(1.2, n).astype(float)
    foreign = (rng.random(n) < 0.08).astype(float)
    new_dev = (rng.random(n) < 0.10).astype(float)
    new_acc = (rng.random(n) < 0.07).astype(float)
    struct = rng.poisson(0.15, n).astype(float)
    X = np.column_stack([np.log10(amount), night, velocity, foreign,
                         new_dev, new_acc, struct])
    logit = (-14.0 + 2.2 * X[:, 0] + 1.6 * night + 0.7 * velocity
             + 2.2 * foreign + 2.0 * new_dev + 1.4 * new_acc + 1.6 * struct)
    logit += rng.normal(0, 0.3, n)
    prob = 1 / (1 + np.exp(-logit))
    y = (rng.random(n) < prob).astype(int)
    return X, y


def _stratified_split(y, test_size, seed):
    """Stratified train/test index split using NumPy only."""
    rng = np.random.default_rng(seed)
    train, test = [], []
    for label in (0, 1):
        idx = rng.permutation(np.where(y == label)[0])
        k = int(round(len(idx) * test_size))
        test.extend(idx[:k]); train.extend(idx[k:])
    return np.array(train), np.array(test)


def _fit_logistic(X, y, C=1.0, iterations=100):
    """L2-regularised logistic regression (same objective as scikit-learn,
    C=1) solved with Newton's method. Returns (intercept, weights)."""
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    penalty = np.eye(len(w)); penalty[0, 0] = 0.0       # intercept not penalised
    for _ in range(iterations):  # pragma: no branch
        p = 1 / (1 + np.exp(-(Xb @ w)))
        grad = C * Xb.T @ (p - y) + penalty @ w
        hess = C * (Xb.T * (p * (1 - p))) @ Xb + penalty
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w[0], w[1:]


class FraudModel:
    """Logistic-regression fraud model (scikit-learn, or NumPy fallback)."""

    def __init__(self, seed: int = 42, backend: str = "auto"):
        if backend not in ("auto", "sklearn", "numpy"):
            raise ValueError("backend must be 'auto', 'sklearn' or 'numpy'")
        if backend == "sklearn" and not HAVE_SKLEARN:  # pragma: no cover
            raise ImportError("scikit-learn is not available")
        self.seed = seed
        self.backend = "sklearn" if (backend == "auto" and HAVE_SKLEARN) else (
            "numpy" if backend in ("auto", "numpy") else backend)
        self.metrics = {}
        self._train()

    def predict_proba(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        if self.backend == "sklearn":
            return self.clf.predict_proba(X)[:, 1]
        return 1 / (1 + np.exp(-(X @ self.coef + self.intercept)))

    def _train(self) -> None:
        X, y = generate_synthetic(seed=self.seed)
        if self.backend == "sklearn":
            Xtr, Xte, ytr, yte = train_test_split(
                X, y, test_size=0.25, random_state=self.seed, stratify=y)
            self.clf = LogisticRegression(max_iter=1000)
            self.clf.fit(Xtr, ytr)
        else:
            tr, te = _stratified_split(y, 0.25, self.seed)
            Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]
            self.intercept, self.coef = _fit_logistic(Xtr, ytr)
        pred = (self.predict_proba(Xte) >= 0.40).astype(int)
        tp = int(((pred == 1) & (yte == 1)).sum())
        fp = int(((pred == 1) & (yte == 0)).sum())
        fn = int(((pred == 0) & (yte == 1)).sum())
        self.metrics = {
            "samples": int(len(y)),
            "fraud_rate": round(float(y.mean()), 4),
            "accuracy": round(float((pred == yte).mean()), 4),
            "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
            "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
        }

    def score(self, txn: Transaction) -> float:
        p = self.predict_proba([features(txn)])[0]
        return float(min(max(p, 0.0), 1.0))
