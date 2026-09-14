"""Backend implementations this platform builds on `deepagents`'
`BackendProtocol`.

- `base` — `KrutrimBackend` (the marker every one descends from),
  `DelegatingBackend` (wrap-an-inner + `_observe` hook), `ReadOnlyBackend`.
- `readonly` — `ReadOnlyFilesystemBackend`, a read-only view of a host dir.
- `default` — `DefaultFilesystemSandbox`, the `"default"` sandbox profile:
  `/workspace` (rw) + harness `/skills/*` `/memory/` (ro), scoped to one run;
  and `LocalExecSandbox`, the opt-in `"local-exec"` profile that adds a host
  shell `execute` over the same routes.
- `profiles` — the `name -> SandboxProfile` registry `build_agent` resolves
  `settings.default_sandbox_profile` against.
"""

from krutrim_agent_sandbox.backends.base import (
    DelegatingBackend,
    KrutrimBackend,
    ReadOnlyBackend,
    SandboxDelegatingBackend,
)
from krutrim_agent_sandbox.backends.default import (
    DefaultFilesystemSandbox,
    LocalExecSandbox,
    SandboxBuildRequest,
    harness_routes,
)
from krutrim_agent_sandbox.backends.profiles import (
    SandboxProfile,
    get_sandbox_profile,
    register_sandbox_profile,
)
from krutrim_agent_sandbox.backends.readonly import ReadOnlyFilesystemBackend

__all__ = [
    "DefaultFilesystemSandbox",
    "DelegatingBackend",
    "KrutrimBackend",
    "LocalExecSandbox",
    "ReadOnlyBackend",
    "ReadOnlyFilesystemBackend",
    "SandboxBuildRequest",
    "SandboxDelegatingBackend",
    "SandboxProfile",
    "get_sandbox_profile",
    "harness_routes",
    "register_sandbox_profile",
]
