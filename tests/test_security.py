"""Security tests added for the DevSecOps lab (headers, input hardening, CSP-safe page)."""
import json
import pytest
from fraud_detector.api import MAX_RECENT_AMOUNTS, create_app
from fraud_detector.model import FraudModel

GOOD = {"amount": 1500, "hour": 14, "txn_last_hour": 1, "account_age_days": 400}


@pytest.fixture(scope="module")
def client():
    app = create_app(FraudModel(backend="numpy"))
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("path", ["/", "/api/health", "/static/app.js", "/static/style.css"])
def test_security_headers_on_every_response(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"


def test_api_responses_are_not_cached(client):
    assert client.get("/api/health").headers["Cache-Control"] == "no-store"


def test_page_has_no_inline_script_or_handlers(client):
    html = client.get("/").get_data(as_text=True)
    assert "onclick" not in html and "style=" not in html
    assert "<script>" not in html and 'src="/static/app.js"' in html


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_amount_rejected(client, bad):
    body = '{"amount": %s, "hour": 1, "txn_last_hour": 1, "account_age_days": 5}' % bad
    r = client.post("/api/assess", data=body, content_type="application/json")
    assert r.status_code == 400


def test_non_finite_recent_amount_rejected(client):
    body = '{"amount": 5, "hour": 1, "txn_last_hour": 1, "account_age_days": 5, "recent_amounts": [NaN]}'
    assert client.post("/api/assess", data=body, content_type="application/json").status_code == 400


def test_recent_amounts_must_be_a_list(client):
    r = client.post("/api/assess", json=dict(GOOD, recent_amounts=5))
    assert r.status_code == 400 and "list" in r.get_json()["error"]


def test_too_many_recent_amounts_rejected(client):
    r = client.post("/api/assess", json=dict(GOOD, recent_amounts=[1.0] * (MAX_RECENT_AMOUNTS + 1)))
    assert r.status_code == 400


def test_huge_integer_does_not_crash(client):
    body = '{"amount": 5, "hour": 1e999, "txn_last_hour": 1, "account_age_days": 5}'
    assert client.post("/api/assess", data=body, content_type="application/json").status_code == 400


def test_oversized_body_gets_413_json(client):
    r = client.post("/api/assess", data=json.dumps(dict(GOOD, pad="x" * 20000)), content_type="application/json")
    assert r.status_code == 413 and r.get_json()["error"] == "request body too large"


def test_error_responses_do_not_leak_internals(client):
    r = client.post("/api/assess", json=dict(GOOD, amount="abc"))
    text = r.get_data(as_text=True)
    assert r.status_code == 400 and "Traceback" not in text and "Error" not in text.replace("error", "")
