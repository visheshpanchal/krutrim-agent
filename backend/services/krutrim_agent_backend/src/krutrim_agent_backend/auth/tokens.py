"""HS256 JWT encode/decode for the access + refresh pair.

Access token claims:  sub, username, role, type="access", jti, iat, exp
Refresh token claims: sub,                 type="refresh", jti, iat, exp

`jti` on the refresh token keys a row in `refresh_tokens` so it can be revoked
(logout) and rotated (each `/refresh` mints a new one and kills the old).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from krutrim_agent_backend.auth.errors import InvalidTokenError

_ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


def _now() -> datetime:
    return datetime.now(UTC)


def encode_access(
    secret: str,
    *,
    user_id: str,
    username: str,
    role: str,
    jti: str,
    ttl: timedelta,
) -> str:
    now = _now()
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "role": role,
            "type": "access",
            "jti": jti,
            "iat": now,
            "exp": now + ttl,
        },
        secret,
        algorithm=_ALGORITHM,
    )


def encode_refresh(secret: str, *, user_id: str, jti: str, ttl: timedelta) -> str:
    now = _now()
    return jwt.encode(
        {
            "sub": user_id,
            "type": "refresh",
            "jti": jti,
            "iat": now,
            "exp": now + ttl,
        },
        secret,
        algorithm=_ALGORITHM,
    )


def decode(secret: str, token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Verify signature + expiry and that `type` matches. Raises
    `InvalidTokenError` for every failure mode."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("token invalid") from exc
    if claims.get("type") != expected_type:
        raise InvalidTokenError(
            f"expected a {expected_type} token, got {claims.get('type')!r}"
        )
    if not claims.get("sub") or not claims.get("jti"):
        raise InvalidTokenError("token missing required claims")
    return claims
