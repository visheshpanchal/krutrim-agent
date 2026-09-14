"""`DefaultFilesystemSandbox` — the `"default"` sandbox profile.

Exposes exactly the surface an agent has today, now behind `KrutrimBackend`:

- `/workspace/…`         — this session's working dir, read-write
- `/skills/common/…`     — shared skills, read-only
- `/skills/<agent_key>/…`— this profile's skills, read-only
- `/memory/…`            — this profile's long-term memory, read-only

and nothing else. It is a thin, run-scoped wrapper around `deepagents`'
`CompositeBackend` (prefix routing, grep/glob merge) — no routing logic of its
own. `/workspace` is the `CompositeBackend` *default* (not a prefix route); the
workspace backend is wrapped in `_WorkspaceRoot` so a `/workspace/…` path is
treated as an alias for the workspace root — otherwise the prefix would become
a literal first segment (`…/workspace/workspace/report.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import BackendProtocol, SandboxBackendProtocol

from krutrim_agent_sandbox.backends.base import (
    DelegatingBackend,
    SandboxDelegatingBackend,
)
from krutrim_agent_sandbox.backends.readonly import ReadOnlyFilesystemBackend
from krutrim_agent_sandbox.paths import HarnessPaths, session_workspace_dir
from krutrim_agent_sandbox.scope import ProjectInfo


@dataclass
class SandboxBuildRequest:
    """Everything a sandbox-profile factory needs to build a backend for one
    graph build (see `krutrim_agent_sandbox.backends.profiles`)."""

    profile_key: str
    """Registered agent-profile key — names the `/skills/<key>/` and
    `/memory/` routes."""

    workspace_backend: BackendProtocol | None = None
    """The session's `/workspace` backend, already constructed (and possibly
    wrapped, e.g. for the eval trace) by the caller — normally the one
    `SandboxRegistry.get_or_create` hands out. `None` lets the sandbox build
    its own from `project_info` (or fall back to in-state storage)."""

    project_info: ProjectInfo | None = None
    """Which project/agent/session this build belongs to. Informational for
    `DefaultFilesystemSandbox`; the future policy layer reasons about it."""


def harness_routes(profile_key: str) -> dict[str, ReadOnlyFilesystemBackend]:
    """The read-only harness mounts, identical to what
    `krutrim_agents_core.builder` wired inline before this sandbox existed."""
    harness = HarnessPaths.from_settings()
    return {
        "/skills/common/": ReadOnlyFilesystemBackend(
            root_dir=harness.common_skills_dir, virtual_mode=True
        ),
        f"/skills/{profile_key}/": ReadOnlyFilesystemBackend(
            root_dir=harness.agent_skills_dir(profile_key), virtual_mode=True
        ),
        "/memory/": ReadOnlyFilesystemBackend(
            root_dir=harness.agent_memory_dir(profile_key), virtual_mode=True
        ),
    }


def _strip_workspace_prefix(path: str | None) -> str | None:
    """`/workspace`, `/workspace/`, `/workspace/x`, `workspace/x`  ->  `/`, `/`,
    `/x`, `/x`. A leading-segment match only — `/workspacefoo` and a nested
    `sub/workspace/x` are left alone."""
    if path is None:
        return None
    s = path if path.startswith("/") else "/" + path
    if s == "/workspace":
        return "/"
    if s.startswith("/workspace/"):
        return s[len("/workspace") :]  # keeps the leading slash
    return path


class _WorkspaceRoot(DelegatingBackend):
    """Aliases a leading `/workspace/…` to the workspace root before delegating.

    The agents are prompted (and the skills/scratchpad hard-code) `/workspace/…`
    paths, but the backend is already rooted at the session's workspace dir, so
    a `virtual_mode` backend would read the prefix as a literal first segment
    and nest everything one level deep (`…/workspace/workspace/report.md`).
    deepagents' `CompositeBackend` only strips prefixes it holds as explicit
    *routes*, and routing `/workspace/` back to this same backend would return
    every glob/grep hit twice (once via the default, once via the route) — so
    the normalisation is a path rewrite here instead.
    """

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return super().read(_strip_workspace_prefix(file_path), offset, limit)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000):
        return await super().aread(_strip_workspace_prefix(file_path), offset, limit)

    def write(self, file_path: str, content: str):
        return super().write(_strip_workspace_prefix(file_path), content)

    async def awrite(self, file_path: str, content: str):
        return await super().awrite(_strip_workspace_prefix(file_path), content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ):
        return super().edit(
            _strip_workspace_prefix(file_path), old_string, new_string, replace_all
        )

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ):
        return await super().aedit(
            _strip_workspace_prefix(file_path), old_string, new_string, replace_all
        )

    def delete(self, file_path: str):
        return super().delete(_strip_workspace_prefix(file_path))

    async def adelete(self, file_path: str):
        return await super().adelete(_strip_workspace_prefix(file_path))

    def ls(self, path: str):
        return super().ls(_strip_workspace_prefix(path))

    async def als(self, path: str):
        return await super().als(_strip_workspace_prefix(path))

    def glob(self, pattern: str, path: str | None = None):
        return super().glob(
            _strip_workspace_prefix(pattern), _strip_workspace_prefix(path)
        )

    async def aglob(self, pattern: str, path: str | None = None):
        return await super().aglob(
            _strip_workspace_prefix(pattern), _strip_workspace_prefix(path)
        )

    def grep(self, pattern, path=None, glob=None, *, max_count=None):
        return super().grep(
            pattern, _strip_workspace_prefix(path), glob, max_count=max_count
        )

    async def agrep(self, pattern, path=None, glob=None, *, max_count=None):
        return await super().agrep(
            pattern, _strip_workspace_prefix(path), glob, max_count=max_count
        )

    def download_files(self, paths: list[str]):
        return super().download_files([_strip_workspace_prefix(p) for p in paths])

    async def adownload_files(self, paths: list[str]):
        return await super().adownload_files(
            [_strip_workspace_prefix(p) for p in paths]
        )

    def upload_files(self, files: list[tuple[str, bytes]]):
        return super().upload_files([(_strip_workspace_prefix(p), c) for p, c in files])

    async def aupload_files(self, files: list[tuple[str, bytes]]):
        return await super().aupload_files(
            [(_strip_workspace_prefix(p), c) for p, c in files]
        )


class _WorkspaceRootSandbox(SandboxDelegatingBackend, _WorkspaceRoot):
    """`_WorkspaceRoot` over an execution-capable inner backend (the shell under
    `local-exec`). `SandboxDelegatingBackend` keeps it a `SandboxBackendProtocol`
    so `CompositeBackend.execute` still reaches the shell; `_WorkspaceRoot`
    supplies the path normalisation for the file ops. `execute` commands are
    left verbatim — the shell's cwd is already the workspace root."""


