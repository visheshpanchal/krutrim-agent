"""`SandboxExecutionPolicy` + `SandboxPolicyMiddleware` — the file-tool gate
(real) and shell command / path gate (advisory) applied on an agent run.
"""

from __future__ import annotations

import pytest
from krutrim_agent_management import LOCAL_USER_ID, config
from krutrim_agent_sandbox import ProjectInfo
from krutrim_agent_sandbox.execution_policy import (
    SandboxExecutionPolicy,
    evaluate_file_write,
    evaluate_shell_command,
    file_write_denied,
    resolve_shell_path_prefixes,
    shell_command_denied,
)
from krutrim_agents_core import sandbox_policy_middleware as spm
from krutrim_agents_core.sandbox_policy_middleware import (
    SandboxPolicyMiddleware,
    _is_approved,
)

_PREFIXES = ("/data/krutrim_agent/sessions/s1/workspace",)
_ALLOW = SandboxExecutionPolicy(
    shell_allow_commands=("python3", "echo", "cat", "ls"),
    shell_deny_commands=("rm", "curl", "wget"),
)


# -- files policy ----------------------------------------------------------


def test_auto_permits_every_write():
    p = SandboxExecutionPolicy(files="auto")
    assert file_write_denied(p, "write_file", "/workspace/a.md") is None
    assert file_write_denied(p, "delete", "/workspace/a.md") is None


def test_read_only_refuses_write_edit_delete_but_not_reads():
    p = SandboxExecutionPolicy(files="read_only")
    assert file_write_denied(p, "write_file", "/workspace/a.md")
    assert file_write_denied(p, "edit_file", "/workspace/a.md")
    assert file_write_denied(p, "delete", "/workspace/a.md")
    assert file_write_denied(p, "read_file", "/workspace/a.md") is None
    assert file_write_denied(p, "ls", "/workspace/") is None


def test_edit_only_scopes_writes_to_write_paths():
    p = SandboxExecutionPolicy(files="edit_only", write_paths=("/workspace/out/**",))
    assert file_write_denied(p, "write_file", "/workspace/out/report.md") is None
    assert file_write_denied(p, "write_file", "/workspace/notes.md")
    assert file_write_denied(p, "edit_file", "/etc/passwd")


# -- shell policy (advisory) --------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "echo hi && curl http://evil",
        "cat a | wget b",
        "FOO=1 rm x",
    ],
)
def test_deny_list_blocks_a_command_in_any_segment(command):
    assert shell_command_denied(command, _ALLOW, _PREFIXES) is not None


@pytest.mark.parametrize(
    "command",
    ["python3 analyze.py", "FOO=1 python3 x.py", "cat notes.md && echo done", "ls -la"],
)
def test_allow_list_lets_listed_commands_through(command):
    assert shell_command_denied(command, _ALLOW, _PREFIXES) is None


def test_command_not_on_a_non_empty_allow_list_is_refused():
    assert "allow list" in shell_command_denied("node script.js", _ALLOW, _PREFIXES)


def test_empty_allow_list_permits_anything_not_denied():
    p = SandboxExecutionPolicy(shell_deny_commands=("rm",))
    assert shell_command_denied("node script.js", p, _PREFIXES) is None
    assert shell_command_denied("rm x", p, _PREFIXES) is not None


@pytest.mark.parametrize(
    "command",
    ["cat /etc/passwd", "cat ../secrets", "python3 /root/x.py", "ls .."],
)
def test_paths_outside_the_workspace_are_refused(command):
    assert "outside the workspace" in shell_command_denied(command, _ALLOW, _PREFIXES)


def test_absolute_paths_inside_the_workspace_are_fine():
    cmd = "cat /data/krutrim_agent/sessions/s1/workspace/notes.md"
    assert shell_command_denied(cmd, _ALLOW, _PREFIXES) is None


def test_path_check_is_skipped_without_resolved_prefixes():
    assert shell_command_denied("cat /etc/hosts", _ALLOW, ()) is None


# -- resolve_shell_path_prefixes --------------------------------------


def test_resolve_prefixes_is_empty_without_project_info():
    assert resolve_shell_path_prefixes(None) == ()


