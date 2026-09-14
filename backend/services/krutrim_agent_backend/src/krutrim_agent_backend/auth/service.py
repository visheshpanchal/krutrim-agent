"""`AuthService` — the one object the FastAPI layer talks to. Ties together an
`AuthStorage` backend (`krutrim_agent_management`), argon2id hashing, and JWT
tokens.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from krutrim_agent_management import AuthStorage, UserRecord

from krutrim_agent_backend.auth import tokens
from krutrim_agent_backend.auth.errors import (
    InvalidCredentialsError,
    InvalidTokenError,
    WeakPasswordError,
)
from krutrim_agent_backend.auth.hashing import (
    hash_password,
    needs_rehash,
    verify_password,
)
from krutrim_agent_backend.auth.models import AuthResult, TokenPair, UserPublic

MIN_USERNAME_LEN = 3
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 4096


class AuthService:
    def __init__(
        self,
        *,
        storage: AuthStorage,
        secret_provider: Callable[[], str],
        access_ttl: timedelta = timedelta(minutes=30),
        refresh_ttl: timedelta = timedelta(days=14),
    ) -> None:
        self._store = storage
        self._secret_provider = secret_provider
        self._secret_cache: str | None = None
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl

    @property
    def _secret(self) -> str:
        if self._secret_cache is None:
            self._secret_cache = self._secret_provider()
        return self._secret_cache

    @property
    def storage(self) -> AuthStorage:
        return self._store

    # -- registration / login ------------------------------------------------
    async def register(
        self, username: str, password: str, email: str | None = None
    ) -> AuthResult:
        username = username.strip()
        if len(username) < MIN_USERNAME_LEN:
            raise WeakPasswordError(
                f"username must be at least {MIN_USERNAME_LEN} characters"
            )
        _check_password(password)
        role = "admin" if await self._store.count_users() == 0 else "user"
        record = await self._store.create_user(
            username=username,
            password_hash=hash_password(password),
            email=(email.strip() or None) if email else None,
            role=role,
        )
        _seed_user_config(record.id)
        return AuthResult(
            user=UserPublic.from_record(record),
            tokens=await self._issue_pair(record),
        )

    async def login(self, username: str, password: str) -> AuthResult:
        record = await self._store.get_user_by_username(username.strip())
        if (
            record is None
            or record.disabled
            or not verify_password(record.password_hash, password)
        ):
            raise InvalidCredentialsError("invalid username or password")
        if needs_rehash(record.password_hash):
            await self._store.update_password_hash(record.id, hash_password(password))
        return AuthResult(
            user=UserPublic.from_record(record),
            tokens=await self._issue_pair(record),
        )

    # -- token lifecycle ---------------------------------------------------
    async def refresh(
        self, refresh_token: str, *, user_agent: str | None = None
    ) -> TokenPair:
        claims = tokens.decode(self._secret, refresh_token, expected_type="refresh")
        if not await self._store.refresh_token_is_active(claims["jti"]):
            raise InvalidTokenError("refresh token has been revoked or has expired")
        record = await self._store.get_user_by_id(claims["sub"])
        if record is None or record.disabled:
            raise InvalidTokenError("account no longer active")
        await self._store.revoke_refresh_token(claims["jti"])  # rotate
        return await self._issue_pair(record, user_agent=user_agent)

    async def logout(self, refresh_token: str) -> None:
        """Revoke the refresh token. Idempotent — a garbage token is a no-op."""
        try:
            claims = tokens.decode(self._secret, refresh_token, expected_type="refresh")
        except InvalidTokenError:
            return
        await self._store.revoke_refresh_token(claims["jti"])

    async def user_from_access_token(self, access_token: str) -> UserPublic:
        claims = tokens.decode(self._secret, access_token, expected_type="access")
        record = await self._store.get_user_by_id(claims["sub"])
        if record is None or record.disabled:
            raise InvalidTokenError("account no longer active")
        return UserPublic.from_record(record)

    async def seed_admin(self, username: str, password: str) -> None:
        """Create an admin from env config iff the users table is still empty."""
        if await self._store.count_users() == 0:
            record = await self._store.create_user(
                username=username.strip(),
                password_hash=hash_password(password),
                email=None,
                role="admin",
            )
            _seed_user_config(record.id)

    # -- internals ------------------------------------------------------
    async def _issue_pair(
        self, record: UserRecord, *, user_agent: str | None = None
    ) -> TokenPair:
        refresh_jti = uuid.uuid4().hex
        access = tokens.encode_access(
            self._secret,
            user_id=record.id,
            username=record.username,
            role=record.role,
            jti=uuid.uuid4().hex,
            ttl=self._access_ttl,
        )
        refresh = tokens.encode_refresh(
            self._secret, user_id=record.id, jti=refresh_jti, ttl=self._refresh_ttl
        )
        expires_at = (datetime.now(UTC) + self._refresh_ttl).isoformat()
        await self._store.add_refresh_token(
            jti=refresh_jti,
            user_id=record.id,
            expires_at=expires_at,
            user_agent=user_agent,
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=int(self._access_ttl.total_seconds()),
        )


def _seed_user_config(user_id: str) -> None:
    """Create the new user's own `config.json` (env / default seed) so it exists
    before their first request."""
    from krutrim_agent_management.config import settings

    settings.ensure_user_config(user_id)


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise WeakPasswordError(
            f"password must be at least {MIN_PASSWORD_LEN} characters"
        )
    if len(password) > MAX_PASSWORD_LEN:
        raise WeakPasswordError("password is unreasonably long")
