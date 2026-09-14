"""`ReadOnlyFilesystemBackend` — a read-only view of a host directory.

Used to mount `harness/skills/` and `harness/memory/` into an agent sandbox
(see `krutrim_agent_sandbox.backends.default`). Read-only enforcement lives at
the backend, not in `deepagents`' `permissions` middleware, because the
`execute` tool bypasses tool-level permission checks entirely — so a
mutation blocked here can't be bypassed by any tool.

Re-parented onto `ReadOnlyBackend` (was a direct `FilesystemBackend`
subclass); the ctor is unchanged so existing callers keep working.
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend

from krutrim_agent_sandbox.backends.base import ReadOnlyBackend

_HARNESS_DENIED = "Permission denied: this path is a read-only harness directory."


class ReadOnlyFilesystemBackend(ReadOnlyBackend):
    def __init__(
        self,
        root_dir: str | Path | None = None,
        virtual_mode: bool = True,
        max_file_size_mb: int = 10,
        *,
        denied_message: str = _HARNESS_DENIED,
    ) -> None:
        super().__init__(
            FilesystemBackend(
                root_dir=root_dir,
                virtual_mode=virtual_mode,
                max_file_size_mb=max_file_size_mb,
            ),
            denied_message=denied_message,
        )
