"""Module defining the base backend classes for Krutrim Agent Sandboxes."""

from __future__ import annotations

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)

_READONLY_DENIED = "Permission denied: this path is read-only."


class KrutrimBackend(BackendProtocol):
    """Marker base for every backend built by this platform."""


class DelegatingBackend(KrutrimBackend):
    """Forward every `BackendProtocol` op to `inner`, with an `_observe` hook.

    `_observe(op, path, *, ok, **extra)` fires after each `read`/`write`/
    `edit`/`delete`/`upload` (pure listings — `ls`/`grep`/`glob`/`download` —
    are forwarded untouched). Default is a no-op; override to record, meter,
    audit, ...
    """

    def __init__(self, inner: BackendProtocol) -> None:
        self._inner = inner

    # -- hook -----------------------------------------------------------

    def _observe(self, op: str, path: str | None, *, ok: bool, **extra: object) -> None:
        """No-op by default."""

    # -- listings / searches (delegated, not observed) ----------------

    def ls(self, path: str) -> LsResult:
        return self._inner.ls(path)

    async def als(self, path: str) -> LsResult:
        return await self._inner.als(path)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return self._inner.grep(pattern, path, glob, max_count=max_count)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return await self._inner.agrep(pattern, path, glob, max_count=max_count)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return self._inner.glob(pattern, path)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return await self._inner.aglob(pattern, path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._inner.download_files(paths)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await self._inner.adownload_files(paths)

    # -- reads (delegated + observed) --------------------------------

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        result = self._inner.read(file_path, offset, limit)
        self._observe("read", file_path, ok=result.error is None)
        return result

    async def aread(
        self, file_path: str, offset: int = 0, limit: int = 2000
    ) -> ReadResult:
        result = await self._inner.aread(file_path, offset, limit)
        self._observe("read", file_path, ok=result.error is None)
        return result

    # -- mutations (delegated + observed) ---------------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        result = self._inner.write(file_path, content)
        self._observe("write", file_path, ok=result.error is None, bytes=len(content))
        return result

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        result = await self._inner.awrite(file_path, content)
        self._observe("write", file_path, ok=result.error is None, bytes=len(content))
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = self._inner.edit(file_path, old_string, new_string, replace_all)
        self._observe("edit", file_path, ok=result.error is None)
        return result

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = await self._inner.aedit(file_path, old_string, new_string, replace_all)
        self._observe("edit", file_path, ok=result.error is None)
        return result

    def delete(self, file_path: str) -> DeleteResult:
        result = self._inner.delete(file_path)
        self._observe("delete", file_path, ok=result.error is None)
        return result

    async def adelete(self, file_path: str) -> DeleteResult:
        result = await self._inner.adelete(file_path)
        self._observe("delete", file_path, ok=result.error is None)
        return result

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        result = self._inner.upload_files(files)
        for (path, content), resp in zip(files, result, strict=False):
            self._observe("upload", path, ok=resp.error is None, bytes=len(content))
        return result

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        result = await self._inner.aupload_files(files)
        for (path, content), resp in zip(files, result, strict=False):
            self._observe("upload", path, ok=resp.error is None, bytes=len(content))
        return result


class SandboxDelegatingBackend(DelegatingBackend, SandboxBackendProtocol):
    """A `DelegatingBackend` whose inner backend can also run shell commands.

    `deepagents`' `supports_execution` looks for `SandboxBackendProtocol` in
    the backend's MRO before offering the `execute` tool; a plain
    `DelegatingBackend` fails that check even when its inner backend is a
    shell. This subclass passes it and forwards `execute`/`aexecute` to the
    inner backend, routing each through `_observe` like the file ops.

    Only construct this over an inner backend that is itself execution-capable
    (`execute` on a filesystem-only inner raises `AttributeError`).
    """

    @property
    def id(self) -> str:
        inner_id = getattr(self._inner, "id", None)
        return inner_id if isinstance(inner_id, str) else type(self).__name__

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        result = self._inner.execute(command, timeout=timeout)
        self._observe(
            "execute",
            None,
            ok=result.exit_code == 0,
            command=command,
            exit_code=result.exit_code,
        )
        return result

    async def aexecute(
        self,
        command: str,
        *,
        # ASYNC109: `timeout` is forwarded to the inner backend's own
        # implementation, not an asyncio.timeout() contract.
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> ExecuteResponse:
        result = await self._inner.aexecute(command, timeout=timeout)
        self._observe(
            "execute",
            None,
            ok=result.exit_code == 0,
            command=command,
            exit_code=result.exit_code,
        )
        return result


class ReadOnlyBackend(DelegatingBackend):
    """Wrap `inner` and refuse every mutation; reads/listings pass through.

    Enforced at the backend (not via `deepagents` `permissions` middleware) so
    it can't be bypassed by any tool — the same reason
    `krutrim_agents_core.harness.readonly_backend` needed it.
    """

    def __init__(
        self, inner: BackendProtocol, *, denied_message: str = _READONLY_DENIED
    ) -> None:
        super().__init__(inner)
        self._denied = denied_message

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=self._denied)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=self._denied)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=self._denied)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=self._denied)

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=self._denied)

    async def adelete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=self._denied)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error=self._denied) for p, _ in files]

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error=self._denied) for p, _ in files]
