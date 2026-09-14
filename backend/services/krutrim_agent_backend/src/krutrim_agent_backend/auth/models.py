"""Service-produced shapes for the auth layer. The persisted `UserRecord`
lives in `krutrim_agent_management`.
"""

from __future__ import annotations

from typing import Literal

from krutrim_agent_management import Role, UserRecord
from pydantic import BaseModel


class UserPublic(BaseModel):
    """The API-safe view of a user — no `password_hash`."""

    id: str
    username: str
    email: str | None
    role: Role
    disabled: bool
    created_at: str

    @classmethod
    def from_record(cls, record: UserRecord) -> UserPublic:
        return cls(
            id=record.id,
            username=record.username,
            email=record.email,
            role=record.role,
            disabled=record.disabled,
            created_at=record.created_at,
        )


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access-token lifetime, seconds


class AuthResult(BaseModel):
    user: UserPublic
    tokens: TokenPair
