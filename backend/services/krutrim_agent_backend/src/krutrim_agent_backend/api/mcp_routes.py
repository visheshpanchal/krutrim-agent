"""`GET/PUT/DELETE /api/mcp` — CRUD over `<home_root>/users/<user_id>/mcp.json`
(`krutrim_agent_management.mcp_config`). `env` / `headers` values are redacted
on read.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.mcp_config import McpConfig, McpServerConfig, mcp_store

from krutrim_agent_backend.auth.middleware import current_user_id

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("")
def get_mcp_config(request: Request) -> dict[str, Any]:
    return mcp_store.get(current_user_id(request)).redacted()


@router.put("/servers/{name}")
def put_mcp_server(
    name: str, server: McpServerConfig, request: Request
) -> dict[str, Any]:
    def _apply(cfg: McpConfig) -> McpConfig:
        cfg.servers[name] = server
        return cfg

    return mcp_store.mutate(current_user_id(request), _apply).redacted()


@router.delete("/servers/{name}")
def delete_mcp_server(name: str, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    if name not in mcp_store.get(user_id).servers:
        raise HTTPException(status_code=404, detail=f"No MCP server {name!r}.")

    def _apply(cfg: McpConfig) -> McpConfig:
        cfg.servers.pop(name, None)
        return cfg

    return mcp_store.mutate(user_id, _apply).redacted()
