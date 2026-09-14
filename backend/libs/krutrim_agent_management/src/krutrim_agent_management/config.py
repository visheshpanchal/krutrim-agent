"""Application Settings Divided into two part User Settings and Server Settings.
Server Settings are read from environment variables and .env files at process start and are frozen for the lifetime of the process.
User Settings are hot-releasable and can be changed at runtime via a settings UI. They are persisted to a per-user config.json file and re-read on change.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from threading import RLock
from time import monotonic
from types import UnionType
from typing import Any, Union, get_args, get_origin

from dotenv import load_dotenv
from krutrim_agent_utils import atomic_write_json
from loguru import logger
from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from krutrim_agent_management.config_models import (
    ContextManagementStrategy,
    RetrivalStrategy,
    SandboxFilesPolicy,
    SandboxProfileType,
)
from krutrim_agent_management.config_utils import (
    env_files,
    find_backend_root,
    get_redis_url,
)

BACKEND_ROOT = find_backend_root(Path(__file__).resolve())
ENV_FILES = env_files(BACKEND_ROOT)

# Loading all envs.
for _env_path in reversed(ENV_FILES):
    load_dotenv(_env_path)


class ServerSettings(BaseSettings):
    """Infrastructure / wiring config — environment + `.env` only, bound once
    at process start. Changing any field needs a restart (see the module
    docstring); `UserSettings` holds the hot-reloadable half.

    env_prefix: every field is read from KRUTRIM_AGENT_<FIELD> (case-
    insensitive). Fields that ALSO accept an unprefixed name (DEV_MODE,
    LANGFUSE_*, REDIS_*) do it explicitly via a default_factory / os.getenv.
    """

    model_config = SettingsConfigDict(
        env_prefix="krutrim_agent_",
        env_file=ENV_FILES,
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000

    home_root: Path = Field(default_factory=lambda: Path.home() / ".krutrim_agent")

    harness_dir: Path = BACKEND_ROOT / "harness"

    # This will define the maximum recursion depth for the graph execution.
    # If the graph is too deep, it may cause a RecursionError.
    # Adjust this value based on the complexity of your graphs.
    graph_recursion_limit: int = 100

    # Overrides `runs_dir` (default `harness/memory/runs`).
    runs_dir_override: Path | None = None

    # Storage backend registry — "local" (SQLite + filesystem) is the only implementation today
    storage_backend: str = "local"
    storage_backend_sources: list[str] = ["krutrim_agent_management.storage.local"]

    # Krutrim Sandbox Profile — the name of the sandbox profile to use for agent execution.
    # This is a server-tier setting and can be overridden on a per-agent or per-session basis. The default value is "default".
    default_sandbox_profile: SandboxProfileType = "default"

    # Agent sandbox execution policy (enforced by SandboxPolicyMiddleware on the
    # agent-run graph, see krutrim_agent_sandbox.execution_policy). Server-tier /
    # static; a per-agent / per-session override lands with a real isolated
    # sandbox_write_paths: virtual-path globs the "edit_only" mode permits.
    sandbox_files_policy: SandboxFilesPolicy = "auto"
    sandbox_write_paths: list[str] = ["/workspace/**"]
    # Shell command allow/deny lists — only consulted under "local-exec". Match
    # the leading token of each `;`/`&&`/`||`/`|`-separated segment. An empty
    # allow list permits any command not on the deny list. Advisory (a shell
    # can be told to run anything); a real boundary comes with the sandbox.
    # A non-empty allow list must include "python3" for the bundled
    # data-analysis and document-export skills to run.
    sandbox_shell_allow_commands: list[str] = []
    sandbox_shell_deny_commands: list[str] = []
    #   sandbox_shell_mode:
    #     "auto"     — a command is refused outright when it fails the allow /
    #                  deny lists or references a path outside the workspace
    #     "approval" — a command that is not on the deny list pauses for a human
    #                  approve/reject instead (deny-list hits are still refused)
    sandbox_shell_mode: str = "auto"

    # VectorStore backend registry — "faisslite" (default) or "qdrant"
    vector_store_backend: str = "faisslite"
    vector_store_backend_sources: list[str] = [
        "krutrim_agent_rag.embeddings",
        "krutrim_agent_rag.qdrant_store",
    ]

    # Qdrant connection settings — only read when vector_store_backend="qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_prefer_grpc: bool = False
    qdrant_https: bool = False
    # ":memory:" for tests/local dev without a running Qdrant server; overrides qdrant_url when set
    qdrant_location: str | None = None

    # Embedding model for RAG ingestion + query. Server-tier: it must match
    # what is already stored in the vector index, so it can't change live.
    rag_embedding_model: str = "qwen/qwen3-embedding-8b"
    # Plugin discovery list for retrieval strategies (the strategy *choice* is
    # user-tier: UserSettings.retrieval_strategy).
    retrieval_strategy_sources: list[str] = ["krutrim_agent_rag.retrieval_strategy"]

    cors_origins: list[str] = []

    # ── Logging ─────────────────────────────────────────────────────────
    # One shared config for every process (see
    # krutrim_agent_management.logging_config.configure_logging). The FastAPI
    # server writes <log_dir>/server/server.log and the Celery worker writes
    # <log_dir>/worker/worker.log — same knobs, different sink. Applied once at
    # startup, so server-tier. Overridable with the KRUTRIM_AGENT_LOG_* env vars.
    log_dir: Path = Field(default_factory=lambda data: data["home_root"] / "logs")
    log_level: str = "INFO"
    log_console_level: str = "INFO"
    log_rotation: str = "1 day"
    log_retention: str = "14 days"
    log_compression: str = ""
    log_backtrace: bool = False
    log_intercept_std: bool = True

    # celery broker/result-backend
    redis_url: str = Field(default_factory=get_redis_url)

    # dotted packages scanned for AgentProfile plugins; OSS profiles always included
    agent_profile_sources: list[str] = ["krutrim_agents.profiles"]

    # "community" or "extended"
    edition: str = "community"

    # dotted modules overriding the no-op RequestAuthenticator/AgentVisibilityPolicy/AuditSink
    extension_sources: list[str] = []

    # ── Auth ───────────────────────────────────────────────────────────
    # Master switch. When true, every route except the auth + health + docs
    # allowlist needs a valid Bearer access token (see
    # krutrim_agent_backend/auth/middleware.py). The test suite forces this
    # false.
    auth_enabled: bool = True
    # HS256 signing secret. If unset, a 64-hex secret is generated once and
    # persisted to `<home_root>/.jwt_secret` (0600).
    auth_jwt_secret: str | None = None
    auth_access_ttl_minutes: int = 30
    auth_refresh_ttl_days: int = 14
    # Optional first-boot admin seed — created only while the users table is
    # empty. KRUTRIM_AGENT_ADMIN_USERNAME / KRUTRIM_AGENT_ADMIN_PASSWORD.
    admin_username: str | None = None
    admin_password: str | None = None

    # KRUTRIM_AGENT_DEV_MODE (prefixed) wins; a bare DEV_MODE also works, read
    # here since env_prefix would otherwise hide it.
    dev_mode: bool = Field(
        default_factory=lambda: (
            os.getenv("DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        )
    )

    # Master off-switch for Langfuse tracing (KRUTRIM_AGENT_LANGFUSE_ENABLED).
    # Even in dev_mode with keys set, flip this false where the collector is
    # unreachable to stop the OTEL exporter error spam.
    langfuse_enabled: bool = True

    # Langfuse tracing, only active when dev_mode is on; unprefixed to match the SDK's own env vars
    langfuse_public_key: str | None = Field(
        default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY")
    )
    langfuse_secret_key: str | None = Field(
        default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY")
    )
    # LANGFUSE_BASE_URL takes priority (self-hosted); LANGFUSE_HOST is the older/cloud-default fallback
    langfuse_host: str | None = Field(
        default_factory=lambda: (
            os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")
        )
    )

    @model_validator(mode="after")
    def _anchor_runtime_dirs(self) -> ServerSettings:
        """`home_root` and `log_dir` follow `home_root` unless set on their
        own, so one `KRUTRIM_AGENT_HOME_ROOT` moves every runtime dir off the
        read-only image tree in a container."""
        if "log_dir" not in self.model_fields_set:
            self.log_dir = self.home_root / "logs"
        return self

    @property
    def skills_dir(self) -> Path:
        return self.harness_dir / "skills"

    @property
    def common_skills_dir(self) -> Path:
        return self.skills_dir / "common"

    def agent_skills_dir(self, agent_key: str) -> Path:
        return self.skills_dir / agent_key

    @property
    def prompts_root_dir(self) -> Path:
        return self.harness_dir / "prompts"

    def prompts_dir(self, folder_name: str) -> Path:
        return self.prompts_root_dir / folder_name

    @property
    def memory_dir(self) -> Path:
        return self.harness_dir / "memory"

    def agent_memory_dir(self, agent_key: str) -> Path:
        return self.memory_dir / agent_key

    @property
    def evals_dir(self) -> Path:
        return self.harness_dir / "evals"

    @property
    def runs_dir(self) -> Path:
        return self.runs_dir_override or (self.memory_dir / "runs")


class UserSettings(BaseSettings):
    """Behaviour knobs a user can change at runtime from the settings UI.

    Persisted in full to `<home_root>/config.json` (created at startup by
    `AppSettings.ensure_user_config`, seeded from env / `.env` / defaults) and
    re-read on change, so an edit takes effect on the next agent turn with no
    restart. Every field keeps a safe default, so a missing or partial file
    still loads.
    """

    model_config = SettingsConfigDict(
        env_prefix="krutrim_agent_",
        env_file=ENV_FILES,
        extra="ignore",
    )

    # OpenRouter model id used when nothing more specific is configured —
    # profile / agent / session overrides all layer on top (see
    # `krutrim_agents_core.providers.resolver`).
    default_model: str = "deepseek/deepseek-v4-flash-0731"

    # Automatic context management so a long turn doesn't blow the model's
    # context window (`build_context_management_middleware`):
    context_management_strategy: ContextManagementStrategy = "off"
    context_trigger_tokens: int = Field(default=120_000, ge=1)
    context_keep_messages: int = Field(default=20, ge=1)

    # max wait on a peer's turn via the cross-agent `message_agent` tool
    cross_agent_call_timeout_seconds: int = Field(default=60, ge=1, le=3600)

    # "tavily" (needs TAVILY_API_KEY, higher quality) or the zero-config default path
    web_search_provider: str = "tavily"

    # which retrieval ranking/query strategy the active vector store uses
    retrieval_strategy: RetrivalStrategy = "vector_only"

    # inject retrieved project context into the research agent's turn
    rag_injection_enabled: bool = False

    # When true, the per-run eval transcript (`RunLoggingMiddleware`) records
    # full tool-call arguments and a preview of every tool/model result, not
    # just their shapes. Off by default — turn on for eval capture.
    eval_record_full_payloads: bool = False
    # Max characters of any single result/response payload written to the eval
    # transcript when `eval_record_full_payloads` is on.
    eval_record_payload_max_chars: int = Field(default=4000, ge=1)


_SERVER_FIELDS: frozenset[str] = frozenset(ServerSettings.model_fields)
_USER_FIELDS: frozenset[str] = frozenset(UserSettings.model_fields)
SERVER_SETTING_KEYS: tuple[str, ...] = tuple(sorted(_SERVER_FIELDS))
USER_SETTING_KEYS: tuple[str, ...] = tuple(sorted(_USER_FIELDS))

# Built-in field defaults, BEFORE env / file are applied — the baseline the
# on-disk `config.json` is diffed against so it only ever stores real changes.
_PURE_USER_DEFAULTS: dict[str, Any] = {
    name: field.get_default(call_default_factory=True)
    for name, field in UserSettings.model_fields.items()
}


def _jsonify(value: Any) -> Any:
    """Enum member -> its plain value; everything else unchanged."""
    return value.value if isinstance(value, Enum) else value


def _setting_type(annotation: Any) -> tuple[str, list[Any] | None]:
    """`(type tag, enum choices | None)` for one `UserSettings` field.

    The tag — `"enum" | "boolean" | "integer" | "number" | "string"` — is what
    the settings UI builds a widget from; it never infers a type from the
    value. `X | None` is unwrapped to `X`.
    """
    if get_origin(annotation) in (Union, UnionType):
        inner = [a for a in get_args(annotation) if a is not type(None)]
        if len(inner) == 1:
            return _setting_type(inner[0])
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "enum", [_jsonify(member) for member in annotation]
    if annotation is bool:  # before int — bool is an int subclass
        return "boolean", None
    if annotation is int:
        return "integer", None
    if annotation is float:
        return "number", None
    return "string", None


def _setting_bounds(field: Any) -> tuple[float | None, float | None]:
    """Lower / upper numeric bound from a field's `Field(ge=/gt=/le=/lt=)`
    metadata; `(None, None)` when it is unbounded."""
    low: float | None = None
    high: float | None = None
    for meta in field.metadata:
        for attr in ("ge", "gt"):
            if hasattr(meta, attr):
                low = getattr(meta, attr)
        for attr in ("le", "lt"):
            if hasattr(meta, attr):
                high = getattr(meta, attr)
    return low, high


# Static descriptor per user-tier setting — runtime `type`, enum
# `possible_values`, numeric `minimum` / `maximum`, built-in `default_value`.
# `AppSettings.user_settings_schema` layers this user's `current_value` and an
# `overridden` flag on top. Definition order == the order the settings form
# renders (related knobs — `context_*`, `eval_*` — stay grouped).
_USER_FIELD_SPECS: dict[str, dict[str, Any]] = {}
for _name, _field in UserSettings.model_fields.items():
    _type, _choices = _setting_type(_field.annotation)
    _low, _high = _setting_bounds(_field)
    _USER_FIELD_SPECS[_name] = {
        "type": _type,
        "possible_values": _choices,
        "minimum": _low,
        "maximum": _high,
        "default_value": _jsonify(_PURE_USER_DEFAULTS[_name]),
    }

_USER_CONFIG_FILENAME = "config.json"
# Per-user config lives at <home_root>/users/<user_id>/.
_USERS_SUBDIR = "users"

# Built-in default OpenRouter model — the value `UserSettings.default_model`
# carries before any env / file. Profiles read this at import time for their
# static `RoleDefaults`; a user's own `default_model` still applies at
# resolve time for roles a profile declares no default for.
DEFAULT_MODEL: str = _PURE_USER_DEFAULTS["default_model"]

# Built-in default retrieval strategy. Resolved where the strategy plugin is
# selected — a process-wide plugin lookup, not a per-request path — so it is
# not user-scoped.
DEFAULT_RETRIEVAL_STRATEGY: str = _PURE_USER_DEFAULTS["retrieval_strategy"]
# Skip the mtime `stat()` if the file was checked within this many seconds —
# bounds syscall rate when a user-tier field is read in a tight loop.
_STAT_THROTTLE_SECONDS = 1.0


class AppSettings:
    """Façade over `ServerSettings` (frozen at startup) and the per-user
    `UserSettings` tier (hot-reloaded from `users/<user_id>/config.json`).

    Bare attribute access resolves the server tier only. The user tier is
    always addressed by id: `settings.user_settings(user_id)`.
    """

    def __init__(self, server: ServerSettings | None = None) -> None:
        self._server = server or ServerSettings()
        self._home_root = Path(self._server.home_root)
        self._lock = RLock()
        # User tier is per-user — config.json lives at
        # <home_root>/users/<user_id>/. Every cache is keyed by user id.
        self._user_by_uid: dict[str, UserSettings] = {}
        self._user_mtime_by_uid: dict[str, int | None] = {}
        self._user_check_by_uid: dict[str, float] = {}

    def __getattr__(self, name: str) -> Any:
        # Reached only when normal lookup misses. Bail on private names so a
        # miss during __init__ (before _server is set) can't recurse forever.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._server, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Route a field write (tests / `monkeypatch.setattr(settings, ...)`,
        # runtime tweaks) to the server tier — so a server-tier @property that
        # derives from a sibling field (`prompts_root_dir` from `harness_dir`,
        # ...) sees the change too. Private attrs stay on the façade; this is
        # inert until `_server` exists (during __init__).
        if (
            not name.startswith("_")
            and "_server" in self.__dict__
            and name in _SERVER_FIELDS
        ):
            setattr(self._server, name, value)
            return
        object.__setattr__(self, name, value)

    # ── tiers ──────────────────────────────────────────────────────────
    @property
    def server(self) -> ServerSettings:
        return self._server

    def user_settings(self, user_id: str) -> UserSettings:
        """This user's live `UserSettings` — parsed from
        `users/<user_id>/config.json`, cached, and re-read on mtime change.
        All defaults when the file is absent."""
        return self._maybe_reload_user(user_id)

    @property
    def base_home_root(self) -> Path:
        """Root of the runtime-config tree — holds `.jwt_secret` and the
        per-user `users/<id>/` subtree. Follows `set_home_root()` (tests /
        desktop) but is never user-scoped, unlike `home_root_path()`."""
        return self._home_root

    def home_dir_path(self, user_id: str) -> Path:
        """This user's runtime-config directory — `<base>/users/<user_id>/`,
        holding their `config.json`, `mcp.json`, `credentials.json`. Follows
        `set_home_root()` (tests / desktop)."""
        return self._home_root / _USERS_SUBDIR / user_id

    def user_config_path(self, user_id: str) -> Path:
        return self.home_dir_path(user_id) / _USER_CONFIG_FILENAME

    # ── user-tier load / reload ────────────────────────────────────────
    def _current_mtime(self, user_id: str) -> int | None:
        try:
            return self.user_config_path(user_id).stat().st_mtime_ns
        except OSError:
            return None

    def _read_user_file(self, user_id: str) -> dict[str, Any]:
        path = self.user_config_path(user_id)
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            logger.warning("Ignoring unreadable user config {} ({})", path, exc)
            return {}
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Ignoring malformed user config {} ({})", path, exc)
            return {}
        if not isinstance(data, dict):
            logger.warning("Ignoring user config {}: expected a JSON object", path)
            return {}
        return data

    def _build_user(self, user_id: str, data: dict[str, Any]) -> UserSettings:
        known = {k: v for k, v in data.items() if k in _USER_FIELDS}
        try:
            return UserSettings(**known)
        except ValidationError as exc:
            logger.warning(
                "Ignoring invalid values in user config {} ({})",
                self.user_config_path(user_id),
                exc,
            )
            return UserSettings()

    def _load_uid_locked(self, user_id: str) -> UserSettings:
        """(Re)read `users/<user_id>/config.json` and refresh that user's cache."""
        obj = self._build_user(user_id, self._read_user_file(user_id))
        self._user_by_uid[user_id] = obj
        self._user_mtime_by_uid[user_id] = self._current_mtime(user_id)
        self._user_check_by_uid[user_id] = monotonic()
        return obj

    def _persist_user_locked(
        self, user_id: str, effective: UserSettings
    ) -> UserSettings:
        """Write `effective` as this user's whole `config.json` and refresh
        their cache."""
        atomic_write_json(
            self.user_config_path(user_id), effective.model_dump(mode="json")
        )
        self._user_by_uid[user_id] = effective
        self._user_mtime_by_uid[user_id] = self._current_mtime(user_id)
        self._user_check_by_uid[user_id] = monotonic()
        return effective

    def _maybe_reload_user(self, user_id: str) -> UserSettings:
        now = monotonic()
        cached = self._user_by_uid.get(user_id)
        if (
            cached is not None
            and now - self._user_check_by_uid.get(user_id, 0.0) < _STAT_THROTTLE_SECONDS
        ):
            return cached
        with self._lock:
            self._user_check_by_uid[user_id] = now
            cached = self._user_by_uid.get(user_id)
            if cached is not None and self._current_mtime(
                user_id
            ) == self._user_mtime_by_uid.get(user_id):
                return cached
            return self._load_uid_locked(user_id)

    # ── public API ────────────────────────────────────────────────────
    def reload_user(self, user_id: str) -> UserSettings:
        """Force an immediate re-read of this user's `config.json`."""
        with self._lock:
            return self._load_uid_locked(user_id)

    def set_home_root(self, path: Path | str) -> None:
        """Point the config tree at a different base dir — for tests, and for a
        desktop shell using an OS app-data dir. Clears every per-user cache."""
        with self._lock:
            self._home_root = Path(path)
            self._user_by_uid.clear()
            self._user_mtime_by_uid.clear()
            self._user_check_by_uid.clear()

    def ensure_user_config(self, user_id: str) -> UserSettings:
        """Create this user's `config.json` if absent, seeded with the full
        user tier (built-in defaults folded with env / `.env`), then load it.
        Called at registration and when a user first opens settings — not at
        server start. An existing file is never rewritten here.

        Once the file exists it is authoritative for that user's tier: always
        rewritten in full, so env no longer overrides a key present in it.
        """
        with self._lock:
            if not self.user_config_path(user_id).exists():
                return self._persist_user_locked(user_id, UserSettings())
            return self._load_uid_locked(user_id)

    def user_overrides(self, user_id: str) -> list[str]:
        """User-tier keys whose effective value differs from the built-in
        default (i.e. changed via env or `config.json`) — for a "modified"
        marker in the UI."""
        dump = self.user_settings(user_id).model_dump()
        return sorted(k for k, v in dump.items() if v != _PURE_USER_DEFAULTS.get(k))

    def user_defaults(self) -> dict[str, Any]:
        """Built-in user-tier defaults (before env / file); JSON-safe."""
        return dict(_PURE_USER_DEFAULTS)

    def user_settings_schema(self, user_id: str) -> dict[str, dict[str, Any]]:
        """Every user-tier setting as `name -> descriptor`, in form-render
        order. Each descriptor is the static `_USER_FIELD_SPECS` entry —
        runtime `type`, `possible_values` (enums only), `minimum` / `maximum`
        (bounded numbers only), built-in `default_value` — plus this user's
        `current_value` and an `overridden` flag (`current_value !=
        default_value`). The settings UI renders each widget from this alone.
        """
        current = self.user_settings(user_id).model_dump(mode="json")
        schema: dict[str, dict[str, Any]] = {}
        for name, spec in _USER_FIELD_SPECS.items():
            value = current.get(name)
            schema[name] = {
                **spec,
                "current_value": value,
                "overridden": value != spec["default_value"],
            }
        return schema

    def update_user(self, user_id: str, updates: dict[str, Any]) -> UserSettings:
        """Validate `updates`, merge them into this user's `config.json`
        (rewritten in full) and swap their live `UserSettings` in memory.

        Raises `ValueError` for an unknown key and `pydantic.ValidationError`
        for an out-of-range value; the file is left untouched in both cases.
        """
        unknown = sorted(set(updates) - set(_USER_FIELDS))
        if unknown:
            raise ValueError(
                f"Unknown user setting(s): {unknown}. Known: {list(USER_SETTING_KEYS)}"
            )
        with self._lock:
            merged = {
                k: v
                for k, v in {**self._read_user_file(user_id), **updates}.items()
                if k in _USER_FIELDS
            }
            effective = UserSettings(**merged)
            return self._persist_user_locked(user_id, effective)

    def reset_user(self, user_id: str, keys: list[str] | None = None) -> UserSettings:
        """Rewrite `keys` (or every key when `None`) back to their built-in
        default in this user's `config.json`. Unknown keys raise `ValueError`.
        """
        if keys is not None:
            unknown = sorted(set(keys) - set(_USER_FIELDS))
            if unknown:
                raise ValueError(f"Unknown user setting(s): {unknown}")
        with self._lock:
            if keys is None:
                values = dict(_PURE_USER_DEFAULTS)
            else:
                reset = set(keys)
                current = {
                    k: v
                    for k, v in self._read_user_file(user_id).items()
                    if k in _USER_FIELDS
                }
                values = {
                    **UserSettings(**current).model_dump(),
                    **{k: _PURE_USER_DEFAULTS[k] for k in reset},
                }
            effective = UserSettings(**values)
            return self._persist_user_locked(user_id, effective)


settings = AppSettings()
