"""`krutrim_agent_backend.auth` — hashing, JWT tokens, `AuthService`, and the
`/api/auth` routes (register / login / refresh / logout / me).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.auth import (
    AuthService,
    InvalidCredentialsError,
    InvalidTokenError,
    UsernameTakenError,
    WeakPasswordError,
)
from krutrim_agent_backend.auth import tokens as jwt_tokens
from krutrim_agent_backend.auth.hashing import (
    hash_password,
    needs_rehash,
    verify_password,
)
from krutrim_agent_management import LocalAuthStorage

SECRET = "test-secret-please-ignore-0123456789abcdef"  # >= 32 bytes for HS256


# ── hashing ──────────────────────────────────────────────────────────
def test_hash_roundtrip_and_mismatch():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password(h, "correct horse") is True
    assert verify_password(h, "wrong") is False


def test_verify_never_raises_on_garbage_hash():
    assert verify_password("not-an-argon2-hash", "whatever") is False
    assert needs_rehash("not-an-argon2-hash") is True


# ── tokens ───────────────────────────────────────────────────────────
def test_access_token_roundtrip():
    t = jwt_tokens.encode_access(
        SECRET,
        user_id="u1",
        username="a",
        role="admin",
        jti="j1",
        ttl=timedelta(minutes=5),
    )
    claims = jwt_tokens.decode(SECRET, t, expected_type="access")
    assert claims["sub"] == "u1"
    assert claims["username"] == "a"
    assert claims["role"] == "admin"


def test_decode_rejects_wrong_secret_type_and_expiry():
    t = jwt_tokens.encode_access(
        SECRET,
        user_id="u1",
        username="a",
        role="user",
        jti="j",
        ttl=timedelta(minutes=5),
    )
    with pytest.raises(InvalidTokenError):
        jwt_tokens.decode(SECRET + "-different", t, expected_type="access")
    with pytest.raises(InvalidTokenError):
        jwt_tokens.decode(SECRET, t, expected_type="refresh")  # wrong type

    expired = jwt_tokens.encode_refresh(
        SECRET, user_id="u1", jti="j", ttl=timedelta(seconds=-1)
    )
    with pytest.raises(InvalidTokenError):
        jwt_tokens.decode(SECRET, expired, expected_type="refresh")


# ── AuthService ─────────────────────────────────────────────────────
@pytest.fixture
def svc(tmp_path) -> AuthService:
    return AuthService(
        storage=LocalAuthStorage(db_path=tmp_path / "users.db"),
        secret_provider=lambda: SECRET,
        access_ttl=timedelta(minutes=15),
        refresh_ttl=timedelta(days=7),
    )


async def test_first_user_is_admin_rest_are_users(svc):
    assert (await svc.register("alice", "password123")).user.role == "admin"
    assert (await svc.register("bob", "password123")).user.role == "user"


async def test_duplicate_username_is_rejected_case_insensitively(svc):
    await svc.register("alice", "password123")
    with pytest.raises(UsernameTakenError):
        await svc.register("ALICE", "password123")


async def test_weak_password_and_short_username_rejected(svc):
    with pytest.raises(WeakPasswordError):
        await svc.register("alice", "short")
    with pytest.raises(WeakPasswordError):
        await svc.register("ab", "password123")


async def test_login_wrong_password_and_unknown_user(svc):
    await svc.register("alice", "password123")
    with pytest.raises(InvalidCredentialsError):
        await svc.login("alice", "nope")
    with pytest.raises(InvalidCredentialsError):
        await svc.login("ghost", "password123")


async def test_disabled_user_cannot_login_or_use_access_token(svc):
    res = await svc.register("alice", "password123")
    await svc.storage.set_user_disabled(res.user.id, True)
    with pytest.raises(InvalidCredentialsError):
        await svc.login("alice", "password123")
    with pytest.raises(InvalidTokenError):
        await svc.user_from_access_token(res.tokens.access_token)


async def test_refresh_rotates_and_old_token_is_dead(svc):
    res = await svc.register("alice", "password123")
    pair2 = await svc.refresh(res.tokens.refresh_token)
    assert pair2.access_token != res.tokens.access_token
    with pytest.raises(InvalidTokenError):
        await svc.refresh(res.tokens.refresh_token)  # reuse of rotated token
    await svc.user_from_access_token(pair2.access_token)  # new access token valid


async def test_logout_revokes_refresh_token_and_is_idempotent(svc):
    res = await svc.register("alice", "password123")
    await svc.logout(res.tokens.refresh_token)
    with pytest.raises(InvalidTokenError):
        await svc.refresh(res.tokens.refresh_token)
    await svc.logout(res.tokens.refresh_token)  # no raise
    await svc.logout("garbage")  # no raise


async def test_seed_admin_only_when_empty(svc):
    await svc.seed_admin("root", "password123")
    assert await svc.storage.count_users() == 1
    await svc.seed_admin("root2", "password123")  # ignored — table not empty
    assert await svc.storage.count_users() == 1
    assert (await svc.login("root", "password123")).user.role == "admin"


# ── /api/auth routes (no middleware — status codes only) ─────────────
@pytest.fixture
def client(tmp_path) -> TestClient:
    from krutrim_agent_backend.api.auth_routes import router

    app = FastAPI()
    app.state.auth = AuthService(
        storage=LocalAuthStorage(db_path=tmp_path / "users.db"),
        secret_provider=lambda: SECRET,
    )
    app.include_router(router)
    return TestClient(app)


def test_register_then_login_then_refresh_then_logout(client):
    r = client.post(
        "/api/auth/register", json={"username": "alice", "password": "password123"}
    )
    assert r.status_code == 201
    refresh = r.json()["tokens"]["refresh_token"]

    assert (
        client.post(
            "/api/auth/login", json={"username": "alice", "password": "password123"}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": refresh}).status_code
        == 200
    )
    # the just-rotated refresh token is now dead
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": refresh}).status_code
        == 401
    )
    assert (
        client.post("/api/auth/logout", json={"refresh_token": "anything"}).status_code
        == 204
    )


def test_register_duplicate_is_409(client):
    body = {"username": "alice", "password": "password123"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_register_short_password_is_422(client):
    r = client.post("/api/auth/register", json={"username": "alice", "password": "x"})
    assert r.status_code == 422


def test_login_bad_credentials_is_401(client):
    client.post(
        "/api/auth/register", json={"username": "alice", "password": "password123"}
    )
    r = client.post("/api/auth/login", json={"username": "alice", "password": "nope"})
    assert r.status_code == 401


def test_refresh_with_garbage_is_401(client):
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": "nonsense"}).status_code
        == 401
    )


# ── /api/auth/me needs the middleware to populate request.state.user ──
def test_me_returns_the_token_user(authed_client):
    client, _ = authed_client
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role"] == "admin"


def test_me_without_token_is_401(authed_client):
    client, _ = authed_client
    client.headers.pop("Authorization")
    assert client.get("/api/auth/me").status_code == 401
