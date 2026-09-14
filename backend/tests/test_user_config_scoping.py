"""Per-user config tier: `config.json` / `mcp.json` / `credentials.json`
resolve under `<home_root>/users/<user_id>/`, addressed by an explicit
`user_id` on every call.
"""

from __future__ import annotations

from krutrim_agent_management import LOCAL_USER_ID, config
from krutrim_agent_management.config import ServerSettings, UserSettings
from krutrim_agent_management.credentials_config import (
    IntegrationCredential,
    credentials_store,
)
from krutrim_agent_management.mcp_config import McpServerConfig, mcp_store


def _settings(tmp_path) -> config.AppSettings:
    return config.AppSettings(server=ServerSettings(home_root=tmp_path))


def test_config_json_path_is_user_scoped(tmp_path):
    s = _settings(tmp_path)
    assert s.user_config_path("alice") == tmp_path / "users" / "alice" / "config.json"
    assert s.user_config_path("bob") == tmp_path / "users" / "bob" / "config.json"


def test_each_user_gets_an_independent_config(tmp_path):
    s = _settings(tmp_path)

    s.update_user("u1", {"default_model": "acme/m1"})
    s.update_user("u2", {"default_model": "acme/m2"})

    assert (tmp_path / "users" / "u1" / "config.json").exists()
    assert (tmp_path / "users" / "u2" / "config.json").exists()
    assert s.user_settings("u2").default_model == "acme/m2"
    assert s.user_settings("u1").default_model == "acme/m1"


def test_unknown_user_falls_back_to_defaults_and_writes_nothing(tmp_path):
    s = _settings(tmp_path)
    assert s.user_settings("ghost").default_model == UserSettings().default_model
    assert not (tmp_path / "users" / "ghost").exists()


def test_ensure_user_config_seeds_only_the_named_user(tmp_path):
    s = _settings(tmp_path)
    s.ensure_user_config("solo")
    assert (tmp_path / "users" / "solo" / "config.json").exists()
    assert not (tmp_path / "users" / LOCAL_USER_ID).exists()


# ── mcp.json / credentials.json ride the same per-user config dir ──────────
def test_mcp_store_is_per_user(tmp_path, monkeypatch):
    # mcp_store uses the global `settings`; point it at tmp_path.
    monkeypatch.setattr(config.settings, "_home_root", tmp_path)

    server = McpServerConfig(transport="stdio", command="echo")
    mcp_store.mutate("a", lambda c: c.model_copy(update={"servers": {"x": server}}))
    assert (tmp_path / "users" / "a" / "mcp.json").exists()

    assert mcp_store.get("b").servers == {}
    assert "x" in mcp_store.get("a").servers


def test_credentials_store_is_per_user(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "_home_root", tmp_path)

    cred = IntegrationCredential(api_key="sk-x")
    credentials_store.mutate(
        "a", lambda c: c.model_copy(update={"integrations": {"openai": cred}})
    )
    assert (tmp_path / "users" / "a" / "credentials.json").exists()
    assert credentials_store.get("b").integrations == {}
