"""Wires `AuthService` to `AppSettings`.

`build_auth_service()` does no I/O — the `AuthStorage` schema and the JWT
secret are both resolved lazily on first use, so importing `main` never
creates `users.db` or `.jwt_secret`.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from krutrim_agent_management import create_auth_storage
from krutrim_agent_management.config import AppSettings
from krutrim_agent_utils import atomic_write_bytes
from loguru import logger

from krutrim_agent_backend.auth import AuthService

_JWT_SECRET_FILENAME = ".jwt_secret"


def resolve_jwt_secret(settings: AppSettings) -> str:
    """`server.auth_jwt_secret` if set, else a 64-hex secret persisted once to
    `<home_root>/.jwt_secret` (0600) and reused on later boots."""
    configured = settings.server.auth_jwt_secret
    if configured:
        return configured

    path = settings.base_home_root / _JWT_SECRET_FILENAME
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    except OSError as exc:  # pragma: no cover - unusual FS state
        logger.warning("Could not read {} ({}); regenerating", path, exc)

    generated = secrets.token_hex(32)
    atomic_write_bytes(path, generated.encode("utf-8"))
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover
        pass
    logger.info("Generated a new JWT signing secret at {}", path)
    return generated


def build_auth_service(settings: AppSettings) -> AuthService:
    return AuthService(
        storage=create_auth_storage(settings),
        secret_provider=lambda: resolve_jwt_secret(settings),
        access_ttl=timedelta(minutes=settings.server.auth_access_ttl_minutes),
        refresh_ttl=timedelta(days=settings.server.auth_refresh_ttl_days),
    )
