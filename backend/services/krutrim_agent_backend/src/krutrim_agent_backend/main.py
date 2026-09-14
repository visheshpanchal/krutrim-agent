"""FastAPI entrypoint: `uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000`."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from krutrim_agent_extensions.middleware import ExtensionMiddleware
from krutrim_agent_extensions.selfcheck import run_startup_selfcheck
from krutrim_agent_management.config import settings
from loguru import logger

from krutrim_agent_backend.api.agent_instances_routes import (
    router as agent_instances_router,
)
from krutrim_agent_backend.api.agent_run import mount_agent_run_endpoint
from krutrim_agent_backend.api.agents_routes import router as agents_router
from krutrim_agent_backend.api.auth_routes import router as auth_router
from krutrim_agent_backend.api.chat_routes import router as chat_router
from krutrim_agent_backend.api.chats_routes import router as chats_router
from krutrim_agent_backend.api.credentials_routes import router as credentials_router
from krutrim_agent_backend.api.error_handlers import register_exception_handlers
from krutrim_agent_backend.api.health import router as health_router
from krutrim_agent_backend.api.mcp_routes import router as mcp_router
from krutrim_agent_backend.api.models_routes import router as models_router
from krutrim_agent_backend.api.projects_routes import router as projects_router
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_backend.api.settings_routes import (
    app_settings_router,
)
from krutrim_agent_backend.api.settings_routes import (
    router as settings_router,
)
from krutrim_agent_backend.api.status_routes import router as status_router
from krutrim_agent_backend.api.system_routes import router as system_router
from krutrim_agent_backend.auth.middleware import AuthMiddleware
from krutrim_agent_backend.auth.setup import build_auth_service
from krutrim_agent_backend.bootstrap import build_app_state, install_app_state
from krutrim_agent_backend.logging_config import configure_logging

configure_logging()

# Import for side effect: registers the session-delete hook that drops a
# session's vector index (Qdrant collection / FAISS dir) whenever its chat or
# session is deleted. See krutrim_agent_rag/cleanup.py.
import krutrim_agent_rag.cleanup  # noqa: E402, F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("Starting krutrim-agent backend")
    state = await build_app_state(settings)
    install_app_state(app, state)

    if settings.server.admin_username and settings.server.admin_password:
        await app.state.auth.seed_admin(
            settings.server.admin_username,
            settings.server.admin_password,
        )

    try:
        yield
    finally:
        logger.info("Shutting down krutrim-agent backend")
        state.sandbox_registry.close_all()


def create_app() -> FastAPI:
    # Fails CLOSED, not open: refuses to construct the app at all if
    # settings.edition == "extended" but no real RequestAuthenticator was
    # registered — see krutrim_agent_extensions/selfcheck.py.
    run_startup_selfcheck(settings)

    app = FastAPI(title="Krutrim Agent Backend", lifespan=lifespan)
    app.state.auth = build_auth_service(settings)

    # Starlette runs middleware outermost-first in REVERSE add order, so the
    # request flow is  CORS -> Auth -> Extension -> routes:
    #  * CORS outermost, so even an AuthMiddleware 401 carries CORS headers and
    #    the browser can read it.
    #  * AuthMiddleware next: rejects tokenless requests (unless auth_enabled is
    #    false) and sets request.state.user / .principal.
    #  * ExtensionMiddleware innermost: resolves request.state.principal /
    #    visible_agent_keys for edition-aware routes; a pure pass-through in
    #    community, and it leaves an already-set principal alone.
    app.add_middleware(ExtensionMiddleware)
    app.add_middleware(
        AuthMiddleware,
        auth_service=app.state.auth,
        enabled=settings.server.auth_enabled,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(agents_router)
    app.include_router(settings_router)
    app.include_router(app_settings_router)
    app.include_router(mcp_router)
    app.include_router(credentials_router)
    app.include_router(projects_router)
    app.include_router(agent_instances_router)
    app.include_router(chats_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(models_router)
    app.include_router(status_router)
    app.include_router(system_router)
    mount_agent_run_endpoint(app)
    logger.info(f"DEV_MODE: {settings.dev_mode}")
    return app


app = create_app()
