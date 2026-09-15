from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents import DeepAgentState
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from krutrim_agent_management.config import settings
from krutrim_agents_core.agent_graph import (
    compose_awrap_tool_call as _compose_awrap_tool_call,
)
from krutrim_agents_core.agent_graph import (
    compose_wrap_model_call as _compose_wrap_model_call,
)
from krutrim_agents_core.agent_graph import (
    compose_wrap_tool_call as _compose_wrap_tool_call,
)
from krutrim_agents_core.agent_graph import (
    normalize_model_result as _normalize_model_result,
)
from krutrim_agents_core.agent_graph import (
    run_state_hooks as _run_state_hooks,
)
from krutrim_agents_core.harness.prompts import PromptLibrary
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import get_runtime

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from deepagents.backends.protocol import BackendProtocol
    from deepagents.middleware.filesystem import FilesystemPermission
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AnyMessage
    from langchain_core.tools import BaseTool
    from langgraph.cache.base import BaseCache
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore

# Middleware hook composition (`_run_state_hooks`/`_compose_*wrap_*_call`/
# `_normalize_model_result`) lives in `krutrim_agents_core.agent_graph`,
# shared with `krutrim_agents.profiles.research.agent.create_research_agent`
# — the other hand-rolled ReAct graph in this codebase — so the two copies
# can't drift apart. `_compose_awrap_tool_call` in particular is what keeps
# `ToolNode` (below) on its real async path once any middleware in the stack
# (e.g. `FilesystemMiddleware`) defines a sync `wrap_tool_call`: without it,
# `ToolNode`'s async run falls back to a sync tool executor, which raises
# `NotImplementedError: StructuredTool does not support sync invocation.` the
# moment an async-only tool (`web_search`, `web_fetch`, `rag_tool`) is called.
#
# NOTE: unlike `create_research_agent`, the model/before_agent nodes below
# are still sync-only (no `_arun_state_hooks`/`_compose_awrap_model_call`
# equivalent), so an async-only middleware hook (e.g. `SkillsMiddleware`'s
# `abefore_agent`/`awrap_model_call`) is silently skipped here. Not fixed in
# this change — flagging it so it isn't mistaken for "already handled".

# 2. Graph nodes


def _make_model_node(
    model: BaseChatModel,
    middlewares: Sequence[AgentMiddleware],
    all_tools: list[BaseTool],
    system_prompt: str | None,
    system_prompt_fn: Callable[[dict[str, Any]], str] | None = None,
):
    def base_handler(request: ModelRequest) -> ModelResponse:
        messages: list[AnyMessage] = (
            [request.system_message] if request.system_message else []
        ) + request.messages
        bound_model = (
            request.model.bind_tools(request.tools) if request.tools else request.model
        )
        # Stream, so LangGraph's `stream_mode="messages"` sees real token deltas
        # (that's what `run_graph_as_agui` turns into `TEXT_MESSAGE_CONTENT` /
        # `REASONING_MESSAGE_CONTENT` events). The accumulated chunk is a plain
        # `AIMessage` for the rest of the graph. Falls back to `.invoke` for a
        # model with no `.stream` (test fakes) or a stream that yields nothing.
        stream = getattr(bound_model, "stream", None)
        if callable(stream):
            accumulated: AnyMessage | None = None
            for chunk in stream(messages):
                accumulated = chunk if accumulated is None else accumulated + chunk
            if accumulated is not None:
                return ModelResponse(result=[accumulated])
        return ModelResponse(result=[bound_model.invoke(messages)])

    wrap_chain = _compose_wrap_model_call(middlewares, base_handler)

    def model_node(state: dict[str, Any]) -> dict[str, Any]:
        before_updates = _run_state_hooks(middlewares, "before_model", state)
        working_state = {**state, **before_updates}

        # `system_prompt_fn`, when supplied, re-renders the prompt from live
        # state on every model call — used by the research profile so its
        # Runtime Context block (research_state/known/unknown information)
        # stays fresh instead of frozen at profile-registration time. Falls
        # back to the static `system_prompt` string when absent, matching
        # every other profile's behavior.
        prompt_text = (
            system_prompt_fn(working_state) if system_prompt_fn else system_prompt
        )

        request = ModelRequest(
            model=model,
            messages=working_state["messages"],
            system_message=SystemMessage(content=prompt_text) if prompt_text else None,
            tools=all_tools,
            state=working_state,
            runtime=get_runtime(),
        )
        response = _normalize_model_result(wrap_chain(request))

        after_updates = _run_state_hooks(middlewares, "after_model", working_state)
        return {**before_updates, **after_updates, "messages": response.result}

    return model_node


def _route_after_model(state: dict[str, Any]) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_chat_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    system_prompt_fn: Callable[[dict[str, Any]], str] | None = None,
    middleware: Sequence[AgentMiddleware] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    permissions: list[FilesystemPermission] | None = None,
    backend: BackendProtocol | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    context_schema: type | None = None,
    state_schema: type | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph:
    """Compile a ReAct agent by hand; same param names as `deepagents.create_deep_agent`.

    `system_prompt_fn`, when supplied, takes precedence over the static
    `system_prompt` string and is re-invoked with the graph's working state
    on every model-node call — see `_make_model_node`.

    `backend`/`skills`/`permissions` grant file capability only when the
    caller explicitly opts in by passing a `backend` (normally the session's
    sandboxed workspace, e.g. via `krutrim_agents_core.builder.build_workspace_backend`):
    a `FilesystemMiddleware` is then added so the model gets `write_file`/
    `read_file`/`edit_file`/`ls`/`glob`/`grep`/`delete`, and, when `skills` is
    non-empty, a `SkillsMiddleware` for the given skill sources (e.g.
    `document-export`). Omitting `backend` keeps today's tool-free chat graph
    unchanged — used by compile-only callers (e.g. reading checkpoint state).
    `memory` is accepted for signature parity with `create_deep_agent` but
    unused — chat has no per-chat long-term memory file yet.
    """
    prompt_lib = PromptLibrary(settings.prompts_root_dir)
    if system_prompt == "default" or system_prompt is None:
        system_prompt = prompt_lib.render("chat_system", scope="default")
    has_backend = backend is not None
    backend = backend or StateBackend()

    stack: list[AgentMiddleware] = []
    stack.extend(middleware or [])
    if skills:
        stack.append(SkillsMiddleware(backend=backend, sources=skills))
    if has_backend:
        stack.append(FilesystemMiddleware(backend=backend, _permissions=permissions))

    # every middleware may contribute tools (e.g. SubAgentMiddleware -> `task`)
    all_tools: list[BaseTool] = [*(tools or [])]
    for mw in stack:
        all_tools.extend(getattr(mw, "tools", None) or [])

    graph_state_schema = state_schema or DeepAgentState
    graph = StateGraph(graph_state_schema, context_schema=context_schema)

    graph.add_node(
        "before_agent", lambda state: _run_state_hooks(stack, "before_agent", state)
    )
    graph.add_node(
        "model",
        _make_model_node(model, stack, all_tools, system_prompt, system_prompt_fn),
    )
    graph.add_edge(START, "before_agent")
    graph.add_edge("before_agent", "model")

    if all_tools:
        graph.add_node(
            "tools",
            ToolNode(
                all_tools,
                wrap_tool_call=_compose_wrap_tool_call(stack),
                awrap_tool_call=_compose_awrap_tool_call(stack),
            ),
        )
        graph.add_conditional_edges(
            "model", _route_after_model, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "model")
    else:
        graph.add_edge("model", END)

    return graph.compile(
        checkpointer=checkpointer, store=store, cache=cache, debug=debug, name=name
    )
