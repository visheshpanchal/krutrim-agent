"""Storage-agnostic contract for the auth user store — `users` and
`refresh_tokens`. `LocalAuthStorage` (`local.py`) is the only implementation
today. `krutrim_agent_backend.auth.AuthService` is the sole caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from krutrim_agent_management.models import Role, UserRecord


class UsernameTakenError(Exception):
    """`create_user` was given a username another account already uses."""


class EmailTakenError(Exception):
    """`create_user` was given an email another account already uses."""


class AuthStorage(ABC):
    """Persists auth users and their refresh-token records. Usernames and
    emails are unique, case-insensitively."""

    # -- users ---------------------------------------------------------------

    @abstractmethod
    async def count_users(self) -> int: ...

    @abstractmethod
    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        email: str | None,
        role: Role,
    ) -> UserRecord:
        """Raises `UsernameTakenError` / `EmailTakenError` on a unique clash."""

    @abstractmethod
    async def get_user_by_username(self, username: str) -> UserRecord | None:
        """Case-insensitive. `None` if unknown."""

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserRecord | None:
        """`None` if unknown."""

    @abstractmethod
    async def update_password_hash(self, user_id: str, password_hash: str) -> None: ...

    @abstractmethod
    async def set_user_disabled(self, user_id: str, disabled: bool) -> None: ...

    # -- refresh tokens ----------------------------------------------------

    @abstractmethod
    async def add_refresh_token(
        self, *, jti: str, user_id: str, expires_at: str, user_agent: str | None
    ) -> None: ...

    @abstractmethod
    async def refresh_token_is_active(self, jti: str) -> bool:
        """`True` only if the `jti` exists, is not revoked, and has not expired."""

    @abstractmethod
    async def revoke_refresh_token(self, jti: str) -> None:
        """No-op if the `jti` is unknown."""

    @abstractmethod
    async def revoke_all_refresh_tokens(self, user_id: str) -> None: ...

    @abstractmethod
    async def purge_expired_refresh_tokens(self) -> int:
        """Delete every expired row; returns the number removed."""
