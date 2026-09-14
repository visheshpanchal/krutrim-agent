"""Auth failure taxonomy. The FastAPI layer maps each to a status code.

`UsernameTakenError` / `EmailTakenError` are raised by the storage layer
(`krutrim_agent_management`) and re-exported from `krutrim_agent_backend.auth`.
"""

from __future__ import annotations


class AuthError(Exception):
    """Base for every expected auth failure — always caller input, never a bug."""


class InvalidCredentialsError(AuthError):
    """Username unknown, password wrong, or the account is disabled. -> 401"""


class InvalidTokenError(AuthError):
    """Token missing, malformed, expired, wrong type, or revoked. -> 401"""


class WeakPasswordError(AuthError):
    """Password fails the minimum policy. -> 422"""
