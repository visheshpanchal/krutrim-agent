"""Generic graph assembly — the same wiring for every agent profile.

Reads whatever a profile declares (prompts, tools, subagents, skills,
memory, roles) and assembles a deepagents graph. Never imports a specific
profile module — profiles are the plugin surface, this is core.

Wiring, in one place:

- `backend`: built by the sandbox profile named by
  `settings.default_sandbox_profile` (`"default"` →
  `krutrim_agent_sandbox.backends.DefaultFilesystemSandbox`). It wraps the
  caller-supplied workspace backend — an in-process `FilesystemBackend` scoped
  to the session's workspace dir (see `krutrim_agent_sandbox.registry`) — in a
  `CompositeBackend` that also routes `/skills/common/`, `/skills/<key>/` and
  `/memory/` to read-only host directories (this profile's harness content,
  scoped so it can't see other profiles' memory). Read-only enforcement lives
  at the backend (`ReadOnlyFilesystemBackend`), not deepagents' `permissions`
  middleware, since the `execute` tool bypasses tool-level checks. The shipped
  `"default"` profile offers no shell `execute` (`DefaultFilesystemSandbox` is
  not a `SandboxBackendProtocol`); the opt-in `"local-exec"` profile builds
  `LocalExecSandbox` over a host `LocalShellBackend`, and the `execute` tool
  is offered then. A future isolated runtime registers its own profile and
  becomes selectable by config alone.
- when `run_logger` is passed, the workspace backend is wrapped in
  `RecordingFilesystemBackend` first (or `RecordingSandboxBackend` when the
  workspace backend is a shell, so `execute` still reaches it), so the per-run
  eval trace sees every `/workspace` read/write (harness routes excluded).
- `middleware=[FrontendToolBridgeMiddleware()]`: bridges frontend-defined
  tools (the shared `render_content` action) into the model's tool list, and
  routes their execution back to the frontend.
- `SandboxPolicyMiddleware` (next, when the sandbox policy has any rule in
  force or the profile grants a shell): checks `write_file`/`edit_file`/
  `delete` against `settings.sandbox_files_policy` (a real block) and `execute`
  against `settings.sandbox_shell_mode` + the allow/deny lists + this run's
  resolved path prefixes (advisory). A rule may `deny` (refusal `ToolMessage`)
  or, under the `"interrupt"` / `"approval"` modes, `approve` — pause the run
  on a LangGraph `interrupt(...)` for a human decision. See
  `krutrim_agent_sandbox.execution_policy`.
- `checkpointer`: required by the AG-UI stream translator
  (`krutrim_agent_agui.run_graph_as_agui` calls `graph.aget_state()` to
  read the final message per `threadId` after a run). Callers
  pass a durable, session-scoped saver (see `api/agent_run.py` — a dedicated
  SQLite file per session, not shared across sessions); an `InMemorySaver()`
  is used only when no checkpointer is supplied, e.g. by tests that just need
  the graph to compile.
- `extra_tools`: additional tools appended after `profile.tools()` — used by
  `api/agent_run.py` to grant the cross-agent `message_agent` tool
  (`agents/cross_agent.py`) only to sessions whose sharing policy and peer
  set actually make it usable, without profiles needing to know this tool
  exists at all.
- `extra_middleware`: `AgentMiddleware` appended after
  `FrontendToolBridgeMiddleware` — used to attach `RunLoggingMiddleware`
  (`krutrim_agents_core.harness.run_logging`) so every model/tool call lands
  in the per-run JSONL transcript, without profiles knowing it exists.
- `graph_pattern`: a profile may override the compiled topology (see
  `DeepAgentContext` below). Every profile without one keeps compiling
  through `create_deep_agent`'s ReAct loop exactly as before.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from deepagents.backends.protocol import SandboxBackendProtocol
from krutrim_agent_management.config import settings
from krutrim_agent_sandbox.backends import SandboxBuildRequest, get_sandbox_profile
from krutrim_agent_sandbox.execution_policy import (
    SandboxExecutionPolicy,
    resolve_shell_path_prefixes,
)
from langgraph.checkpoint.memory import InMemorySaver

from krutrim_agents_core.frontend_tools import FrontendToolBridgeMiddleware
from krutrim_agents_core.harness.recording_backend import (
    RecordingFilesystemBackend,
    RecordingSandboxBackend,
)
from krutrim_agents_core.providers.registry import build_chat_model
from krutrim_agents_core.sandbox_policy_middleware import SandboxPolicyMiddleware

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol
    from deepagents.middleware.subagents import SubAgent
    from krutrim_agent_sandbox.scope import ProjectInfo
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from krutrim_agents_core.harness.runs import RunLogger
    from krutrim_agents_core.profile import AgentProfile
    from krutrim_agents_core.providers.base import ModelSettings


@dataclass
class DeepAgentContext:
    """Everything `create_deep_agent` would consume, assembled once by `build_agent`.

    Handed to `profile.graph_pattern` instead of a raw `create_deep_agent(...)`
    call, so a profile that wants a different graph topology (planner/worker,
    supervisor, reflection loop, ...) can still reuse the model, tools,
    prompt, subagents, skills, memory, backend, middleware, and checkpointer
    that `build_agent` already wired up — without recomputing any of it.

    Call `.react_agent()` to get a fully-wired deepagents ReAct graph
    (filesystem/subagent/skills/memory middleware, prompt assembly,
    `DeepAgentState`, `FrontendToolBridgeMiddleware`) as a single compiled
    node — LangGraph compiled graphs are plain runnables, so it can be
    dropped into a hand-built `StateGraph` with `graph.add_node("worker",
    context.react_agent())`.

    Skipping `.react_agent()` entirely (building nodes by hand instead) means
    re-earning, on your own, everything `create_deep_agent` gives you for
    free:

    - filesystem/skills/memory/subagent tool wiring — these middleware
      classes are coupled to `create_agent`'s fixed `model`/`tools` node
      shape and don't attach to an arbitrary `StateGraph` node on their own.
    - `FrontendToolBridgeMiddleware` — only fires inside a `create_agent`-built
      model node; a hand-written node silently won't bridge frontend tools
      unless you replicate that wiring yourself.
    - checkpointer/state compatibility — the AG-UI translator
      (`krutrim_agent_agui`) calls `graph.aget_state()` keyed by
      `threadId`; a custom graph must be compiled with the same `checkpointer`
      and keep a `messages` key
      shaped like `DeepAgentState` (it uses a `DeltaChannel` reducer to keep
      checkpoint growth linear) or streaming/resume breaks.
    - the `recursion_limit`/tracing `.with_config(...)` that `create_deep_agent`
      applies at the end — a custom top-level graph needs its own equivalent.

    None of this applies to nodes built via `.react_agent()` — only to graph
    nodes you construct by hand instead of using it.
    """

    model: BaseChatModel
    tools: list[BaseTool]
    system_prompt: str
    subagents: list[SubAgent]
    skills: list[str]
    memory: list[str]
    backend: BackendProtocol
    middleware: list[AgentMiddleware[Any, Any, Any]]
    checkpointer: BaseCheckpointSaver
    name: str
    user_id: str

    def react_agent(self, **overrides: Any) -> CompiledStateGraph:
        """Compile the standard deepagents ReAct graph from this context.

        Pass keyword overrides (e.g. `tools=`, `system_prompt=`) to compile a
        variant — e.g. a planner or critic node with a narrower tool set —
        without hand-rolling the rest of the wiring.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "tools": self.tools,
            "system_prompt": self.system_prompt,
            "subagents": self.subagents,
            "skills": self.skills,
            "memory": self.memory,
            "backend": self.backend,
            "middleware": self.middleware,
            "checkpointer": self.checkpointer,
            "name": self.name,
        }
        kwargs.update(overrides)
        return create_deep_agent(**kwargs)


