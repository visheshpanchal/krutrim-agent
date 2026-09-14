"""The two-tier app settings — `krutrim_agent_management.config` +
`api/settings_routes.py`'s `/api/settings/app` router.

`ServerSettings` is env-only and frozen at startup; `UserSettings` is
persisted in full to `<home_root>/users/<user_id>/config.json` (created by
`ensure_user_config(user_id)` on first use, per-user) and hot-reloaded.
`AppSettings` is the façade: bare attribute access resolves the server tier;
the user tier is addressed by id via `settings.user_settings(user_id)`.
"""

from __future__ import annotations

import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_management import LOCAL_USER_ID, config
from krutrim_agent_management.config import ServerSettings, UserSettings
from pydantic import ValidationError

USER_KEYS = set(config.USER_SETTING_KEYS)
U = LOCAL_USER_ID


def _app_settings(tmp_path) -> config.AppSettings:
    """A fully independent `AppSettings` whose user config lives under `tmp_path`."""
    return config.AppSettings(server=ServerSettings(home_root=tmp_path))


def _seed_config_file(tmp_path, content: str) -> None:
    """Write raw `content` to where `_app_settings(tmp_path)` will look for the
    `"local"` user's `config.json`."""
    path = tmp_path / "users" / LOCAL_USER_ID / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ── façade ─────────────────────────────────────────────────────────────
def test_facade_delegates_to_the_server_tier(tmp_path):
    s = _app_settings(tmp_path)

    assert s.host == s.server.host  # server-tier field
    assert s.skills_dir == s.server.skills_dir  # server-tier @property still reachable

    with pytest.raises(AttributeError):
        _ = s.definitely_not_a_setting
    # user-tier fields are NOT on the façade — they need a user id
    with pytest.raises(AttributeError):
        _ = s.default_model


def test_setattr_routes_to_the_owning_tier(tmp_path):
    s = _app_settings(tmp_path)
    # a server-tier @property that derives from a sibling field must see the patch
    s.harness_dir = tmp_path / "harness"
    assert s.server.harness_dir == tmp_path / "harness"
    assert s.prompts_root_dir == tmp_path / "harness" / "prompts"


def test_user_and_server_key_sets_are_disjoint_and_cover_the_models():
    assert set(config.SERVER_SETTING_KEYS) == set(ServerSettings.model_fields)
    assert set(config.USER_SETTING_KEYS) == set(UserSettings.model_fields)
    assert not set(config.USER_SETTING_KEYS) & set(config.SERVER_SETTING_KEYS)


# ── ensure_user_config / bootstrap ────────────────────────────────────
def test_ensure_user_config_creates_a_full_file_once(tmp_path):
    s = _app_settings(tmp_path)
    assert not s.user_config_path(U).exists()

    s.ensure_user_config(U)
    assert s.user_config_path(U).exists()
    on_disk = json.loads(s.user_config_path(U).read_text())
    assert set(on_disk) == USER_KEYS  # full, not sparse

    # idempotent: a second call does not clobber an edited file
    s.update_user(U, {"default_model": "acme/model-1"})
    s.ensure_user_config(U)
    assert (
        json.loads(s.user_config_path(U).read_text())["default_model"] == "acme/model-1"
    )


def test_existing_full_config_wins_over_env(tmp_path, monkeypatch):
    s = _app_settings(tmp_path)
    s.ensure_user_config(U)
    s.update_user(U, {"web_search_provider": "duckduckgo"})

    monkeypatch.setenv("KRUTRIM_AGENT_WEB_SEARCH_PROVIDER", "tavily")
    s.reload_user(U)
    assert s.user_settings(U).web_search_provider == "duckduckgo"  # file beats env


# ── user-tier load / fallbacks ────────────────────────────────────────
def test_missing_file_yields_env_and_defaults(tmp_path):
    s = _app_settings(tmp_path)
    assert not s.user_config_path(U).exists()
    assert s.user_settings(U).model_dump() == UserSettings().model_dump()


