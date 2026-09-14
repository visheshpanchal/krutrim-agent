"""`mcp.json` store + schema (`krutrim_agent_management.mcp_config`) and the
`/api/mcp` CRUD router.

Storage only — nothing here wires MCP servers into an agent yet.
"""

from __future__ import annotations

import json
import stat
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_management import LOCAL_USER_ID
from krutrim_agent_management.json_config_store import JsonConfigStore
from krutrim_agent_management.mcp_config import McpConfig, McpServerConfig
from pydantic import ValidationError

U = LOCAL_USER_ID


def _store(tmp_path) -> JsonConfigStore[McpConfig]:
    return JsonConfigStore("mcp.json", McpConfig, lambda _uid: tmp_path)


# ── schema ────────────────────────────────────────────────────────────
def test_stdio_server_requires_command():
    with pytest.raises(ValidationError):
        McpServerConfig(transport="stdio")
    McpServerConfig(transport="stdio", command="uvx")  # ok


def test_http_server_requires_url():
    with pytest.raises(ValidationError):
        McpServerConfig(transport="http")
    McpServerConfig(transport="sse", url="https://example.test/mcp")  # ok


def test_redacted_masks_env_and_headers_but_keeps_keys():
    s = McpServerConfig(
        transport="stdio",
        command="uvx",
        env={"TOKEN": "secret", "PATH": "/x"},
        headers={"Authorization": "Bearer secret"},
    )
    red = s.redacted()
    assert red["env"] == {"TOKEN": "***", "PATH": "***"}
    assert red["headers"] == {"Authorization": "***"}


# ── store ─────────────────────────────────────────────────────────────
def test_get_on_missing_file_is_empty(tmp_path):
    assert _store(tmp_path).get(U).servers == {}


def test_mutate_writes_file_at_0600(tmp_path):
    store = _store(tmp_path)

    def _add(cfg: McpConfig) -> McpConfig:
        cfg.servers["fs"] = McpServerConfig(transport="stdio", command="uvx")
        return cfg

    store.mutate(U, _add)
    path = tmp_path / "mcp.json"
    assert json.loads(path.read_text())["servers"]["fs"]["command"] == "uvx"
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_reload_picks_up_external_write(tmp_path):
    store = _store(tmp_path)
    assert store.get(U).servers == {}
    (tmp_path / "mcp.json").write_text(
        '{"servers": {"x": {"transport": "sse", "url": "https://e.test"}}}'
    )
    assert store.reload(U).servers["x"].url == "https://e.test"


@pytest.mark.parametrize("bad", ["}{", "[]", '{"servers": 3}'])
def test_malformed_or_invalid_file_falls_back_to_empty(tmp_path, bad):
    (tmp_path / "mcp.json").write_text(bad)
    assert _store(tmp_path).get(U).servers == {}


# ── /api/mcp router ──────────────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    from krutrim_agent_backend.api.mcp_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_is_empty_then_put_then_get_reflects(client):
    assert client.get("/api/mcp").json() == {"servers": {}}

    r = client.put(
        "/api/mcp/servers/fs",
        json={"transport": "stdio", "command": "uvx", "env": {"TOKEN": "secret"}},
    )
    assert r.status_code == 200
    assert r.json()["servers"]["fs"]["env"] == {"TOKEN": "***"}  # redacted

    got = client.get("/api/mcp").json()
    assert got["servers"]["fs"]["command"] == "uvx"


def test_put_invalid_server_is_422(client):
    r = client.put("/api/mcp/servers/bad", json={"transport": "stdio"})  # no command
    assert r.status_code == 422


def test_delete_server(client):
    client.put("/api/mcp/servers/fs", json={"transport": "stdio", "command": "uvx"})
    assert client.delete("/api/mcp/servers/fs").json() == {"servers": {}}


def test_delete_unknown_server_is_404(client):
    assert client.delete("/api/mcp/servers/nope").status_code == 404