def build_workspace_backend(
    profile_key: str,
    workspace_backend: BackendProtocol | None = None,
    project_info: ProjectInfo | None = None,
    run_logger: RunLogger | None = None,
) -> BackendProtocol:
    """Build the routed `/workspace` + `/skills/*` + `/memory/` backend for one
    graph build, via `settings.default_sandbox_profile` (`"default"` point to
    `DefaultFilesystemSandbox`) — see the module docstring's `backend` bullet.

    `workspace_backend` is the raw `/workspace` backend (normally
    `SandboxRegistry.get_or_create(...).backend`); `None` lets the sandbox
    profile build its own from `project_info` (or fall back to in-state
    storage for compile-only callers). `profile_key` names the `/skills/<key>/`
    and `/memory/` routes — a key with no matching `harness/{skills,memory}/<key>/`
    directory on disk just mounts an empty read-only route, not an error.
    `run_logger`, when given, wraps the workspace backend in
    `RecordingFilesystemBackend` first so the per-run eval trace captures
    every `/workspace` read/write.
    """
    if run_logger is not None and workspace_backend is not None:
        recorder = (
            RecordingSandboxBackend
            if isinstance(workspace_backend, SandboxBackendProtocol)
            else RecordingFilesystemBackend
        )
        workspace_backend = recorder(workspace_backend, run_logger)

    sandbox_profile = get_sandbox_profile(settings.default_sandbox_profile)
    return sandbox_profile.build(
        SandboxBuildRequest(
            profile_key=profile_key,
            workspace_backend=workspace_backend,
            project_info=project_info,
        )
    )