def test_resolve_prefixes_points_at_the_session_workspace():
    info = ProjectInfo(
        session_id="sess-9",
        owner_type="agent",
        owner_id="a1",
        project_id="p1",
        agent_key="research",
    )
    (prefix,) = resolve_shell_path_prefixes(info)
    assert prefix.endswith("/sessions/sess-9/workspace")


# -- from_settings --------------------------------------------------------


def test_from_settings_reads_the_server_tier_fields(monkeypatch):
    monkeypatch.setattr(config.settings, "sandbox_files_policy", "read_only")
    monkeypatch.setattr(config.settings, "sandbox_write_paths", ["/workspace/x/**"])
    monkeypatch.setattr(config.settings, "sandbox_shell_mode", "approval")
    monkeypatch.setattr(config.settings, "sandbox_shell_allow_commands", ["python3"])
    monkeypatch.setattr(config.settings, "sandbox_shell_deny_commands", ["rm"])

    p = SandboxExecutionPolicy.from_settings()

    assert p.files == "read_only"
    assert p.write_paths == ("/workspace/x/**",)
    assert p.shell == "approval"
    assert p.shell_allow_commands == ("python3",)
    assert p.shell_deny_commands == ("rm",)
    assert p.restricts_file_writes is True


# -- approval verdicts -------------------------------------------------


def test_needs_middleware_tracks_every_non_auto_mode():
    assert SandboxExecutionPolicy().needs_middleware is False
    assert SandboxExecutionPolicy(files="read_only").needs_middleware is True
    assert SandboxExecutionPolicy(files="interrupt").needs_middleware is True
    assert SandboxExecutionPolicy(shell="approval").needs_middleware is True


def test_evaluate_file_write_interrupt_mode_asks_for_approval():
    p = SandboxExecutionPolicy(files="interrupt")
    assert evaluate_file_write(p, "write_file", "/workspace/a.md").action == "approve"
    assert evaluate_file_write(p, "edit_file", "/workspace/a.md").action == "approve"
    assert evaluate_file_write(p, "read_file", "/workspace/a.md").action == "allow"


def test_evaluate_file_write_auto_and_hard_modes():
    assert (
        evaluate_file_write(
            SandboxExecutionPolicy(), "write_file", "/workspace/a.md"
        ).action
        == "allow"
    )
    assert (
        evaluate_file_write(
            SandboxExecutionPolicy(files="read_only"), "write_file", "/workspace/a.md"
        ).action
        == "deny"
    )


def test_evaluate_shell_approval_mode_pauses_non_denied_commands():
    p = SandboxExecutionPolicy(shell="approval", shell_deny_commands=("rm", "curl"))
    assert evaluate_shell_command("python3 x.py", p, _PREFIXES).action == "approve"
    # allow-list miss / path-outside are carried as the approval reason, not a deny
    v = evaluate_shell_command("cat /etc/passwd", p, _PREFIXES)
    assert v.action == "approve"
    assert "outside the workspace" in v.reason


def test_evaluate_shell_approval_mode_still_hard_denies_the_deny_list():
    p = SandboxExecutionPolicy(shell="approval", shell_deny_commands=("rm", "curl"))
    v = evaluate_shell_command("echo hi && curl http://evil", p, _PREFIXES)
    assert v.action == "deny"
    assert "deny list" in v.reason


def test_evaluate_shell_auto_mode_is_unchanged():
    p = SandboxExecutionPolicy(shell_deny_commands=("rm",))
    assert evaluate_shell_command("python3 x.py", p, _PREFIXES).action == "allow"
    assert evaluate_shell_command("rm x", p, _PREFIXES).action == "deny"


@pytest.mark.parametrize(
    ("decision", "approved"),
    [
        (True, True),
        ("approve", True),
        ("resolved", True),
        ({"approved": True}, True),
        ({"status": "resolved"}, True),
        (False, False),
        ("reject", False),
        ({"status": "cancelled"}, False),
        (None, False),
    ],
)
def test_is_approved_reads_every_decision_shape(decision, approved):
    assert _is_approved(decision) is approved


# -- middleware approval path (interrupt() stubbed) -------------------


