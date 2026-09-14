"""`DefaultFilesystemSandbox` + the `KrutrimBackend` / `DelegatingBackend` seam.

The default sandbox must expose exactly what the agent saw before it existed:
`/workspace` read-write, harness `/skills/*` + `/memory/` read-only, nothing
else — and it must not advertise a shell.
"""

from __future__ import annotations

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from krutrim_agent_sandbox import ProjectInfo
from krutrim_agent_sandbox.backends import (
    DefaultFilesystemSandbox,
    DelegatingBackend,
    KrutrimBackend,
    ReadOnlyFilesystemBackend,
    SandboxBuildRequest,
    get_sandbox_profile,
    harness_routes,
)


def _sandbox(tmp_path, **overrides) -> DefaultFilesystemSandbox:
    req = SandboxBuildRequest(
        profile_key="research",
        workspace_backend=FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
        **overrides,
    )
    return DefaultFilesystemSandbox(req)


def test_workspace_is_read_write(tmp_path):
    sandbox = _sandbox(tmp_path)

    assert sandbox.write("/notes.md", "hello").error is None
    read = sandbox.read("/notes.md")
    assert read.error is None
    assert read.file_data["content"] == "hello"
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "hello"


def test_workspace_prefix_is_not_a_nested_dir(tmp_path):
    """The agents/skills/scratchpad all write `/workspace/…` paths; the backend
    is already rooted at the workspace dir, so those must land flat — never a
    literal `workspace/` subdirectory (`…/workspace/workspace/report.md`)."""
    sandbox = _sandbox(tmp_path)

    for path in (
        "/workspace/report.md",
        "/workspace/.research/state.md",
        "workspace/md_export.py",  # no leading slash
        "/workspace",  # bare, resolves to the root
    ):
        if path != "/workspace":
            assert sandbox.write(path, "x").error is None, path

    # nothing created a `workspace/` folder inside the workspace root
    assert not (tmp_path / "workspace").exists()
    assert (tmp_path / "report.md").is_file()
    assert (tmp_path / ".research" / "state.md").is_file()
    assert (tmp_path / "md_export.py").is_file()

    # `/workspace/x` and a bare `/x` are the same file
    assert sandbox.read("/workspace/report.md").file_data["content"] == "x"
    assert sandbox.read("/report.md").file_data["content"] == "x"


def test_glob_does_not_double_count_workspace_files(tmp_path):
    """A `/workspace/` alias must not surface each file twice (once bare, once
    prefixed) — the reason it's a path rewrite, not a second CompositeBackend
    route pointing at the same backend."""
    sandbox = _sandbox(tmp_path)
    sandbox.write("/workspace/a.md", "one")
    sandbox.write("/workspace/sub/b.md", "two")

    matches = sorted(m["path"] for m in (sandbox.glob("**/*.md").matches or []))
    ws_matches = [m for m in matches if not m.startswith(("/skills/", "/memory/"))]
    assert ws_matches == ["/a.md", "/sub/b.md"]


def test_harness_routes_are_read_only(tmp_path):
    sandbox = _sandbox(tmp_path)

    assert sandbox.write("/skills/common/x.md", "nope").error is not None
    assert sandbox.write("/memory/x.md", "nope").error is not None
    assert sandbox.edit("/skills/common/x.md", "a", "b").error is not None
    # the route itself resolves (real harness dir), the mount just refuses writes
    assert sandbox.ls("/skills/common/").error is None


def test_route_prefixes_and_identity(tmp_path):
    sandbox = _sandbox(
        tmp_path,
        project_info=ProjectInfo(
            session_id="s1",
            owner_type="agent",
            owner_id="a1",
            project_id="p1",
            agent_key="research",
        ),
    )

    assert sandbox.route_prefixes == [
        "/workspace/",
        "/skills/common/",
        "/skills/research/",
        "/memory/",
    ]
    assert isinstance(sandbox, KrutrimBackend)
    assert isinstance(sandbox, DelegatingBackend)
    assert "session:s1" in sandbox.describe()


def test_not_a_shell_sandbox(tmp_path):
    # deepagents only offers the `execute` tool for a SandboxBackendProtocol.
    assert not isinstance(_sandbox(tmp_path), SandboxBackendProtocol)


def test_builds_without_workspace_or_identity():
    # compile-only callers: no workspace backend, no project_info -> the
    # default route falls back to an in-state backend so the graph still
    # compiles (it's only usable inside a running graph).
    from deepagents.backends import CompositeBackend, StateBackend

    sandbox = DefaultFilesystemSandbox(SandboxBuildRequest(profile_key="research"))
    assert isinstance(sandbox, KrutrimBackend)
    inner = sandbox._inner
    assert isinstance(inner, CompositeBackend)
    assert isinstance(inner.default, StateBackend)


def test_harness_routes_helper():
    routes = harness_routes("research")
    assert set(routes) == {"/skills/common/", "/skills/research/", "/memory/"}
    assert all(isinstance(b, ReadOnlyFilesystemBackend) for b in routes.values())


def test_default_profile_is_registered():
    assert get_sandbox_profile("default").build is DefaultFilesystemSandbox
    try:
        get_sandbox_profile("does-not-exist")
    except KeyError as exc:
        assert "does-not-exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for unknown profile")


# -- DelegatingBackend seam --------------------------------------------------


class _Recorder(DelegatingBackend):
    def __init__(self, inner) -> None:
        super().__init__(inner)
        self.seen: list[tuple[str, str | None, bool]] = []

    def _observe(self, op, path, *, ok, **extra):
        self.seen.append((op, path, ok))


def test_delegating_backend_forwards_and_observes(tmp_path):
    rec = _Recorder(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True))

    rec.write("/a.md", "1")
    rec.read("/a.md")
    rec.edit("/a.md", "1", "2")
    rec.delete("/a.md")
    rec.ls("/")  # listing -> forwarded, not observed

    assert [op for op, _p, _ok in rec.seen] == ["write", "read", "edit", "delete"]
    assert all(ok for _op, _p, ok in rec.seen)


async def test_delegating_backend_async_paths(tmp_path):
    rec = _Recorder(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True))

    assert (await rec.awrite("/b.md", "hi")).error is None
    assert (await rec.aread("/b.md")).file_data["content"] == "hi"
    assert [op for op, _p, _ok in rec.seen] == ["write", "read"]


def test_readonly_backend_importable_from_old_path():
    from krutrim_agents_core.harness.readonly_backend import (
        ReadOnlyFilesystemBackend as Shimmed,
    )

    assert Shimmed is ReadOnlyFilesystemBackend
