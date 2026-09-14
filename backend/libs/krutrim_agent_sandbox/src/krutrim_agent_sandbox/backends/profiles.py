"""`name -> SandboxProfile` registry.

`krutrim_agents_core.builder.build_agent` resolves
`settings.default_sandbox_profile` (default `"default"`) against this to decide
which sandbox class to build for a graph. A future isolated runtime registers
its own profile here (e.g. `"vercel"`) and becomes selectable by config alone,
with no `build_agent` change.

Importing this module registers `"default"` as a side effect (same idiom as
`register_storage_backend` in `krutrim_agent_management.storage.local`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from krutrim_agent_sandbox.backends.base import KrutrimBackend
from krutrim_agent_sandbox.backends.default import (
    DefaultFilesystemSandbox,
    LocalExecSandbox,
    SandboxBuildRequest,
)


@dataclass(frozen=True)
class SandboxProfile:
    """How to build a backend for one graph. `build` takes the fully-formed
    `SandboxBuildRequest` and returns a ready `KrutrimBackend`.

    `execute` is `True` for a profile that grants the agent a shell —
    `SandboxRegistry` reads it to build a shell-capable workspace backend, and
    `build` returns a sandbox that carries that capability through its wrapper
    stack.
    """

    build: Callable[[SandboxBuildRequest], KrutrimBackend]
    execute: bool = False


_REGISTRY: dict[str, SandboxProfile] = {}


def register_sandbox_profile(name: str, profile: SandboxProfile) -> None:
    _REGISTRY[name] = profile


def get_sandbox_profile(name: str) -> SandboxProfile:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        msg = f"Unknown sandbox profile {name!r}. Registered: {known}."
        raise KeyError(msg) from None


register_sandbox_profile("default", SandboxProfile(build=DefaultFilesystemSandbox))
# Opt-in: grants the agent a shell `execute` tool over its `/workspace`, run on
# the host with no isolation. Select with KRUTRIM_AGENT_DEFAULT_SANDBOX_PROFILE
# = "local-exec". Not for shared or production hosts.
register_sandbox_profile(
    "local-exec", SandboxProfile(build=LocalExecSandbox, execute=True)
)
