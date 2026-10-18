import pytest
from fraud_detector.api import create_app, parse_transaction
from fraud_detector.model import FEATURE_NAMES, FraudModel, features
from tests.conftest import make_txn


@pytest.fixture(scope="module")
def model():
    return FraudModel()


@pytest.fixture
def client(model):
    app = create_app(model)
    app.config["TESTING"] = True
    return app.test_client()


GOOD = {"amount": 1500, "hour": 14, "txn_last_hour": 1, "account_age_days": 400}


def test_index_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200 and b"FraudGuard" in r.data


def test_health(client):
    j = client.get("/api/health").get_json()
    assert j["status"] == "ok" and "precision" in j["model_metrics"]


def test_assess_normal_is_approved(client):
    j = client.post("/api/assess", json=GOOD).get_json()
    assert j["verdict"] == "APPROVE"


def test_assess_suspicious_is_blocked(client):
    body = dict(GOOD, amount=85000, hour=2, is_foreign=True, is_new_device=True)
    assert client.post("/api/assess", json=body).get_json()["verdict"] == "BLOCK"


def test_assess_blacklisted_merchant(client):
    body = dict(GOOD, is_blacklisted_merchant="true")     # string boolean
    j = client.post("/api/assess", json=body).get_json()
    assert j["verdict"] == "BLOCK"


def test_assess_invalid_values_rejected_with_200(client):
    j = client.post("/api/assess", json=dict(GOOD, amount=-10)).get_json()
    assert j["verdict"] == "REJECTED"


@pytest.mark.parametrize("payload", [
    {"amount": 100}, {**GOOD, "amount": "abc"}, {**GOOD, "recent_amounts": ["x"]}, [1, 2, 3],
])
def test_assess_bad_payload_returns_400(client, payload):
    assert client.post("/api/assess", json=payload).status_code == 400


def test_assess_non_json_body_returns_400(client):
    assert client.post("/api/assess", data="not json").status_code == 400


def test_parse_transaction_bool_coercion():
    t = parse_transaction({**GOOD, "is_foreign": "YES", "is_new_device": 0})
    assert t.is_foreign is True and t.is_new_device is False


def test_features_vector_matches_names():
    assert len(features(make_txn())) == len(FEATURE_NAMES)


def test_model_scores_are_probabilities_and_ordered(model):
    benign = model.score(make_txn())
    risky = model.score(make_txn(amount=85000, hour=2, is_foreign=True, is_new_device=True))
    assert 0 <= benign <= 1 and 0 <= risky <= 1 and risky > benign


def test_model_metrics_reasonable_and_reproducible(model):
    assert model.metrics["accuracy"] > 0.90 and model.metrics["precision"] > 0.55
    assert FraudModel().metrics == model.metrics        # fixed seed -> same result


# ---- NumPy fallback backend (used when scikit-learn is blocked/unavailable) ----
@pytest.fixture(scope="module")
def np_model():
    return FraudModel(backend="numpy")


def test_numpy_backend_metrics_reasonable(np_model):
    assert np_model.backend == "numpy"
    assert np_model.metrics["accuracy"] > 0.90 and np_model.metrics["precision"] > 0.50


def test_numpy_backend_scores_ordered(np_model):
    benign = np_model.score(make_txn())
    risky = np_model.score(make_txn(amount=85000, hour=2, is_foreign=True, is_new_device=True))
    assert 0 <= benign < risky <= 1


def test_numpy_backend_close_to_default_backend(model, np_model):
    t = make_txn(amount=85000, hour=2, is_foreign=True, is_new_device=True)
    assert abs(model.score(t) - np_model.score(t)) < 0.05


def test_invalid_backend_rejected():
    with pytest.raises(ValueError):
        FraudModel(backend="gpu")