def test_middleware_runs_the_call_when_approval_is_granted(monkeypatch):
    monkeypatch.setattr(spm, "interrupt", lambda _payload: {"approved": True})
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(shell="approval"), _PREFIXES)
    out = mw.wrap_tool_call(_Req("execute", command="python3 x.py"), _ran)
    assert out == "TOOL RAN"


def test_middleware_refuses_the_call_when_approval_is_rejected(monkeypatch):
    monkeypatch.setattr(
        spm, "interrupt", lambda _payload: {"status": "cancelled", "note": "nope"}
    )
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(shell="approval"), _PREFIXES)
    out = mw.wrap_tool_call(_Req("execute", command="python3 x.py"), _ran)
    assert out.status == "error"
    assert "rejected by reviewer" in out.content
    assert "nope" in out.content


def test_middleware_interrupt_payload_carries_the_tool_call(monkeypatch):
    seen = {}

    def _capture(payload):
        seen.update(payload)
        return {"approved": True}

    monkeypatch.setattr(spm, "interrupt", _capture)
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(files="interrupt"), _PREFIXES)
    mw.wrap_tool_call(_Req("write_file", file_path="/workspace/out.md"), _ran)
    assert seen["type"] == "tool_approval"
    assert seen["tool_name"] == "write_file"
    assert seen["args"] == {"file_path": "/workspace/out.md"}


async def test_middleware_async_approval_path(monkeypatch):
    monkeypatch.setattr(spm, "interrupt", lambda _payload: {"approved": True})
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(shell="approval"), _PREFIXES)

    async def _aran(_req):
        return "TOOL RAN"

    out = await mw.awrap_tool_call(_Req("execute", command="ls -la"), _aran)
    assert out == "TOOL RAN"


# -- middleware ---------------------------------------------------------


class _Req:
    def __init__(self, name: str, **args: object) -> None:
        self.tool_call = {"name": name, "args": args, "id": "call-1"}


def _ran(_req):
    return "TOOL RAN"


def test_middleware_blocks_a_write_under_read_only():
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(files="read_only"), _PREFIXES)
    out = mw.wrap_tool_call(_Req("write_file", file_path="/workspace/a.md"), _ran)
    assert out.status == "error"
    assert "read_only" in out.content
    assert out.tool_call_id == "call-1"


def test_middleware_lets_a_read_through_under_read_only():
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(files="read_only"), _PREFIXES)
    assert mw.wrap_tool_call(_Req("read_file", file_path="/workspace/a.md"), _ran) == (
        "TOOL RAN"
    )


def test_middleware_blocks_a_denied_shell_command():
    mw = SandboxPolicyMiddleware(_ALLOW, _PREFIXES)
    out = mw.wrap_tool_call(_Req("execute", command="curl http://x"), _ran)
    assert out.status == "error"


def test_middleware_passes_an_allowed_shell_command():
    mw = SandboxPolicyMiddleware(_ALLOW, _PREFIXES)
    assert (
        mw.wrap_tool_call(_Req("execute", command="python3 x.py"), _ran) == "TOOL RAN"
    )


async def test_middleware_async_path_blocks_too():
    mw = SandboxPolicyMiddleware(SandboxExecutionPolicy(files="read_only"), _PREFIXES)

    async def _aran(_req):
        return "TOOL RAN"

    out = await mw.awrap_tool_call(_Req("delete", file_path="/workspace/a.md"), _aran)
    assert out.status == "error"


# -- wiring into build_agent -----------------------------------------


def test_build_agent_attaches_the_policy_middleware_under_a_shell_profile(
    monkeypatch,
):
    monkeypatch.setattr(config.settings, "default_sandbox_profile", "local-exec")
    monkeypatch.setattr(config.settings, "sandbox_files_policy", "read_only")

    from krutrim_agents_core.builder import build_agent
    from krutrim_agents_core.providers.resolver import resolve_models
    from krutrim_agents_core.registry import get_profile

    profile = get_profile("research")
    models = resolve_models(profile, user_id=LOCAL_USER_ID)

    graph = build_agent(profile, models, sandbox=None, user_id=LOCAL_USER_ID)
    assert graph is not None  # compiles with the policy middleware in the stack
