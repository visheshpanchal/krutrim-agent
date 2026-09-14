"""`GET/PUT/DELETE /api/credentials` — CRUD over
`<home_root>/users/<user_id>/credentials.json`
(`krutrim_agent_management.credentials_config`). Secret fields (`api_key`,
`access_token`, `refresh_token`, `password`) are redacted on read, with a
`secrets_set` map telling the UI which are present.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.credentials_config import (
    CredentialsConfig,
    IntegrationCredential,
    credentials_store,
)

from krutrim_agent_backend.auth.middleware import current_user_id

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


@router.get("")
def get_credentials(request: Request) -> dict[str, Any]:
    return credentials_store.get(current_user_id(request)).redacted()


@router.put("/{provider}")
def put_credential(
    provider: str, credential: IntegrationCredential, request: Request
) -> dict[str, Any]:
    def _apply(cfg: CredentialsConfig) -> CredentialsConfig:
        cfg.integrations[provider] = credential
        return cfg

    return credentials_store.mutate(current_user_id(request), _apply).redacted()


@router.delete("/{provider}")
def delete_credential(provider: str, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    if provider not in credentials_store.get(user_id).integrations:
        raise HTTPException(status_code=404, detail=f"No credential for {provider!r}.")

    def _apply(cfg: CredentialsConfig) -> CredentialsConfig:
        cfg.integrations.pop(provider, None)
        return cfg

    return credentials_store.mutate(user_id, _apply).redacted()
