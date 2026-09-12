"""Contract tests: exact responses, auth bypasses, validation and shared replay state."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import fakeredis
import jwt
import pytest
from fastapi.testclient import TestClient

from devops_service.app import create_app
from devops_service.settings import Settings

KEY = "2f5ae96c-b558-4c7b-a590-a501ae1c3f6c"
SECRET = "test-only-signing-secret-with-at-least-32-bytes"
PAYLOAD = {
    "message": "This is a test",
    "to": "Juan Perez",
    "from": "Rita Asturia",
    "timeToLifeSec": 45,
}


def token(**changes):
    now = int(time.time())
    claims = {
        "iss": "devops-assessment",
        "aud": "devops",
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        "jti": str(uuid4()),
    }
    claims.update(changes)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def headers(value=None):
    return {"X-Parse-REST-API-Key": KEY, "X-JWT-KWY": value or token()}


@pytest.fixture
def setup():
    server = fakeredis.FakeServer()
    redis = fakeredis.FakeRedis(server=server)
    settings = Settings(api_key=KEY, jwt_secret=SECRET, redis_url="redis://localhost:6379/0")
    with TestClient(create_app(settings, redis)) as client:
        yield client, server, settings, redis


def test_post_returns_exact_contract(setup):
    response = setup[0].post("/DevOps", json=PAYLOAD, headers=headers())
    assert response.status_code == 200
    assert response.json() == {"message": "Hello Juan Perez your message will be send"}


def test_recipient_is_dynamic(setup):
    response = setup[0].post("/DevOps", json={**PAYLOAD, "to": "María"}, headers=headers())
    assert response.json() == {"message": "Hello María your message will be send"}


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
def test_other_methods_are_plain_error(setup, method):
    response = setup[0].request(method, "/DevOps")
    assert response.status_code == 405
    assert response.text == "ERROR"
    assert response.headers["allow"] == "POST"


def test_head_has_no_body(setup):
    response = setup[0].head("/DevOps")
    assert response.status_code == 405
    assert response.content == b""


@pytest.mark.parametrize("auth", [{}, {"X-Parse-REST-API-Key": KEY}, {"X-JWT-KWY": "invalid"}])
def test_missing_credentials_are_rejected(setup, auth):
    assert setup[0].post("/DevOps", json=PAYLOAD, headers=auth).status_code == 401


def test_wrong_key_is_rejected(setup):
    auth = {**headers(), "X-Parse-REST-API-Key": "wrong"}
    assert setup[0].post("/DevOps", json=PAYLOAD, headers=auth).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 1},
        {"nbf": 9999999999},
        {"iss": "other"},
        {"aud": "other"},
        {"jti": ""},
        {"jti": "not-a-uuid"},
        {"exp": int(time.time()) + 3600},
        {"iat": "invalid"},
    ],
)
def test_invalid_claims_are_rejected(setup, changes):
    assert (
        setup[0].post("/DevOps", json=PAYLOAD, headers=headers(token(**changes))).status_code == 401
    )


def test_invalid_signature_is_rejected(setup):
    claims = jwt.decode(token(), SECRET, algorithms=["HS256"], audience="devops")
    forged = jwt.encode(claims, "another-secret-with-at-least-32-bytes", algorithm="HS256")
    assert setup[0].post("/DevOps", json=PAYLOAD, headers=headers(forged)).status_code == 401


def test_missing_required_claim_is_rejected(setup):
    claims = jwt.decode(token(), SECRET, algorithms=["HS256"], audience="devops")
    del claims["jti"]
    unsigned = jwt.encode(claims, SECRET, algorithm="HS256")
    assert setup[0].post("/DevOps", json=PAYLOAD, headers=headers(unsigned)).status_code == 401


def test_token_is_single_use_across_replicas(setup):
    client, server, settings, _ = setup
    auth = headers()
    assert client.post("/DevOps", json=PAYLOAD, headers=auth).status_code == 200
    with TestClient(create_app(settings, fakeredis.FakeRedis(server=server))) as replica:
        assert replica.post("/DevOps", json=PAYLOAD, headers=auth).status_code == 409


def test_concurrent_replay_has_exactly_one_winner(setup):
    auth = headers()
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(
            pool.map(
                lambda _: setup[0].post("/DevOps", json=PAYLOAD, headers=auth).status_code, range(8)
            )
        )
    assert sorted(codes) == [200, 409, 409, 409, 409, 409, 409, 409]


@pytest.mark.parametrize(
    "field,value",
    [
        ("to", ""),
        ("from", "   "),
        ("message", 12),
        ("timeToLifeSec", 0),
        ("timeToLifeSec", -1),
        ("timeToLifeSec", True),
        ("timeToLifeSec", "45"),
        ("timeToLifeSec", 86401),
        ("unexpected", "field"),
    ],
)
def test_invalid_payload_is_rejected(setup, field, value):
    assert (
        setup[0].post("/DevOps", json={**PAYLOAD, field: value}, headers=headers()).status_code
        == 422
    )


def test_missing_field_is_rejected(setup):
    assert setup[0].post("/DevOps", json={"to": "Juan"}, headers=headers()).status_code == 422


def test_malformed_json_is_rejected(setup):
    response = setup[0].post(
        "/DevOps", content="{", headers={**headers(), "Content-Type": "application/json"}
    )
    assert response.status_code == 422


def test_wrong_media_type_is_rejected(setup):
    assert (
        setup[0]
        .post("/DevOps", content="hello", headers={**headers(), "Content-Type": "text/plain"})
        .status_code
        == 415
    )


def test_oversized_payload_is_rejected(setup):
    assert (
        setup[0]
        .post("/DevOps", json={**PAYLOAD, "message": "a" * 17000}, headers=headers())
        .status_code
        == 413
    )


def test_unknown_routes_are_not_redirected(setup):
    assert setup[0].get("/unknown").status_code == 404
    assert setup[0].post("/DevOps/", json=PAYLOAD, headers=headers()).status_code == 404


def test_redis_failure_fails_closed_and_readiness_fails(setup):
    client, server, _, _ = setup
    server.connected = False
    assert client.post("/DevOps", json=PAYLOAD, headers=headers()).status_code == 503
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_readiness_when_redis_works(setup):
    assert setup[0].get("/readyz").status_code == 200


def test_invalid_request_does_not_consume_token(setup):
    auth = headers()
    assert setup[0].post("/DevOps", json={}, headers=auth).status_code == 422
    assert setup[0].post("/DevOps", json=PAYLOAD, headers=auth).status_code == 200


def test_settings_reject_insecure_secrets():
    with pytest.raises(ValueError):
        Settings(api_key=KEY, jwt_secret="short", redis_url="redis://localhost:6379/0")


def test_numeric_but_noninteger_timestamps_are_rejected(setup):
    assert (
        setup[0]
        .post("/DevOps", json=PAYLOAD, headers=headers(token(iat=float(int(time.time())))))
        .status_code
        == 401
    )


def test_default_factory_reads_environment_and_closes_connection(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200


def test_expiration_during_request_is_rejected(setup, monkeypatch):
    from fastapi import HTTPException

    from devops_service.security import consume_token

    monkeypatch.setattr("devops_service.security.time.time", lambda: 1000)
    with pytest.raises(HTTPException) as error:
        consume_token(setup[3], {"exp": 1000, "iss": "devops-assessment", "jti": str(uuid4())})
    assert error.value.status_code == 401