def _alias_workspace_root(inner: BackendProtocol) -> BackendProtocol:
    """Wrap `inner` so `/workspace/…` resolves to its root. Picks the
    execution-aware variant when `inner` is a shell so `execute` survives."""
    if isinstance(inner, SandboxBackendProtocol):
        return _WorkspaceRootSandbox(inner)
    return _WorkspaceRoot(inner)


def _workspace_backend(req: SandboxBuildRequest) -> BackendProtocol:
    if req.workspace_backend is not None:
        return _alias_workspace_root(req.workspace_backend)
    if req.project_info is not None:
        workspace_dir = session_workspace_dir(req.project_info.session_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return _alias_workspace_root(
            FilesystemBackend(root_dir=str(workspace_dir), virtual_mode=True)
        )
    # No workspace and no identity — compile-only callers (tests). In-state
    # storage keeps the graph runnable without touching disk; no `_WorkspaceRoot`
    # wrapper needed — a `StateBackend` key is a dict key, not a nesting path.
    return StateBackend()


class DefaultFilesystemSandbox(DelegatingBackend):
    def __init__(self, req: SandboxBuildRequest) -> None:
        self._request = req
        self._routes = harness_routes(req.profile_key)
        # `_workspace_backend` has already wrapped the workspace in
        # `_WorkspaceRoot`, so `/workspace/report.md` (via the default) and a
        # bare `report.md` both land at `<workspace_root>/report.md` — never
        # `<workspace_root>/workspace/report.md`. Staged converters, the shell
        # cwd and the file API all rely on that flat layout.
        super().__init__(
            CompositeBackend(
                default=_workspace_backend(req),
                routes=dict(self._routes),
            )
        )

    @property
    def route_prefixes(self) -> list[str]:
        """`/workspace` (the default) plus every read-only harness prefix."""
        return ["/workspace/", *self._routes]

    def describe(self) -> str:
        pi = self._request.project_info
        who = (
            f"{pi.owner_type}:{pi.owner_id} session:{pi.session_id}"
            if pi is not None
            else "no project_info"
        )
        return f"{type(self).__name__}({who}; routes={self.route_prefixes})"


class LocalExecSandbox(DefaultFilesystemSandbox, SandboxDelegatingBackend):
    """`DefaultFilesystemSandbox` plus shell execution — the `"local-exec"`
    sandbox profile. Same `/workspace` (rw) + read-only harness routing;
    `execute` delegates through the `CompositeBackend` to the workspace
    backend, which under this profile is a shell
    (`deepagents.backends.LocalShellBackend`, built by `SandboxRegistry`).

    Runs commands on the host with no isolation — opt-in only, never the
    shipped default.
    """
