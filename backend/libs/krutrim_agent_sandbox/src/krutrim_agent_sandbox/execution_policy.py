"""Agent sandbox execution policy: what the file tools may write, and what the
shell may run, for one agent run.

Two halves, deliberately split:

* `SandboxExecutionPolicy` — the **static**, server-tier rules
  (`ServerSettings.sandbox_*`): a files mode + a write-path allowlist, plus
  shell command allow / deny lists.
* `resolve_shell_path_prefixes` — the **dynamic** half: the real host path
  prefixes this run's shell is allowed to touch, resolved per project / session
  at graph-build time. It lives in its own function because it is the piece
  that changes with the deployment — the bind-mount layout, project-shared
  workspaces, or a real isolated sandbox that enforces the boundary at the
  mount instead of here.

`SandboxPolicyMiddleware` (`krutrim_agents_core.sandbox_policy_middleware`)
calls `evaluate_file_write` / `evaluate_shell_command` from `wrap_tool_call`.
Each returns a `PolicyVerdict` — `allow`, `deny` (a refusal `ToolMessage` the
model reads), or `approve` (pause the run for a human approve/reject, then
either run the call or refuse it). The `approve` verdict is what the
`"interrupt"` files mode and the `"approval"` shell mode produce.

The file checks are a real gate on the file *tools*; the shell checks are
**advisory** — a shell can be told to run anything (`bash -c`, `eval`,
`$(...)`), so they are defense-in-depth and the place human approval hangs off,
not a security boundary. That boundary arrives with the isolated sandbox.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING

import wcmatch.glob as wcglob

from krutrim_agent_sandbox.paths import session_workspace_dir

if TYPE_CHECKING:
    from krutrim_agent_sandbox.scope import ProjectInfo

_GLOB_FLAGS = wcglob.GLOBSTAR | wcglob.DOTGLOB

# File tools whose calls the files policy gates.
WRITE_TOOLS = frozenset({"write_file", "edit_file", "delete"})

# Split a shell line into the segments a leading command can start: `;`,
# newline, `&&`, `||`, `|`, `|&`, `&`.
_SEGMENT_SPLIT = re.compile(r"&&|\|\|?&?|[;\n&]")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Absolute-path-looking token: a `/` not preceded by a word char, then path chars.
_ABS_PATH = re.compile(r"(?<![\w$])/[\w./+@=-]*")
_PARENT_REF = re.compile(r"(?:^|[\s/'\"])\.\.(?:/|$)")


@dataclass(frozen=True)
class SandboxExecutionPolicy:
    """The static half of the run's sandbox policy — see the module docstring."""

    files: str = "auto"  # "auto" | "read_only" | "edit_only" | "interrupt"
    write_paths: tuple[str, ...] = ("/workspace/**",)
    shell: str = "auto"  # "auto" | "approval"
    shell_allow_commands: tuple[str, ...] = ()
    shell_deny_commands: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls) -> SandboxExecutionPolicy:
        from krutrim_agent_management.config import settings

        return cls(
            files=settings.sandbox_files_policy,
            write_paths=tuple(settings.sandbox_write_paths),
            shell=settings.sandbox_shell_mode,
            shell_allow_commands=tuple(settings.sandbox_shell_allow_commands),
            shell_deny_commands=tuple(settings.sandbox_shell_deny_commands),
        )

    @property
    def restricts_file_writes(self) -> bool:
        return self.files in ("read_only", "edit_only")

    @property
    def needs_middleware(self) -> bool:
        """`True` when any file or shell rule is in force — `build_agent` reads
        this to decide whether to attach `SandboxPolicyMiddleware` at all."""
        return self.files != "auto" or self.shell != "auto"


@dataclass(frozen=True)
class PolicyVerdict:
    """Outcome of checking one tool call against the policy.

    `action` is `"allow"` (run it), `"deny"` (refuse with `reason`), or
    `"approve"` (pause for a human — on approve run it, on reject refuse with
    `reason`). `reason` is model-/human-facing and empty only for `"allow"`.
    """

    action: str
    reason: str = ""


_ALLOW = PolicyVerdict("allow")


def resolve_shell_path_prefixes(project_info: ProjectInfo | None) -> tuple[str, ...]:
    """Real host path prefixes this run's shell may reference.

    Today: just the session's own workspace dir (the shell's `cwd`). This is
    the one place to widen — a project-shared workspace, an attached session's
    dir, a different bind-mount root — or to drop once an isolated sandbox
    enforces the boundary at the mount.
    """
    if project_info is None:
        return ()
    return (str(session_workspace_dir(project_info.session_id).resolve()),)


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return bool(patterns) and wcglob.globmatch(path, list(patterns), flags=_GLOB_FLAGS)


