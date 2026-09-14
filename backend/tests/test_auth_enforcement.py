"""`AuthMiddleware` — global bearer-token enforcement, the public allowlist,
the `auth_enabled` kill-switch, and cooperation with `ExtensionMiddleware`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from krutrim_agent_management.config import settings


def _app(monkeypatch, *, auth_enabled: bool) -> TestClient:
    monkeypatch.setattr(settings, "auth_enabled", auth_enabled)
    from krutrim_agent_backend.main import create_app

    return TestClient(create_app())


# ── enforcement on ─────────────────────────────────────────────────────
def test_protected_route_needs_a_token(monkeypatch):
    client = _app(monkeypatch, auth_enabled=True)
    r = client.get("/api/agents")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_bad_and_malformed_tokens_are_401(monkeypatch):
    client = _app(monkeypatch, auth_enabled=True)
    assert (
        client.get("/api/agents", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )
    assert (
        client.get("/api/agents", headers={"Authorization": "Basic x"}).status_code
        == 401
    )


@pytest.mark.parametrize("path", ["/api/health", "/openapi.json", "/docs"])
def test_allowlisted_paths_need_no_token(monkeypatch, path):
    client = _app(monkeypatch, auth_enabled=True)
    assert client.get(path).status_code == 200


def test_auth_endpoints_are_reachable_without_a_token(monkeypatch):
    client = _app(monkeypatch, auth_enabled=True)
    # reachable == handled by the route (401 for bad creds), not blocked by middleware
    r = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid username or password"


def test_logout_is_reachable_without_a_token(monkeypatch):
    client = _app(monkeypatch, auth_enabled=True)
    # self-authenticating: revokes the refresh token in its body, no-op otherwise
    r = client.post("/api/auth/logout", json={"refresh_token": "anything"})
    assert r.status_code == 204


# ── SSE query-param token fallback ─────────────────────────────────────
def test_access_token_query_param_authenticates_headerless_clients(monkeypatch):
    client = _app(monkeypatch, auth_enabled=True)
    reg = client.post(
        "/api/auth/register", json={"username": "alice", "password": "password123"}
    )
    access = reg.json()["tokens"]["access_token"]
    # `EventSource` can't send an Authorization header — the token rides in the query
    assert client.get(f"/api/agents?access_token={access}").status_code == 200
    assert client.get("/api/agents?access_token=nope").status_code == 401
    # the header still wins when both are present
    r = client.get(
        "/api/agents?access_token=nope",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200


def test_auth_config_is_public_and_reports_the_flag(monkeypatch):
    on = _app(monkeypatch, auth_enabled=True)
    assert on.get("/api/auth/config").json() == {"enabled": True}
    off = _app(monkeypatch, auth_enabled=False)
    assert off.get("/api/auth/config").json() == {"enabled": False}


def test_valid_token_passes_through(monkeypatch):
    client = _app(monkeypatch, auth_enabled=True)
    reg = client.post(
        "/api/auth/register", json={"username": "alice", "password": "password123"}
    )
    access = reg.json()["tokens"]["access_token"]
    r = client.get("/api/agents", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200


def test_principal_from_jwt_reaches_the_route(monkeypatch):
    """AuthMiddleware sets request.state.principal; ExtensionMiddleware must not
    stomp it — /api/auth/me echoes request.state.user."""
    client = _app(monkeypatch, auth_enabled=True)
    reg = client.post(
        "/api/auth/register", json={"username": "alice", "password": "password123"}
    )
    access = reg.json()["tokens"]["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


# ── kill-switch off ─────────────────────────────────────────────────
def test_disabled_auth_is_a_passthrough(monkeypatch):
    client = _app(monkeypatch, auth_enabled=False)
    assert client.get("/api/agents").status_code == 200  # no token, still fine
