"""`AuthMiddleware` — enforces a valid access token on every request except a
small allowlist (auth endpoints, health, the API docs).

The token normally rides in the `Authorization: Bearer` header. SSE clients
(`EventSource`) cannot set headers, so a `?access_token=` query parameter is
accepted as a fallback — the header wins when both are present. This covers
the AG-UI run stream and the background-job progress stream equally.

Runs OUTSIDE `ExtensionMiddleware` (added last in `create_app`), so it sets
`request.state.user` / `request.state.principal` / `request.state.user_id`
before anything downstream reads them. When `settings.server.auth_enabled` is
false it sets `request.state.user_id = LOCAL_USER_ID` and passes through —
matches the pre-auth single-user behaviour and lets the test suite run
untouched. Route handlers read the owner id via `current_user_id(request)`.
"""

from __future__ import annotations

from krutrim_agent_extensions.contracts import Principal
from krutrim_agent_management import LOCAL_USER_ID
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from krutrim_agent_backend.auth import AuthError, AuthService


def current_user_id(request: Request) -> str:
    """The owning user id for this request — set by `AuthMiddleware`.
    `LOCAL_USER_ID` when auth is disabled or the middleware never ran (tests
    that build a bare app)."""
    return getattr(request.state, "user_id", LOCAL_USER_ID)


# Exact paths reachable with no token. `logout` is here because it
# authenticates itself — it revokes the refresh token carried in its body and
# is a harmless no-op for an unknown one, so requiring a live access token on
# top would just leave stale refresh tokens un-revoked once the access token
# expires.
_PUBLIC_PATHS = frozenset(
    {
        "/api/auth/config",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/health",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, auth_service: AuthService, enabled: bool) -> None:
        super().__init__(app)
        self._auth = auth_service
        self._enabled = enabled

    def _is_public(self, path: str) -> bool:
        return path in _PUBLIC_PATHS or path.startswith("/docs/")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if (
            not self._enabled
            or request.method == "OPTIONS"
            or self._is_public(request.url.path)
        ):
            request.state.user = None
            request.state.user_id = LOCAL_USER_ID
            return await call_next(request)

        token = _bearer_token(request.headers.get("Authorization")) or _query_token(
            request
        )
        if not token:
            return _unauthorized("missing bearer token")
        try:
            user = await self._auth.user_from_access_token(token)
        except AuthError as exc:
            return _unauthorized(str(exc))

        request.state.user = user
        request.state.principal = Principal(
            id=user.id, display_name=user.username, metadata={"role": user.role}
        )
        # Route handlers read this via `current_user_id(request)` and pass it
        # into storage / config calls explicitly.
        request.state.user_id = user.id
        return await call_next(request)


def _bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _query_token(request: Request) -> str | None:
    """`?access_token=` fallback for `EventSource`/SSE clients, which cannot
    send an `Authorization` header. Only consulted when the header is absent."""
    value = request.query_params.get("access_token")
    return value.strip() if value and value.strip() else None


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        {"detail": detail},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )
