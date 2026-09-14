"""Provider/model catalog + per-role model selection.

Two scopes of selection, same shape:

* **agent instance** — `/api/providers/agents/{agent_id}` — the model each
  role of an agent uses by default (agent settings panel).
* **session** — `/api/providers/sessions/{session_id}` — a per-conversation
  override of the above (the chat-composer model switcher).

Neither is the source of truth for *what can be picked* — that's the static
`krutrim_agents_core.providers.catalog`, exposed here as `GET /api/providers`
(providers, with `configured` reflecting which API keys are present) and
`GET /api/providers/models` (the model cards; chat-only by default). The
frontend never hardcodes either list.

`krutrim_agents_core.providers.resolver` merges profile defaults < agent
override < session override into the effective `ModelSettings` a run uses.
The graph is rebuilt per request (see `api/agent_run.py`), so a change here
takes effect on the agent's next message — no backend restart.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.config import settings as app_settings
from krutrim_agents_core.providers.catalog import (
    ModelCard,
    ProviderCard,
    is_known_model,
    list_models,
    provider_cards,
)
from krutrim_agents_core.providers.registry import (
    known_providers,
    parse_model_id,
    parse_model_settings,
    provider_available,
)
from krutrim_agents_core.providers.resolver import (
    effective_role_sources,
    resolve_models,
)
from krutrim_agents_core.registry import get_profile
from pydantic import BaseModel, Field

from krutrim_agent_backend.auth.middleware import current_user_id

router = APIRouter(prefix="/api/providers", tags=["providers"])

# ─────────────────────────────────────────────────────────────────────
#  App settings — the hot-reloadable user tier of `AppSettings` (see
#  `krutrim_agent_management.config`), persisted to `<home_root>/config.json`.
#  A `PUT` rewrites the file and swaps the live values, so the change lands on
#  the next agent turn with no restart. The server / infra tier (host, Redis,
#  Qdrant, ...) is env-only and deliberately NOT exposed here.
# ─────────────────────────────────────────────────────────────────────

app_settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── request / response models ──────────────────────────────────────────
class ModelSelection(BaseModel):
    """One role's desired model, as sent by the frontend picker.

    `model_id` is `"{provider}:{model}"` (e.g. `"openrouter:anthropic/claude-sonnet-4.5"`).
    `temperature` / `max_tokens` are optional partial overrides — omit them to
    inherit whatever the lower layer (profile default) already has. `custom`
    bypasses the catalog check, for a model id not in the static list yet."""

    model_id: str
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    custom: bool = False


class RoleSettings(BaseModel):
    role: str
    settings: dict[str, Any]
    source: Literal["session", "agent", "profile"]


class RoleSettingsList(BaseModel):
    roles: list[RoleSettings]


class ModelCatalogResponse(BaseModel):
    models: list[ModelCard]


class ProviderListResponse(BaseModel):
    providers: list[ProviderCard]


# ── helpers ────────────────────────────────────────────────────────────
def _storage(request: Request):
    return request.app.state.storage


def _selection_to_override(sel: ModelSelection) -> dict[str, Any]:
    try:
        provider, model = parse_model_id(sel.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if provider not in known_providers():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider {provider!r}. Known: {known_providers()}",
        )
    if not provider_available(provider):
        raise HTTPException(
            status_code=422,
            detail=f"Provider {provider!r} is not installed on this backend.",
        )
    if not sel.custom and not is_known_model(provider, model, kind="chat"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{provider}/{model} is not in the model catalog. "
                "Pass `custom: true` to use it anyway."
            ),
        )
    override: dict[str, Any] = {"provider": provider, "model": model}
    if sel.temperature is not None:
        override["temperature"] = sel.temperature
    if sel.max_tokens is not None:
        override["max_tokens"] = sel.max_tokens
    return override


def _validate_role(profile, role: str) -> None:
    if role not in profile.roles:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown role {role!r} for agent {profile.key!r}. Roles: {list(profile.roles)}",
        )


def _role_list(
    profile,
    *,
    user_id: str,
    agent_overrides: dict[str, Any],
    session_overrides: dict[str, Any] | None = None,
) -> RoleSettingsList:
    models = resolve_models(
        profile,
        user_id=user_id,
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )
    sources = effective_role_sources(
        profile,
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )
    return RoleSettingsList(
        roles=[
            RoleSettings(
                role=role,
                settings=models[role].model_dump(),
                source=sources[role],
            )
            for role in profile.roles
        ]
    )


async def _agent_profile(request: Request, agent_id: str):
    """The `AgentProfile` behind an agent instance; 404s if either is unknown."""
    try:
        agent = await _storage(request).get_agent(current_user_id(request), agent_id)
        return get_profile(agent.agent_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _session_agent_profile(request: Request, session_id: str):
    """`(agent, profile)` for an agent-owned session; 400 for a chat session."""
    storage = _storage(request)
    user_id = current_user_id(request)
    try:
        session = await storage.get_session(user_id, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session.owner_type != "agent":
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_id!r} is not an agent session; it has no per-role model settings.",
        )
    try:
        agent = await storage.get_agent(user_id, session.owner_id)
        return agent, get_profile(agent.agent_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── catalog ────────────────────────────────────────────────────────────
@router.get("")
def list_providers() -> ProviderListResponse:
    return ProviderListResponse(providers=provider_cards())


@router.get("/models")
def list_model_catalog(
    kind: Literal["chat", "embedding"] | None = "chat",
    provider: str | None = None,
) -> ModelCatalogResponse:
    return ModelCatalogResponse(models=list_models(kind=kind, provider=provider))


# ── agent-instance scope ───────────────────────────────────────────────
@router.get("/agents/{agent_id}")
async def get_agent_settings(agent_id: str, request: Request) -> RoleSettingsList:
    profile = await _agent_profile(request, agent_id)
    overrides = await _storage(request).read_agent_model_settings(agent_id) or {}
    return _role_list(
        profile, user_id=current_user_id(request), agent_overrides=overrides
    )


@router.put("/agents/{agent_id}/{role}")
async def set_agent_role(
    agent_id: str, role: str, selection: ModelSelection, request: Request
) -> RoleSettingsList:
    profile = await _agent_profile(request, agent_id)
    _validate_role(profile, role)
    storage = _storage(request)
    user_id = current_user_id(request)
    overrides = await storage.read_agent_model_settings(agent_id) or {}
    overrides[role] = _selection_to_override(selection)
    _ensure_parseable(profile, role, user_id=user_id, agent_overrides=overrides)
    await storage.write_agent_model_settings(agent_id, overrides)
    return _role_list(profile, user_id=user_id, agent_overrides=overrides)


@router.post("/agents/{agent_id}/{role}/reset")
async def reset_agent_role(
    agent_id: str, role: str, request: Request
) -> RoleSettingsList:
    profile = await _agent_profile(request, agent_id)
    _validate_role(profile, role)
    storage = _storage(request)
    user_id = current_user_id(request)
    overrides = await storage.read_agent_model_settings(agent_id) or {}
    overrides.pop(role, None)
    await storage.write_agent_model_settings(agent_id, overrides)
    return _role_list(profile, user_id=user_id, agent_overrides=overrides)


# ── session scope ──────────────────────────────────────────────────────
@router.get("/sessions/{session_id}")
async def get_session_settings(session_id: str, request: Request) -> RoleSettingsList:
    agent, profile = await _session_agent_profile(request, session_id)
    storage = _storage(request)
    agent_overrides = await storage.read_agent_model_settings(agent.agent_id) or {}
    session_overrides = await storage.read_model_settings(session_id) or {}
    return _role_list(
        profile,
        user_id=current_user_id(request),
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )


@router.put("/sessions/{session_id}/{role}")
async def set_session_role(
    session_id: str, role: str, selection: ModelSelection, request: Request
) -> RoleSettingsList:
    agent, profile = await _session_agent_profile(request, session_id)
    _validate_role(profile, role)
    storage = _storage(request)
    user_id = current_user_id(request)
    agent_overrides = await storage.read_agent_model_settings(agent.agent_id) or {}
    session_overrides = await storage.read_model_settings(session_id) or {}
    session_overrides[role] = _selection_to_override(selection)
    _ensure_parseable(
        profile,
        role,
        user_id=user_id,
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )
    await storage.write_model_settings(session_id, session_overrides)
    return _role_list(
        profile,
        user_id=user_id,
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )


@router.post("/sessions/{session_id}/{role}/reset")
async def reset_session_role(
    session_id: str, role: str, request: Request
) -> RoleSettingsList:
    agent, profile = await _session_agent_profile(request, session_id)
    _validate_role(profile, role)
    storage = _storage(request)
    user_id = current_user_id(request)
    agent_overrides = await storage.read_agent_model_settings(agent.agent_id) or {}
    session_overrides = await storage.read_model_settings(session_id) or {}
    session_overrides.pop(role, None)
    await storage.write_model_settings(session_id, session_overrides)
    return _role_list(
        profile,
        user_id=user_id,
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )


def _ensure_parseable(
    profile,
    role: str,
    *,
    user_id: str,
    agent_overrides: dict[str, Any],
    session_overrides: dict[str, Any] | None = None,
) -> None:
    """Fail the request (not a later run) if the merged settings don't parse."""
    try:
        models = resolve_models(
            profile,
            user_id=user_id,
            agent_overrides=agent_overrides,
            session_overrides=session_overrides,
        )
        parse_model_settings(models[role].model_dump())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ------ Settings ---------


