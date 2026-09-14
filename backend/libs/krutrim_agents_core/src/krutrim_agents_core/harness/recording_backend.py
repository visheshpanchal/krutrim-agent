"""`RecordingFilesystemBackend` — the backend-level half of the per-run eval trace.

`RunLoggingMiddleware` (`krutrim_agents_core.harness.run_logging`) records every
model call and every *tool* call. This wrapper records filesystem activity one
layer lower — at the backend boundary — so the transcript also covers reads and
writes issued by sub-agents or other middleware that never surface as a named
tool call, and gives eval a clean `fs_op` event stream keyed by real path.

It is a `DelegatingBackend` (`krutrim_agent_sandbox.backends.base`) whose only
addition over the base is an `_observe` override that writes an `fs_op` line
per read/mutate op. `RecordingFilesystemBackend` is not a
`SandboxBackendProtocol` (no `execute` tool for it); `RecordingSandboxBackend`
is the counterpart for a shell-capable inner backend — same recording, plus
`execute`/`aexecute` forwarded (and logged) so the `"local-exec"` profile's
`execute` tool survives the recording wrapper. `build_agent` picks the one
that matches the workspace backend it was handed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from krutrim_agent_sandbox.backends.base import (
    DelegatingBackend,
    SandboxDelegatingBackend,
)

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol

    from krutrim_agents_core.harness.runs import RunLogger


class RecordingFilesystemBackend(DelegatingBackend):
    def __init__(self, inner: BackendProtocol, run_logger: RunLogger) -> None:
        super().__init__(inner)
        self._log = run_logger

    def _observe(self, op: str, path: str | None, *, ok: bool, **extra: object) -> None:
        try:
            self._log.log(
                "fs_op",
                {"source": "sandbox_fs", "op": op, "path": path, "ok": ok, **extra},
            )
        except Exception:  # noqa: BLE001, S110 - the transcript is best-effort
            pass


class RecordingSandboxBackend(RecordingFilesystemBackend, SandboxDelegatingBackend):
    """`RecordingFilesystemBackend` for a shell-capable inner backend: the same
    `fs_op` recording, plus `execute`/`aexecute` forwarded (and logged) so the
    `"local-exec"` profile's `execute` tool survives the recording wrapper."""
