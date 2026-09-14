"""`current_user_id(request)` + `AuthMiddleware` wiring.

`AuthMiddleware` puts the request's user id on `request.state.user_id`;
`current_user_id` reads it, falling back to `LOCAL_USER_ID` when the
middleware never ran or auth is disabled.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from krutrim_agent_backend.auth import AuthService
from krutrim_agent_backend.auth.middleware import AuthMiddleware, current_user_id
from krutrim_agent_management import LOCAL_USER_ID, LocalAuthStorage

SECRET = "test-secret-please-ignore-0123456789abcdef"  # >= 32 bytes for HS256


def test_current_user_id_defaults_to_local_when_unset():
    assert current_user_id(SimpleNamespace(state=SimpleNamespace())) == LOCAL_USER_ID


def test_current_user_id_reads_request_state():
    req = SimpleNamespace(state=SimpleNamespace(user_id="u-123"))
    assert current_user_id(req) == "u-123"


def _app(tmp_path, *, enabled: bool) -> tuple[FastAPI, AuthService]:
    svc = AuthService(
        storage=LocalAuthStorage(db_path=tmp_path / "users.db"),
        secret_provider=lambda: SECRET,
    )
    app = FastAPI()
    app.state.auth = svc

    @app.get("/whoami")
    def whoami(request: Request) -> dict[str, str]:
        return {"uid": current_user_id(request)}

    app.add_middleware(AuthMiddleware, auth_service=svc, enabled=enabled)
    return app, svc


async def test_middleware_sets_user_id_from_token(tmp_path):
    app, svc = _app(tmp_path, enabled=True)
    res = await svc.register("alice", "password123")
    client = TestClient(app)

    r = client.get(
        "/whoami", headers={"Authorization": f"Bearer {res.tokens.access_token}"}
    )
    assert r.status_code == 200
    assert r.json()["uid"] == res.user.id


async def test_middleware_missing_token_is_401(tmp_path):
    app, _ = _app(tmp_path, enabled=True)
    client = TestClient(app)
    assert client.get("/whoami").status_code == 401


def test_middleware_disabled_leaves_local(tmp_path):
    app, _ = _app(tmp_path, enabled=False)
    client = TestClient(app)
    r = client.get("/whoami")
    assert r.status_code == 200
    assert r.json()["uid"] == LOCAL_USER_ID
