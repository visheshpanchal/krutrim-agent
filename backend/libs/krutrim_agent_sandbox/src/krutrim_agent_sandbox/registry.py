"""Owner-scoped sandbox registry — the lightweight, in-process form.

The Docker + gRPC in-sandbox runtime has been removed. Every agent run now
executes in the backend process against a deepagents `FilesystemBackend`
scoped to the session's workspace directory — no container, no isolation.
This is a deliberate placeholder; a real isolated runtime will be
reintroduced later.

Whether that backend also runs shell commands is set by the active sandbox
profile (`settings.default_sandbox_profile`): the shipped `"default"` profile
gets a plain `FilesystemBackend` (no `execute`); the opt-in `"local-exec"`
profile gets a `LocalShellBackend` — a host shell over the same workspace
dir, with no isolation, given a curated environment (`PATH`/`HOME`/locale
only, so `os.environ` secrets are not visible to the agent's shell).

`SandboxRegistry` stays as the single entry point request handlers call
before anything that needs a "sandbox": it resolves the owning session
(honouring `attached_to_session_id`) and hands back a filesystem backend
rooted at ``<home_root>/sessions/<owner_id>/workspace``. With the default
`LocalBlobStore`, that path is the exact same bytes on disk as the blob key
`Storage.read_workspace_file` / `sync_workspace_from_container` use, so RAG
and the sessions file API see the agent's writes with no sync step.

The `AttachHandle.backend` this returns is the raw ``/workspace`` backend.
`krutrim_agents_core.builder.build_agent` wraps it in a
`DefaultFilesystemSandbox` (see `krutrim_agent_sandbox.backends`) — which adds
the read-only harness routes (`/skills/*`, `/memory/`) and is the seam a
future policy-aware or non-filesystem runtime plugs into via
`settings.default_sandbox_profile`.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from deepagents.backends import LocalShellBackend
from deepagents.backends.filesystem import FilesystemBackend
from krutrim_agent_management.config import settings

from krutrim_agent_sandbox.backends import get_sandbox_profile

if TYPE_CHECKING:
    from pathlib import Path

    from krutrim_agent_management.storage.base import Storage

# Handed to the agent's shell under the "local-exec" profile: enough to find
# interpreters and CLIs, but none of the backend process's own secrets
# (KRUTRIM_AGENT_*, OPENROUTER_API_KEY, TAVILY_API_KEY, ...). A real isolated
# runtime, when it lands, replaces this with a proper environment boundary.
_SHELL_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR")
_SHELL_ENV_FALLBACK_PATH = "/usr/local/bin:/usr/bin:/bin"


def _curated_shell_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _SHELL_ENV_ALLOWLIST if key in os.environ}
    env.setdefault("PATH", _SHELL_ENV_FALLBACK_PATH)
    return env


def _build_workspace_backend(workspace_dir: Path) -> FilesystemBackend:
    """A `FilesystemBackend` rooted at `workspace_dir`, or a `LocalShellBackend`
    (same root, curated env) when the active sandbox profile grants a shell."""
    profile = get_sandbox_profile(settings.default_sandbox_profile)
    if getattr(profile, "execute", False):
        return LocalShellBackend(
            root_dir=str(workspace_dir),
            virtual_mode=True,
            env=_curated_shell_env(),
        )
    return FilesystemBackend(root_dir=str(workspace_dir), virtual_mode=True)


@dataclass
class AttachHandle:
    backend: FilesystemBackend
    owner_id: str


class SandboxRegistry:
    def __init__(self, store: Storage) -> None:
        self._store: Storage = store
        self._backends: dict[str, FilesystemBackend] = {}
        self._lock = threading.Lock()

    async def resolve_owner_id(
        self, user_id: str, session_id: str
    ) -> tuple[str, str]:
        """(1) An explicit `attached_to_session_id` wins — the session's
        sandbox actions resolve to that other session's workspace. (2)
        Otherwise the session is its own owner (isolated by default).

        `sandbox_sharing` never affects workspace identity — it only gates the
        separate cross-agent `message_agent` tool.
        """
        session = await self._store.get_session(user_id, session_id)
        if session.attached_to_session_id:
            return session.attached_to_session_id, "session"
        return session_id, "session"

    async def get_or_create(self, user_id: str, session_id: str) -> AttachHandle:
        owner_id, _ = await self.resolve_owner_id(user_id, session_id)
        workspace_dir = self._store.session_dir(owner_id) / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            backend = self._backends.get(owner_id)
            if backend is None:
                backend = _build_workspace_backend(workspace_dir)
                self._backends[owner_id] = backend
        return AttachHandle(backend=backend, owner_id=owner_id)

    async def release(self, owner_id: str) -> None:
        """No-op: the workspace is a real directory on disk, already durable."""

    async def interrupt(self, session_id: str) -> bool:
        """Nothing runs server-side to cancel in the in-process model."""
        return False

    def local_backend(self, owner_id: str) -> FilesystemBackend | None:
        return self._backends.get(owner_id)

    def close_all(self) -> None:
        with self._lock:
            self._backends.clear()
