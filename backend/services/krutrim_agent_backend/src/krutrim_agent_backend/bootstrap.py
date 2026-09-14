"""Reusable `app.state` construction — extracted from `main.py`'s `lifespan()`
so a second FastAPI app (e.g. a separate deployment wrapping this same
platform with its own extra routes/middleware) gets the exact same startup
wiring without re-deriving it. `main.py`'s `lifespan()` is now just:

    state = await build_app_state(settings)
    install_app_state(app, state)
    ...
    state.sandbox_registry.close_all()

and that other app's own lifespan does the same two calls, then
`app.include_router(agents_router)` etc. straight from `krutrim_agent_backend.api.*`
(already plain `APIRouter`s) plus whatever routes/middleware it adds itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from krutrim_agent_management.storage_factory import create_storage
from krutrim_agent_sandbox.registry import SandboxRegistry

if TYPE_CHECKING:
    from fastapi import FastAPI
    from krutrim_agent_management.config import AppSettings
    from krutrim_agent_management.storage.base import Storage

_IMAGE_TREE = Path("/app")


def _reject_ephemeral_storage(settings: AppSettings) -> None:
    """In a container, a storage/config root under `/app` is the image's own
    tree — writes there vanish on the next rebuild (projects, users,
    `.jwt_secret`). Fail at startup, not after the data is gone."""
    if not Path("/.dockerenv").exists():
        return
    for env_name, value in (
        ("KRUTRIM_AGENT_HOME_ROOT", settings.home_root),
        ("KRUTRIM_AGENT_LOG_DIR", settings.log_dir),
    ):
        resolved = Path(value).resolve()
        if resolved == _IMAGE_TREE or _IMAGE_TREE in resolved.parents:
            raise RuntimeError(
                f"{env_name} ({resolved}) is inside the image tree /app — data "
                "would be lost on the next rebuild. Mount a volume and set "
                f"{env_name} to a path on it."
            )


@dataclass
class AppState:
    storage: Storage
    # Owner-scoped sandbox registry — resolves a session to its workspace dir
    # and hands back an in-process `FilesystemBackend` rooted there (see
    # krutrim_agent_sandbox/registry.py). Every route that needs a sandbox
    # goes through this and never constructs a backend directly.
    sandbox_registry: SandboxRegistry


async def build_app_state(settings: AppSettings) -> AppState:
    _reject_ephemeral_storage(settings)
    # config.json is per-user now (<home_root>/users/<user_id>/) and created
    # lazily — at registration and when a user first opens settings — so there
    # is nothing user-scoped to materialise at server start.
    storage = create_storage(settings)
    sandbox_registry = SandboxRegistry(store=storage)
    return AppState(
        storage=storage,
        sandbox_registry=sandbox_registry,
    )


def install_app_state(app: FastAPI, state: AppState) -> None:
    app.state.storage = state.storage
    app.state.sandbox_registry = state.sandbox_registry
