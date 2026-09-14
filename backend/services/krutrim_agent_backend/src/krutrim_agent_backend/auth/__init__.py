"""Local username/password auth: argon2id hashing, HS256 JWT access/refresh
tokens, over the `krutrim_agent_management.AuthStorage` contract. `setup.py`
wires `AuthService` to `AppSettings`; `middleware.py` enforces a Bearer token
on every route outside the allowlist.
"""

from krutrim_agent_management import EmailTakenError, UsernameTakenError

from krutrim_agent_backend.auth.errors import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    WeakPasswordError,
)
from krutrim_agent_backend.auth.models import AuthResult, TokenPair, UserPublic
from krutrim_agent_backend.auth.service import AuthService

__all__ = [
    "AuthError",
    "AuthResult",
    "AuthService",
    "EmailTakenError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "TokenPair",
    "UserPublic",
    "UsernameTakenError",
    "WeakPasswordError",
]
