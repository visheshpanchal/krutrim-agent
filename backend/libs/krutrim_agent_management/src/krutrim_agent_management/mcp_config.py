"""`mcp.json` — MCP (Model Context Protocol) server definitions.

Lives at `<home_root>/users/<user_id>/mcp.json`, managed entirely from the
app (never environment-backed). This module owns the schema and the
`mcp_store` singleton; every `mcp_store` call takes the `user_id` to act on.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from krutrim_agent_management.json_config_store import JsonConfigStore

Transport = Literal["stdio", "http", "sse"]

_REDACTED = "***"


class McpServerConfig(BaseModel):
    """One MCP server. `stdio` launches a subprocess (`command` + `args`);
    `http` / `sse` connect to a URL."""

    transport: Transport = "sse"
    enabled: bool = True
    description: str | None = None

    # stdio
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    # http / sse
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_transport_fields(self) -> McpServerConfig:
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio transport requires `command`")
        if self.transport in ("http", "sse") and not self.url:
            raise ValueError(f"{self.transport} transport requires `url`")
        return self

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["env"] = dict.fromkeys(self.env, _REDACTED)
        data["headers"] = dict.fromkeys(self.headers, _REDACTED)
        return data


class McpConfig(BaseModel):
    servers: dict[str, McpServerConfig] = Field(default_factory=dict)

    def redacted(self) -> dict[str, Any]:
        return {"servers": {n: s.redacted() for n, s in self.servers.items()}}


mcp_store: JsonConfigStore[McpConfig] = JsonConfigStore("mcp.json", McpConfig)
