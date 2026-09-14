"""The opt-in `"local-exec"` sandbox profile: a host `LocalShellBackend`
workspace plus the `SandboxDelegatingBackend` / `LocalExecSandbox` /
`RecordingSandboxBackend` wrappers that keep `deepagents`' `execute` tool
reachable through the run-scoped stack. The shipped `"default"` profile must
stay shell-free.
"""

from __future__ import annotations

import json
import os

from deepagents.backends import LocalShellBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from deepagents.middleware.filesystem import supports_execution
from krutrim_agent_management import LOCAL_USER_ID, LocalStorage, config
from krutrim_agent_sandbox.backends import (
    DefaultFilesystemSandbox,
    LocalExecSandbox,
    SandboxBuildRequest,
    get_sandbox_profile,
)
from krutrim_agent_sandbox.registry import SandboxRegistry
from krutrim_agents_core.harness.recording_backend import (
    RecordingFilesystemBackend,
    RecordingSandboxBackend,
)
from krutrim_agents_core.harness.runs import RunLogger


def _shell(root) -> LocalShellBackend:
    return LocalShellBackend(
        root_dir=str(root),
        virtual_mode=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )


async def _agent_session(storage: LocalStorage):
    project = await storage.create_project(LOCAL_USER_ID, "P")
    agent = await storage.create_agent(
        LOCAL_USER_ID, project.project_id, "research", "A"
    )
    return await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)


# -- profile registry --------------------------------------------------------


def test_profiles_declare_execution_capability():
    assert get_sandbox_profile("default").execute is False
    assert get_sandbox_profile("local-exec").execute is True
    assert get_sandbox_profile("local-exec").build is LocalExecSandbox


# -- LocalExecSandbox ------------------------------------------------------


def test_local_exec_sandbox_supports_and_runs_execution(tmp_path):
    sandbox = get_sandbox_profile("local-exec").build(
        SandboxBuildRequest(profile_key="research", workspace_backend=_shell(tmp_path))
    )

    assert isinstance(sandbox, LocalExecSandbox)
    assert isinstance(sandbox, SandboxBackendProtocol)
    assert supports_execution(sandbox) is True

    result = sandbox.execute("echo hello-from-exec")
    assert "hello-from-exec" in result.output
    assert result.exit_code == 0

    # file routing is unchanged
    assert sandbox.write("/note.md", "hi").error is None
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "hi"
    assert sandbox.write("/skills/common/x.md", "nope").error is not None


def test_staged_script_runs_from_the_flat_workspace_root(tmp_path):
    """The document-export flow: `write_file` a helper + a source to
    `/workspace/…`, then `execute` it with paths relative to the shell's cwd
    (the workspace root). Only works if `/workspace/x` lands at `<root>/x`, not
    `<root>/workspace/x` — the shell's cwd is `<root>`."""
    sandbox = get_sandbox_profile("local-exec").build(
        SandboxBuildRequest(profile_key="research", workspace_backend=_shell(tmp_path))
    )

    sandbox.write("/workspace/gen.py", "open('out.txt', 'w').write('done')\n")
    sandbox.write("/workspace/in.md", "# hi\n")
    assert not (tmp_path / "workspace").exists()  # flat, no nested dir

    result = sandbox.execute("python3 gen.py")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "done"


def test_default_sandbox_still_offers_no_shell(tmp_path):
    sandbox = get_sandbox_profile("default").build(
        SandboxBuildRequest(
            profile_key="research",
            workspace_backend=FilesystemBackend(
                root_dir=str(tmp_path), virtual_mode=True
            ),
        )
    )
    assert isinstance(sandbox, DefaultFilesystemSandbox)
    assert not isinstance(sandbox, SandboxBackendProtocol)
    assert supports_execution(sandbox) is False


# -- recording wrappers --------------------------------------------------


def test_recording_sandbox_backend_forwards_and_logs_execute(tmp_path):
    transcript = tmp_path / "run.jsonl"
    backend = RecordingSandboxBackend(
        _shell(tmp_path), RunLogger("research", "t", path=transcript)
    )
    assert isinstance(backend, SandboxBackendProtocol)

    out = backend.execute("echo recorded-exec")
    assert "recorded-exec" in out.output

    events = [json.loads(line) for line in transcript.read_text().splitlines() if line]
    assert any(e["type"] == "fs_op" and e["op"] == "execute" for e in events)


def test_plain_recording_backend_stays_shell_free(tmp_path):
    backend = RecordingFilesystemBackend(
        FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
        RunLogger("research", "t", path=tmp_path / "r.jsonl"),
    )
    assert not isinstance(backend, SandboxBackendProtocol)


# -- SandboxRegistry -------------------------------------------------------


async def test_registry_builds_a_shell_backend_under_the_exec_profile(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config.settings, "default_sandbox_profile", "local-exec")
    storage = LocalStorage(tmp_path)
    session = await _agent_session(storage)
    registry = SandboxRegistry(store=storage)

    handle = await registry.get_or_create(LOCAL_USER_ID, session.session_id)

    assert isinstance(handle.backend, LocalShellBackend)
    assert "registry-exec" in handle.backend.execute("echo registry-exec").output


async def test_registry_default_profile_builds_a_plain_filesystem_backend(tmp_path):
    storage = LocalStorage(tmp_path)
    session = await _agent_session(storage)
    registry = SandboxRegistry(store=storage)

    handle = await registry.get_or_create(LOCAL_USER_ID, session.session_id)

    assert isinstance(handle.backend, FilesystemBackend)
    assert not isinstance(handle.backend, LocalShellBackend)
