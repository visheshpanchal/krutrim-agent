from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents import DeepAgentState
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from krutrim_agents_core.agent_graph import (
    arun_state_hooks as _arun_state_hooks,
)
from krutrim_agents_core.agent_graph import (
    compose_awrap_model_call as _compose_awrap_model_call,
)
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
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import get_runtime
from langgraph.utils.runnable import RunnableCallable

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from deepagents.backends.protocol import BackendProtocol
    from deepagents.middleware.filesystem import FilesystemPermission
    from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AnyMessage
    from langchain_core.tools import BaseTool
    from langgraph.cache.base import BaseCache
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore

# Middleware hook composition (`_overrides`/`_run_state_hooks`/
# `_compose_*wrap_*_call`/`_normalize_model_result`) lives in
# `krutrim_agents_core.agent_graph`, shared with
# `krutrim_agent_backend.chat.graph.build_chat_graph` — the other hand-rolled
# ReAct graph in this codebase — so the two copies can't drift apart.

# 2. Graph nodes


def _make_model_node(
    model: BaseChatModel,
    middlewares: Sequence[AgentMiddleware],
    all_tools: list[BaseTool],
    system_prompt: str | None,
    system_prompt_fn: Callable[[dict[str, Any]], str] | None = None,
):
    def _messages(request: ModelRequest) -> list[AnyMessage]:
        return (
            [request.system_message] if request.system_message else []
        ) + request.messages

    def base_handler(request: ModelRequest) -> ModelResponse:
        bound_model = (
            request.model.bind_tools(request.tools) if request.tools else request.model
        )
        return ModelResponse(result=[bound_model.invoke(_messages(request))])

    async def abase_handler(request: ModelRequest) -> ModelResponse:
        bound_model = (
            request.model.bind_tools(request.tools) if request.tools else request.model
        )
        return ModelResponse(result=[await bound_model.ainvoke(_messages(request))])

    wrap_chain = _compose_wrap_model_call(middlewares, base_handler)
    awrap_chain = _compose_awrap_model_call(middlewares, abase_handler)

    def _request(working_state: dict[str, Any]) -> ModelRequest:
        # `system_prompt_fn`, when supplied, re-renders the prompt from live
        # state on every model call — used by the research profile so its
        # Runtime Context block (research_state/known/unknown information)
        # stays fresh instead of frozen at profile-registration time. Falls
        # back to the static `system_prompt` string when absent, matching
        # every other profile's behavior.
        prompt_text = (
            system_prompt_fn(working_state) if system_prompt_fn else system_prompt
        )
        return ModelRequest(
            model=model,
            messages=working_state["messages"],
            system_message=SystemMessage(content=prompt_text) if prompt_text else None,
            tools=all_tools,
            state=working_state,
            runtime=get_runtime(),
        )

    def model_node(state: dict[str, Any]) -> dict[str, Any]:
        before_updates = _run_state_hooks(middlewares, "before_model", state)
        working_state = {**state, **before_updates}
        response = _normalize_model_result(wrap_chain(_request(working_state)))
        after_updates = _run_state_hooks(middlewares, "after_model", working_state)
        return {**before_updates, **after_updates, "messages": response.result}

    async def amodel_node(state: dict[str, Any]) -> dict[str, Any]:
        before_updates = await _arun_state_hooks(middlewares, "before_model", state)
        working_state = {**state, **before_updates}
        response = _normalize_model_result(await awrap_chain(_request(working_state)))
        after_updates = await _arun_state_hooks(
            middlewares, "after_model", working_state
        )
        return {**before_updates, **after_updates, "messages": response.result}

    return RunnableCallable(model_node, amodel_node, name="model")


def _route_after_model(state: dict[str, Any]) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def create_research_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    system_prompt_fn: Callable[[dict[str, Any]], str] | None = None,
    middleware: Sequence[AgentMiddleware] | None = None,
    subagents: Sequence[SubAgent | CompiledSubAgent] | None = None,
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
    """
    backend = backend or StateBackend()

    stack: list[AgentMiddleware] = []
    if skills is not None:
        stack.append(SkillsMiddleware(backend=backend, sources=skills))
    stack.append(FilesystemMiddleware(backend=backend, _permissions=permissions))
    if subagents:
        stack.append(SubAgentMiddleware(backend=backend, subagents=subagents))
    stack.append(PatchToolCallsMiddleware())
    if memory is not None:
        stack.append(MemoryMiddleware(backend=backend, sources=memory))
    stack.extend(middleware or [])

    # every middleware may contribute tools (e.g. SubAgentMiddleware -> `task`)
    all_tools: list[BaseTool] = [*(tools or [])]
    for mw in stack:
        all_tools.extend(getattr(mw, "tools", None) or [])

    graph_state_schema = state_schema or DeepAgentState
    graph = StateGraph(graph_state_schema, context_schema=context_schema)

    graph.add_node(
        "before_agent",
        RunnableCallable(
            lambda state: _run_state_hooks(stack, "before_agent", state),
            lambda state: _arun_state_hooks(stack, "before_agent", state),
            name="before_agent",
        ),
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