def file_write_denied(
    policy: SandboxExecutionPolicy, tool_name: str | None, file_path: str
) -> str | None:
    """Reason `tool_name` on `file_path` is refused by the files policy, or `None`."""
    if tool_name not in WRITE_TOOLS or not policy.restricts_file_writes:
        return None
    if policy.files == "read_only":
        return (
            f"sandbox policy: writes are disabled (read_only) — "
            f"`{tool_name}` on {file_path!r} refused."
        )
    if _matches_any(file_path, policy.write_paths):
        return None
    return (
        f"sandbox policy: `{tool_name}` on {file_path!r} refused — edit_only "
        f"permits writes under {list(policy.write_paths)} only."
    )


def _leading_command(segment: str) -> str | None:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    for token in tokens:
        if _ENV_ASSIGN.match(token):
            continue  # `FOO=bar cmd ...`
        return token
    return None


def _command_matches(head: str, pattern: str) -> bool:
    base = head.rsplit("/", 1)[-1]
    return (
        pattern in (head, base)
        or wcglob.globmatch(base, pattern, flags=wcglob.DOTGLOB)
        or wcglob.globmatch(head, pattern, flags=wcglob.DOTGLOB)
    )


def _paths_outside(command: str, prefixes: tuple[str, ...]) -> list[str]:
    if _PARENT_REF.search(command):
        return [".."]
    if not prefixes:
        return []
    outside = [
        match
        for match in _ABS_PATH.findall(command)
        if len(match) > 1 and not any(match.startswith(p) for p in prefixes)
    ]
    return sorted(set(outside))


def shell_command_denied(
    command: str,
    policy: SandboxExecutionPolicy,
    path_prefixes: tuple[str, ...],
) -> str | None:
    """Reason `command` is refused by the shell policy, or `None`. Advisory —
    see the module docstring."""
    for segment in (s.strip() for s in _SEGMENT_SPLIT.split(command)):
        if not segment:
            continue
        head = _leading_command(segment)
        if head is None:
            continue
        base = head.rsplit("/", 1)[-1]
        if any(_command_matches(head, p) for p in policy.shell_deny_commands):
            return f"sandbox policy: command {base!r} is on the deny list."
        if policy.shell_allow_commands and not any(
            _command_matches(head, p) for p in policy.shell_allow_commands
        ):
            return (
                f"sandbox policy: command {base!r} is not on the allow list "
                f"{list(policy.shell_allow_commands)}."
            )
    escaping = _paths_outside(command, path_prefixes)
    if escaping:
        return (
            f"sandbox policy: shell command references path(s) outside the "
            f"workspace: {escaping}."
        )
    return None


def _shell_deny_list_reason(command: str, policy: SandboxExecutionPolicy) -> str | None:
    """Reason a segment of `command` leads with a deny-listed command, or `None`.

    The deny list is absolute — it is never downgraded to an approval prompt,
    so this check is split out from the advisory allow-list / path checks.
    """
    for segment in (s.strip() for s in _SEGMENT_SPLIT.split(command)):
        head = _leading_command(segment) if segment else None
        if head is None:
            continue
        if any(_command_matches(head, p) for p in policy.shell_deny_commands):
            base = head.rsplit("/", 1)[-1]
            return f"sandbox policy: command {base!r} is on the deny list."
    return None


def evaluate_file_write(
    policy: SandboxExecutionPolicy, tool_name: str | None, file_path: str
) -> PolicyVerdict:
    """How the files policy handles `tool_name` on `file_path`."""
    if tool_name not in WRITE_TOOLS:
        return _ALLOW
    reason = file_write_denied(policy, tool_name, file_path)
    if reason is not None:
        return PolicyVerdict("deny", reason)
    if policy.files == "interrupt":
        return PolicyVerdict(
            "approve", f"`{tool_name}` on {file_path!r} needs approval."
        )
    return _ALLOW


def evaluate_shell_command(
    command: str,
    policy: SandboxExecutionPolicy,
    path_prefixes: tuple[str, ...],
) -> PolicyVerdict:
    """How the shell policy handles `command`. A deny-list hit is always a hard
    refusal; under the `"approval"` mode everything else pauses for a human,
    carrying any advisory allow-list / path concern as the reason."""
    hard = _shell_deny_list_reason(command, policy)
    if hard is not None:
        return PolicyVerdict("deny", hard)
    advisory = shell_command_denied(command, policy, path_prefixes)
    if policy.shell == "approval":
        return PolicyVerdict("approve", advisory or "shell command needs approval.")
    if advisory is not None:
        return PolicyVerdict("deny", advisory)
    return _ALLOW
