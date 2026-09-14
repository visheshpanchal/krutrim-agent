"""`/api/auth` — register, login, token refresh (with rotation), logout
(refresh-token revocation), and `me`.

`register` / `login` / `refresh` are on the `AuthMiddleware` allowlist, so they
are reachable with no token. `me` reads `request.state.user`, which the
middleware set from the access token (so it 401s when auth is disabled — it is
meaningless without it).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.config import settings
from pydantic import BaseModel, Field

from krutrim_agent_backend.auth import (
    AuthResult,
    AuthService,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenPair,
    UsernameTakenError,
    UserPublic,
    WeakPasswordError,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    email: str | None = Field(default=None, max_length=254)


class LoginBody(BaseModel):
    username: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


def _auth(request: Request) -> AuthService:
    return request.app.state.auth


class AuthConfig(BaseModel):
    enabled: bool


@router.get("/config")
def auth_config() -> AuthConfig:
    """Public — lets the frontend decide whether to show a login gate at all."""
    return AuthConfig(enabled=settings.server.auth_enabled)


@router.post("/register", status_code=201)
async def register(body: RegisterBody, request: Request) -> AuthResult:
    try:
        return await _auth(request).register(body.username, body.password, body.email)
    except (UsernameTakenError, EmailTakenError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WeakPasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/login")
async def login(body: LoginBody, request: Request) -> AuthResult:
    try:
        return await _auth(request).login(body.username, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh(body: RefreshBody, request: Request) -> TokenPair:
    try:
        return await _auth(request).refresh(
            body.refresh_token,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout", status_code=204)
async def logout(body: RefreshBody, request: Request) -> None:
    await _auth(request).logout(body.refresh_token)


@router.get("/me")
def me(request: Request) -> UserPublic:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
