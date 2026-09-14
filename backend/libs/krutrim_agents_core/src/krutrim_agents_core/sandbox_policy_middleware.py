"""Enforces `SandboxExecutionPolicy` on an agent run.

`wrap_tool_call` checks `write_file` / `edit_file` / `delete` against the files
mode and `execute` against the shell mode + allow / deny lists + this run's
resolved path prefixes (see `krutrim_agent_sandbox.execution_policy`). Each
check yields a `PolicyVerdict`:

- `allow`   — the call runs untouched.
- `deny`    — a `ToolMessage(status="error")` is returned in its place; the
  model reads the reason and adapts.
- `approve` — the run pauses on a LangGraph `interrupt(...)` carrying the tool
  call + reason. The host surfaces it (the AG-UI translator turns it into a
  `RUN_FINISHED` interrupt outcome); the resume value decides: approve → the
  call runs, reject → the same refusal `ToolMessage`.

`approve` is what the `"interrupt"` files mode and the `"approval"` shell mode
produce. On resume LangGraph re-enters the tool node, so `interrupt()` returns
the decision instead of raising.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from krutrim_agent_sandbox.execution_policy import (
    SandboxExecutionPolicy,
    evaluate_file_write,
    evaluate_shell_command,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain.agents.middleware.types import ToolCallRequest
    from langgraph.types import Command

_APPROVE_WORDS = frozenset(
    {"approve", "approved", "accept", "accepted", "resolved", "yes", "allow"}
)


def _is_approved(decision: Any) -> bool:
    """Whether a resume value means "run the call". Anything unrecognised is a
    reject — a pause defaults to the safe answer."""
    if decision is True:
        return True
    if isinstance(decision, str):
        return decision.strip().lower() in _APPROVE_WORDS
    if isinstance(decision, dict):
        if decision.get("approved") is True:
            return True
        if str(decision.get("status", "")).lower() == "resolved":
            return True
        return str(decision.get("decision", "")).strip().lower() in _APPROVE_WORDS
    return False


def _rejection_note(decision: Any) -> str:
    if isinstance(decision, dict):
        payload = decision.get("payload")
        if isinstance(payload, dict) and payload.get("note"):
            return f" ({payload['note']})"
        if decision.get("note"):
            return f" ({decision['note']})"
    return ""


class SandboxPolicyMiddleware(AgentMiddleware):
    def __init__(
        self,
        policy: SandboxExecutionPolicy,
        shell_path_prefixes: tuple[str, ...],
    ) -> None:
        super().__init__()
        self._policy = policy
        self._prefixes = shell_path_prefixes

    @property
    def name(self) -> str:
        return "SandboxPolicyMiddleware"

    def _verdict(self, tool_call: dict[str, Any]):
        name = tool_call.get("name")
        args = tool_call.get("args") or {}
        if name == "execute":
            return evaluate_shell_command(
                str(args.get("command", "")), self._policy, self._prefixes
            )
        return evaluate_file_write(self._policy, name, str(args.get("file_path", "")))

    @staticmethod
    def _refusal(tool_call: dict[str, Any], reason: str) -> ToolMessage:
        return ToolMessage(
            content=f"Error: {reason}",
            name=tool_call.get("name"),
            tool_call_id=tool_call.get("id"),
            status="error",
        )

    @staticmethod
    def _approval_request(tool_call: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "type": "tool_approval",
            "reason": reason,
            "tool_name": tool_call.get("name"),
            "tool_call_id": tool_call.get("id"),
            "args": tool_call.get("args") or {},
        }

    def _gate(self, tool_call: dict[str, Any]) -> ToolMessage | None:
        """A refusal `ToolMessage` to return in the call's place, or `None` to
        let it run. Raises (via `interrupt`) to pause for approval; on resume
        `interrupt` returns the decision and this returns `None` / a refusal."""
        verdict = self._verdict(tool_call)
        if verdict.action == "deny":
            return self._refusal(tool_call, verdict.reason)
        if verdict.action == "approve":
            decision = interrupt(self._approval_request(tool_call, verdict.reason))
            if not _is_approved(decision):
                return self._refusal(
                    tool_call,
                    f"rejected by reviewer{_rejection_note(decision)}: "
                    f"{verdict.reason}",
                )
        return None

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        blocked = self._gate(request.tool_call)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        blocked = self._gate(request.tool_call)
        return blocked if blocked is not None else await handler(request)
