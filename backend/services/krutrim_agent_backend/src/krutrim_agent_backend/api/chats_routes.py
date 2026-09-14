"""Chat CRUD — a lightweight, non-agentic chat thread container.

Unlike `Agent`, a `Chat`'s `project_id` is optional: a standalone chat
(`project_id=None`) behaves exactly like today's plain `POST /api/chat`
flow, with no meaningful sandbox policy (nothing to share memory with).
Moving a chat in/out of a project (`POST .../move`) is a first-class,
explicit action — unlike `Agent`, which can't move projects yet.

`GET /api/chats?project_id=<id>` lists that project's chats;
`GET /api/chats` (no `project_id`) lists standalone chats — there is
currently no single call that lists every chat regardless of project (list
project-by-project, or list standalone, matching `Storage.list_chats`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.models import Chat, SessionInfo, SharingScope
from krutrim_agent_management.storage.base import Storage
from krutrim_agents_core.providers.registry import parse_model_id
from loguru import logger
from pydantic import BaseModel

from krutrim_agent_backend.auth.middleware import current_user_id
from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL, is_known_chat_model

router = APIRouter(prefix="/api/chats", tags=["chats"])


def _storage(request: Request) -> Storage:
    return request.app.state.storage


def resolve_chat_model(model_id: str | None) -> tuple[str, str]:
    """Parse an optional `"{provider}:{model}"` id, falling back to
    `DEFAULT_CHAT_MODEL`; raises `HTTPException` if malformed or unknown."""
    if model_id is None:
        return DEFAULT_CHAT_MODEL.provider, DEFAULT_CHAT_MODEL.model
    try:
        provider, model = parse_model_id(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not is_known_chat_model(provider, model):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chat model {provider}/{model}. See GET /api/models for supported models.",
        )
    return provider, model


class CreateChatRequest(BaseModel):
    display_name: str
    project_id: str | None = None
    model_id: str | None = None


class ChatDeletedResponse(BaseModel):
    status: str
    chat_id: str


@router.post("")
async def create_chat(body: CreateChatRequest, request: Request) -> Chat:
    storage = _storage(request)
    provider, model = resolve_chat_model(body.model_id)
    try:
        chat = await storage.create_chat(
            current_user_id(request),
            body.display_name,
            provider,
            model,
            project_id=body.project_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return chat.model_dump()


@router.get("")
async def list_chats(request: Request, project_id: str | None = None) -> list[Chat]:
    chats = await _storage(request).list_chats(current_user_id(request), project_id)
    return [chat.model_dump() for chat in chats]


@router.get("/{chat_id}")
async def get_chat(chat_id: str, request: Request) -> Chat:
    try:
        chat = await _storage(request).get_chat(current_user_id(request), chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return chat.model_dump()


class UpdateChatRequest(BaseModel):
    display_name: str | None = None


@router.put("/{chat_id}")
async def update_chat(chat_id: str, body: UpdateChatRequest, request: Request) -> Chat:
    try:
        updated = await _storage(request).update_chat(
            current_user_id(request), chat_id, display_name=body.display_name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


class UpdateChatModelRequest(BaseModel):
    model_id: str
    """`"{provider}:{model}"` — see `GET /api/models` for the supported list."""


@router.put("/{chat_id}/model")
async def update_chat_model(
    chat_id: str, body: UpdateChatModelRequest, request: Request
) -> Chat:
    provider, model = resolve_chat_model(body.model_id)
    try:
        updated = await _storage(request).update_chat_model(
            current_user_id(request), chat_id, provider=provider, model=model
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, request: Request) -> ChatDeletedResponse:
    logger.info(
        "chats: deleting chat {} — cascades its sessions and their vector indexes "
        "(FAISS dir / Qdrant collection, per KRUTRIM_AGENT_VECTOR_STORE_BACKEND)",
        chat_id,
    )
    try:
        await _storage(request).delete_chat(current_user_id(request), chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "chat_id": chat_id}


class MoveChatRequest(BaseModel):
    project_id: str | None
    """The project to move this chat into, or `None` to detach it back to standalone."""


@router.post("/{chat_id}/move")
async def move_chat(chat_id: str, body: MoveChatRequest, request: Request) -> Chat:
    try:
        updated = await _storage(request).move_chat(
            current_user_id(request), chat_id, project_id=body.project_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


class ChatSandboxPolicyUpdate(BaseModel):
    """Unset (`None`) fields are left unchanged. Stored regardless of whether
    `project_id` is currently set, but only takes effect once it is — see
    `Chat`'s docstring."""

    sharing: SharingScope | None = None
    idle_timeout_seconds: int | None = None
    resource_overrides: dict[str, int] | None = None


@router.put("/{chat_id}/sandbox-policy")
async def update_chat_sandbox_policy(
    chat_id: str, body: ChatSandboxPolicyUpdate, request: Request
) -> Chat:
    try:
        updated = await _storage(request).update_chat_sandbox_policy(
            current_user_id(request),
            chat_id,
            sharing=body.sharing,
            idle_timeout_seconds=body.idle_timeout_seconds,
            resource_overrides=body.resource_overrides,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


# -- sessions (owned by this chat) ---------------------------------------
# Individual-session operations (get/rename/delete/messages/policy/embed)
# live in `sessions_routes.py`, addressed by session_id alone.


@router.post("/{chat_id}/sessions")
async def create_chat_session(chat_id: str, request: Request) -> SessionInfo:
    storage = _storage(request)
    user_id = current_user_id(request)
    try:
        await storage.get_chat(user_id, chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session = await storage.create_session(user_id, "chat", chat_id)
    return session.model_dump()


@router.get("/{chat_id}/sessions")
async def list_chat_sessions(chat_id: str, request: Request) -> list[SessionInfo]:
    storage = _storage(request)
    user_id = current_user_id(request)
    try:
        await storage.get_chat(user_id, chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    sessions = await storage.list_sessions(user_id, "chat", chat_id)
    return [session.model_dump() for session in sessions]