class AppSettingField(BaseModel):
    """One hot-reloadable user-tier setting, described for the settings form.

    `type` is the runtime kind the UI builds a widget from — `boolean` →
    checkbox, `integer` / `number` → number input, `enum` → `<select>` over
    `possible_values`, `string` → text. `possible_values` is non-null only for
    an `enum`; `minimum` / `maximum` only for a number declared with a
    `ge`/`gt` / `le`/`lt` bound. `overridden` is `current_value !=
    default_value` and drives the per-key **Reset**.
    """

    type: Literal["boolean", "integer", "number", "string", "enum"]
    current_value: Any
    default_value: Any
    overridden: bool
    possible_values: list[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None


class UserSettingsPayload(BaseModel):
    """Every hot-reloadable user-tier setting as a `name -> descriptor` map, in
    the order the settings form renders them. Returned by `GET /api/settings/app`
    and by the `PUT` / `reset` endpoints."""

    settings: dict[str, AppSettingField]


class UserSettingsUpdate(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


class UserSettingsReset(BaseModel):
    # None (or omitted) resets every app setting to its built-in default.
    keys: list[str] | None = None


def _user_payload(user_id: str) -> UserSettingsPayload:
    return UserSettingsPayload(settings=app_settings.user_settings_schema(user_id))


@app_settings_router.get("/app")
def get_app_settings(request: Request) -> UserSettingsPayload:
    user_id = current_user_id(request)
    # Materialise this user's config.json on first visit (a user who registered
    # before the per-user split, or the env-seeded admin).
    app_settings.ensure_user_config(user_id)
    return _user_payload(user_id)


@app_settings_router.put("/app/user")
def update_user_settings(
    body: UserSettingsUpdate, request: Request
) -> UserSettingsPayload:
    if not body.updates:
        raise HTTPException(status_code=400, detail="No updates supplied.")
    user_id = current_user_id(request)
    try:
        # ValueError = unknown key; pydantic ValidationError (a ValueError
        # subclass) = out-of-range value. Both are the caller's fault -> 400.
        app_settings.update_user(user_id, body.updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_payload(user_id)


@app_settings_router.post("/app/user/reset")
def reset_user_settings(
    request: Request, body: UserSettingsReset | None = None
) -> UserSettingsPayload:
    user_id = current_user_id(request)
    keys = body.keys if body else None
    try:
        app_settings.reset_user(user_id, keys)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_payload(user_id)


__all__ = ["app_settings_router", "router"]
