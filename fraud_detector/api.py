"""Flask web UI + JSON API for the fraud detection prototype (DevSecOps edition)."""
import math
from dataclasses import asdict
from flask import Flask, jsonify, render_template, request

from .engine import Transaction, evaluate
from .model import FraudModel

REQUIRED = ["amount", "hour", "txn_last_hour", "account_age_days"]
MAX_RECENT_AMOUNTS = 50
MAX_BODY_BYTES = 16 * 1024

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _finite(value) -> float:
    """float() that rejects NaN and infinity (they slip past range checks)."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not finite")
    return number


def parse_transaction(payload: dict) -> Transaction:
    """Convert a JSON payload into a Transaction; raises ValueError if bad."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    missing = [k for k in REQUIRED if k not in payload]
    if missing:
        raise ValueError("missing field(s): " + ", ".join(missing))
    raw_recent = payload.get("recent_amounts", [])
    if not isinstance(raw_recent, list):
        raise ValueError("recent_amounts must be a list")
    if len(raw_recent) > MAX_RECENT_AMOUNTS:
        raise ValueError("recent_amounts can have at most %d items" % MAX_RECENT_AMOUNTS)
    try:
        return Transaction(
            amount=_finite(payload["amount"]),
            hour=int(payload["hour"]),
            txn_last_hour=int(payload["txn_last_hour"]),
            is_foreign=_to_bool(payload.get("is_foreign", False)),
            is_new_device=_to_bool(payload.get("is_new_device", False)),
            account_age_days=int(payload["account_age_days"]),
            is_blacklisted_merchant=_to_bool(payload.get("is_blacklisted_merchant", False)),
            recent_amounts=[_finite(a) for a in raw_recent],
        )
    except (TypeError, ValueError, OverflowError):
        raise ValueError("fields have invalid types or values")


def create_app(model=None) -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config["MODEL"] = model or FraudModel()
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

    @app.after_request
    def security_headers(resp):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="request body too large"), 413

    @app.get("/")
    def index():
        return render_template("index.html", metrics=app.config["MODEL"].metrics)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", model_metrics=app.config["MODEL"].metrics)

    @app.post("/api/assess")
    def assess_route():
        try:
            txn = parse_transaction(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        decision = evaluate(txn, app.config["MODEL"].score)
        return jsonify(asdict(decision))

    return app
