"""`credentials.json` store + schema
(`krutrim_agent_management.credentials_config`) and the `/api/credentials`
CRUD router. Storage only — nothing consumes these yet.
"""

from __future__ import annotations

import json
import stat
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_management import LOCAL_USER_ID
from krutrim_agent_management.credentials_config import (
    CredentialsConfig,
    IntegrationCredential,
)
from krutrim_agent_management.json_config_store import JsonConfigStore


def _store(tmp_path) -> JsonConfigStore[CredentialsConfig]:
    return JsonConfigStore("credentials.json", CredentialsConfig, lambda _uid: tmp_path)


U = LOCAL_USER_ID


# ── schema ────────────────────────────────────────────────────────────
def test_redacted_masks_secrets_and_reports_which_are_set():
    cred = IntegrationCredential(
        kind="oauth2", access_token="at", refresh_token="rt", scopes=["repo"]
    )
    red = cred.redacted()
    assert red["access_token"] == "***"
    assert red["refresh_token"] == "***"
    assert red["scopes"] == ["repo"]  # not a secret
    assert red["secrets_set"] == {
        "api_key": False,
        "access_token": True,
        "refresh_token": True,
        "password": False,
    }


# ── store ─────────────────────────────────────────────────────────────
def test_get_on_missing_file_is_empty(tmp_path):
    assert _store(tmp_path).get(U).integrations == {}


def test_mutate_writes_file_at_0600(tmp_path):
    store = _store(tmp_path)

    def _add(cfg: CredentialsConfig) -> CredentialsConfig:
        cfg.integrations["github"] = IntegrationCredential(kind="api_key", api_key="k")
        return cfg

    store.mutate(U, _add)
    path = tmp_path / "credentials.json"
    assert json.loads(path.read_text())["integrations"]["github"]["api_key"] == "k"
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ── /api/credentials router ─────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    from krutrim_agent_backend.api.credentials_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_empty_then_put_then_get_redacts(client):
    assert client.get("/api/credentials").json() == {"integrations": {}}

    r = client.put(
        "/api/credentials/github",
        json={"kind": "api_key", "api_key": "ghp_secret"},
    )
    assert r.status_code == 200
    assert r.json()["integrations"]["github"]["api_key"] == "***"
    assert r.json()["integrations"]["github"]["secrets_set"]["api_key"] is True

    # the raw secret is never returned, but it IS persisted
    assert (
        client.get("/api/credentials").json()["integrations"]["github"]["api_key"]
        == "***"
    )


def test_delete_credential(client):
    client.put("/api/credentials/github", json={"kind": "api_key", "api_key": "k"})
    assert client.delete("/api/credentials/github").json() == {"integrations": {}}


def test_delete_unknown_credential_is_404(client):
    assert client.delete("/api/credentials/nope").status_code == 404
