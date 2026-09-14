"""
Module for managing integration credentials.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from krutrim_agent_management.json_config_store import JsonConfigStore

CredentialKind = Literal["oauth2", "api_key", "basic"]

_SECRET_FIELDS = ("api_key", "access_token", "refresh_token", "password")
_REDACTED = "***"


class IntegrationCredential(BaseModel):
    kind: CredentialKind = "api_key"
    description: str | None = None
    service_name: str | None = None

    # api_key
    api_key: str | None = None

    # oauth2
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    expires_at: str | None = None  # ISO 8601
    scopes: list[str] = Field(default_factory=list)

    # basic
    username: str | None = None
    password: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        secrets_set: dict[str, bool] = {}
        for field in _SECRET_FIELDS:
            secrets_set[field] = bool(data.get(field))
            if data.get(field):
                data[field] = _REDACTED
        data["secrets_set"] = secrets_set
        return data


class CredentialsConfig(BaseModel):
    integrations: dict[str, IntegrationCredential] = Field(default_factory=dict)

    def redacted(self) -> dict[str, Any]:
        return {
            "integrations": {
                name: cred.redacted() for name, cred in self.integrations.items()
            }
        }


credentials_store: JsonConfigStore[CredentialsConfig] = JsonConfigStore(
    "credentials.json", CredentialsConfig
)