def build_agent(
    profile: AgentProfile,
    models: Mapping[str, ModelSettings],
    sandbox: BackendProtocol | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_tools: list[BaseTool] | None = None,
    extra_middleware: list[AgentMiddleware[Any, Any, Any]] | None = None,
    *,
    user_id: str,
    project_info: ProjectInfo | None = None,
    run_logger: RunLogger | None = None,
) -> CompiledStateGraph:
    """`models` is the resolved `{role: ModelSettings}` map for this profile
    (see `krutrim_agents_core.providers.resolver.resolve_models`) — one entry
    per declared role, already merged from profile defaults + the agent
    instance's + the session's overrides by the caller.

    `sandbox` is the raw `/workspace` backend (normally
    `SandboxRegistry.get_or_create(...).backend`); `None` lets the sandbox
    profile build its own from `project_info` (or fall back to in-state
    storage for compile-only callers). `project_info` names the
    project/agent/session this build is for. `run_logger`, when given, wraps
    the workspace backend in `RecordingFilesystemBackend` so the per-run eval
    trace captures every `/workspace` read/write.
    """
    backend = build_workspace_backend(
        profile.key,
        workspace_backend=sandbox,
        project_info=project_info,
        run_logger=run_logger,
    )

    # Sandbox execution policy — gates the file tools (real) and, under a shell
    # profile, the `execute` command (advisory). Outermost tool-call wrapper
    # after the frontend bridge, so a refused call never reaches the logger.
    policy = SandboxExecutionPolicy.from_settings()
    policy_middleware: list[AgentMiddleware[Any, Any, Any]] = []
    sandbox_profile = get_sandbox_profile(settings.default_sandbox_profile)
    if policy.needs_middleware or getattr(sandbox_profile, "execute", False):
        policy_middleware = [
            SandboxPolicyMiddleware(policy, resolve_shell_path_prefixes(project_info))
        ]

    main_settings = models.get("main") or next(iter(models.values()))
    context = DeepAgentContext(
        model=build_chat_model(main_settings),
        tools=[*profile.tools(), *(extra_tools or [])],
        system_prompt=profile.main_system_prompt,
        subagents=profile.subagents(models),
        skills=list(profile.skills_sources),
        memory=list(profile.memory_sources),
        backend=backend,
        middleware=[
            FrontendToolBridgeMiddleware(),
            *policy_middleware,
            *(extra_middleware or []),
        ],
        checkpointer=checkpointer or InMemorySaver(),
        name=profile.key,
        user_id=user_id,
    )

    if profile.graph_pattern is not None:
        return profile.graph_pattern(context)

    return context.react_agent()