@pytest.mark.parametrize("bad", ["not json{", '["a", "list"]', "42", ""])
def test_malformed_config_file_falls_back_to_defaults(tmp_path, bad):
    _seed_config_file(tmp_path, bad)
    s = _app_settings(tmp_path)
    assert s.user_settings(U).default_model == UserSettings().default_model


def test_out_of_range_value_in_file_falls_back_without_raising(tmp_path):
    _seed_config_file(tmp_path, '{"context_keep_messages": -3}')
    s = _app_settings(tmp_path)
    assert s.user_settings(U).context_keep_messages == UserSettings().context_keep_messages


def test_unknown_key_in_file_is_ignored(tmp_path):
    _seed_config_file(
        tmp_path, '{"web_search_provider": "duckduckgo", "leftover_key": 1}'
    )
    s = _app_settings(tmp_path)
    assert s.user_settings(U).web_search_provider == "duckduckgo"


# ── update_user ──────────────────────────────────────────────────────
def test_update_user_persists_full_and_swaps_live_value(tmp_path):
    s = _app_settings(tmp_path)
    s.update_user(U, {"default_model": "acme/model-1"})

    on_disk = json.loads(s.user_config_path(U).read_text())
    assert set(on_disk) == USER_KEYS  # written in full
    assert on_disk["default_model"] == "acme/model-1"
    assert s.user_settings(U).default_model == "acme/model-1"
    assert "default_model" in s.user_overrides(U)


def test_update_user_rejects_unknown_key(tmp_path):
    s = _app_settings(tmp_path)
    with pytest.raises(ValueError, match="Unknown user setting"):
        s.update_user(U, {"host": "1.2.3.4"})
    assert not s.user_config_path(U).exists()


def test_update_user_rejects_out_of_range_and_leaves_file_untouched(tmp_path):
    s = _app_settings(tmp_path)
    s.update_user(U, {"cross_agent_call_timeout_seconds": 30})
    before = s.user_config_path(U).read_text()

    with pytest.raises(ValidationError):
        s.update_user(U, {"cross_agent_call_timeout_seconds": 0})  # ge=1

    assert s.user_config_path(U).read_text() == before
    assert s.user_settings(U).cross_agent_call_timeout_seconds == 30


def test_update_user_merges_with_existing_overrides(tmp_path):
    s = _app_settings(tmp_path)
    s.update_user(U, {"default_model": "acme/model-1"})
    s.update_user(U, {"rag_injection_enabled": True})
    assert s.user_settings(U).default_model == "acme/model-1"
    assert s.user_settings(U).rag_injection_enabled is True


# ── reset_user ──────────────────────────────────────────────────────
def test_reset_user_rewrites_named_keys_to_default(tmp_path):
    s = _app_settings(tmp_path)
    s.update_user(U, {"rag_injection_enabled": True, "default_model": "acme/model-1"})

    s.reset_user(U, ["rag_injection_enabled"])
    assert (
        s.user_settings(U).rag_injection_enabled
        == s.user_defaults()["rag_injection_enabled"]
    )
    assert s.user_settings(U).default_model == "acme/model-1"
    assert "rag_injection_enabled" not in s.user_overrides(U)


def test_reset_user_all_restores_pure_defaults(tmp_path):
    s = _app_settings(tmp_path)
    s.update_user(U, {"rag_injection_enabled": True, "default_model": "acme/model-1"})

    s.reset_user(U)
    assert s.user_settings(U).model_dump() == s.user_defaults()
    assert s.user_overrides(U) == []


# ── user_settings_schema (the settings-form descriptor) ──────────────
def test_user_settings_schema_describes_every_field(tmp_path):
    s = _app_settings(tmp_path)
    s.reset_user(U)  # pin the file to built-in defaults so current_value is env-independent
    schema = s.user_settings_schema(U)
    assert set(schema) == USER_KEYS

    strat = schema["retrieval_strategy"]
    assert strat["type"] == "enum"
    assert strat["possible_values"] == ["vector_only", "hybrid"]
    assert strat["current_value"] == "vector_only"
    assert strat["default_value"] == "vector_only"
    assert strat["overridden"] is False

    keep = schema["context_keep_messages"]
    assert keep["type"] == "integer"
    assert keep["minimum"] == 1
    assert keep["possible_values"] is None

    timeout = schema["cross_agent_call_timeout_seconds"]
    assert (timeout["minimum"], timeout["maximum"]) == (1, 3600)

    assert schema["rag_injection_enabled"]["type"] == "boolean"
    assert schema["default_model"]["type"] == "string"


def test_user_settings_schema_flags_overrides(tmp_path):
    s = _app_settings(tmp_path)
    s.update_user(U, {"retrieval_strategy": "hybrid"})

    strat = s.user_settings_schema(U)["retrieval_strategy"]
    assert strat["current_value"] == "hybrid"
    assert strat["default_value"] == "vector_only"
    assert strat["overridden"] is True


def test_reset_user_rejects_unknown_key(tmp_path):
    s = _app_settings(tmp_path)
    with pytest.raises(ValueError):
        s.reset_user(U, ["not_a_key"])


# ── hot reload ─────────────────────────────────────────────────────
def test_user_settings_reload_on_external_write(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_STAT_THROTTLE_SECONDS", 0.0)
    s = _app_settings(tmp_path)
    changed = s.user_settings(U).default_model + "-changed"

    path = s.user_config_path(U)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"default_model": changed}))
    future = time.time_ns() + 5_000_000_000  # distinct mtime on coarse filesystems
    os.utime(path, ns=(future, future))

    assert s.user_settings(U).default_model == changed


def test_reload_is_throttled_between_stat_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_STAT_THROTTLE_SECONDS", 1_000.0)
    s = _app_settings(tmp_path)
    before = s.user_settings(U).default_model  # records the stat-check timestamp
    changed = before + "-changed"

    _seed_config_file(tmp_path, json.dumps({"default_model": changed}))
    assert s.user_settings(U).default_model == before  # within the throttle window
    assert s.reload_user(U).default_model == changed  # explicit reload sees it


# ── /api/settings/app router ──────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    from krutrim_agent_backend.api.settings_routes import app_settings_router

    app = FastAPI()
    app.include_router(app_settings_router)
    return TestClient(app)


def test_get_app_settings_returns_user_tier_only(client):
    body = client.get("/api/settings/app").json()
    fields = body["settings"]
    assert fields["default_model"]["type"] == "string"
    assert fields["default_model"]["current_value"]
    assert fields["retrieval_strategy"]["type"] == "enum"
    assert fields["retrieval_strategy"]["possible_values"] == ["vector_only", "hybrid"]
    assert "values" not in body and "server" not in body


def test_put_user_setting_persists_and_get_reflects_it(client):
    r = client.put(
        "/api/settings/app/user",
        json={"updates": {"web_search_provider": "duckduckgo"}},
    )
    assert r.status_code == 200
    field = r.json()["settings"]["web_search_provider"]
    assert field["current_value"] == "duckduckgo"
    assert field["overridden"] is True

    got = client.get("/api/settings/app").json()
    assert got["settings"]["web_search_provider"]["current_value"] == "duckduckgo"


def test_put_user_rejects_unknown_key(client):
    r = client.put("/api/settings/app/user", json={"updates": {"host": "1.2.3.4"}})
    assert r.status_code == 400


def test_put_user_rejects_out_of_range_value(client):
    r = client.put(
        "/api/settings/app/user", json={"updates": {"context_keep_messages": 0}}
    )
    assert r.status_code == 400


def test_put_user_rejects_empty_body(client):
    r = client.put("/api/settings/app/user", json={"updates": {}})
    assert r.status_code == 400


def test_reset_user_endpoint(client):
    client.put(
        "/api/settings/app/user", json={"updates": {"rag_injection_enabled": True}}
    )
    r = client.post(
        "/api/settings/app/user/reset", json={"keys": ["rag_injection_enabled"]}
    )
    assert r.status_code == 200
    assert r.json()["settings"]["rag_injection_enabled"]["overridden"] is False
