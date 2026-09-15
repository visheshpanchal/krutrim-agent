"""Shared primitives for hand-rolled `AgentMiddleware`-driven graphs.

Two call sites compile a ReAct-style graph node-by-node instead of going
through `deepagents.create_deep_agent` / `langchain.agents.create_agent`:
`krutrim_agents.profiles.research.agent.create_research_agent` (needs a
`system_prompt_fn` re-rendered on every model call, plus an async model node)
and `krutrim_agent_backend.chat.graph.build_chat_graph` (needs the same
middleware-hook shape without the subagent/skills scaffolding
`create_deep_agent` bundles). Both still have to run the exact same
`AgentMiddleware` hook protocol (`before_agent`/`before_model`/`after_model`,
`wrap_model_call`/`awrap_model_call`, `wrap_tool_call`/`awrap_tool_call`) that
`create_agent` runs internally for them — `langchain.agents.factory` has its
own version of this composition logic, but it's private
(`_chain_tool_call_wrappers` and friends) and tied to `create_agent`'s fixed
node shape, so it isn't something a hand-built graph can import.

This module is the one place *our* copy of that composition logic lives, so
the two call sites can't drift out of sync with each other — which is
exactly what happened before this module existed: `chat/graph.py` had a
`_compose_wrap_tool_call` but no async twin, which was harmless while nothing
in chat's middleware stack overrode `wrap_tool_call`. The moment
`FilesystemMiddleware` (which overrides both) was added to chat's stack,
`ToolNode` started routing every tool call through its sync-fallback path
(see `langgraph.prebuilt.tool_node.ToolNode._arun_one`: sync `wrap_tool_call`
set + no `awrap_tool_call` => sync executor even on the async run path), and
any async-only tool (`web_search`, `web_fetch`, `rag_tool` — plain `@tool`
on an `async def`, no sync `func`) started raising
`NotImplementedError: StructuredTool does not support sync invocation.`
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage
from langgraph.config import get_config
from langgraph.runtime import get_runtime

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain.agents.middleware.types import ToolCallRequest


def overrides(mw: AgentMiddleware, hook_name: str) -> bool:
    """True if `mw` actually implements `hook_name` (base default raises, not no-ops)."""
    return getattr(type(mw), hook_name) is not getattr(AgentMiddleware, hook_name)


def hook_accepts_config(mw: AgentMiddleware, hook_name: str) -> bool:
    """True if `mw`'s override of `hook_name` declares a `config` parameter.

    `AgentMiddleware`'s base hooks take only `(state, runtime)`, but some
    deepagents middleware (`SkillsMiddleware`/`MemoryMiddleware`'s
    `before_agent`) override with an extra `config: RunnableConfig` param —
    calling those without it raises `TypeError`.
    """
    return "config" in inspect.signature(getattr(type(mw), hook_name)).parameters


def run_state_hooks(
    middlewares: Sequence[AgentMiddleware], hook_name: str, state: dict[str, Any]
) -> dict[str, Any]:
    """Run a hook (before_agent/before_model/after_model) across middlewares, merging updates."""
    runtime = get_runtime()
    updates: dict[str, Any] = {}
    for mw in middlewares:
        if not overrides(mw, hook_name):
            continue
        kwargs = {"config": get_config()} if hook_accepts_config(mw, hook_name) else {}
        result = getattr(mw, hook_name)({**state, **updates}, runtime, **kwargs)
        if result:
            updates.update(result)
    return updates


async def arun_state_hooks(
    middlewares: Sequence[AgentMiddleware], hook_name: str, state: dict[str, Any]
) -> dict[str, Any]:
    """Async twin of `run_state_hooks`: prefer a middleware's `a<hook>` override
    (awaited), fall back to its sync override. Used by the async graph path so a
    hook never forces a sync call into the async-only checkpointer."""
    runtime = get_runtime()
    ahook = f"a{hook_name}"
    updates: dict[str, Any] = {}
    for mw in middlewares:
        if overrides(mw, ahook):
            name = ahook
            result = getattr(mw, name)(
                {**state, **updates},
                runtime,
                **({"config": get_config()} if hook_accepts_config(mw, name) else {}),
            )
            result = await result
        elif overrides(mw, hook_name):
            name = hook_name
            result = getattr(mw, name)(
                {**state, **updates},
                runtime,
                **({"config": get_config()} if hook_accepts_config(mw, name) else {}),
            )
        else:
            continue
        if result:
            updates.update(result)
    return updates


def compose_wrap_model_call(
    middlewares: Sequence[AgentMiddleware], base_handler
) -> Any:
    """Chain `wrap_model_call` hooks: first middleware in the list becomes outermost."""
    chain = base_handler
    for mw in reversed([m for m in middlewares if overrides(m, "wrap_model_call")]):

        def step(request: ModelRequest, _next=chain, _mw=mw) -> ModelResponse:
            return _mw.wrap_model_call(request, _next)

        chain = step
    return chain


def compose_awrap_model_call(
    middlewares: Sequence[AgentMiddleware], abase_handler
) -> Any:
    """Async twin of `compose_wrap_model_call` — chains `awrap_model_call`."""
    chain = abase_handler
    for mw in reversed([m for m in middlewares if overrides(m, "awrap_model_call")]):

        async def step(request: ModelRequest, _next=chain, _mw=mw) -> ModelResponse:
            return await _mw.awrap_model_call(request, _next)

        chain = step
    return chain


def compose_wrap_tool_call(middlewares: Sequence[AgentMiddleware]):
    """Chain `wrap_tool_call` hooks; `None` if none defined, so `ToolNode` uses its default."""
    wrapping = [m for m in middlewares if overrides(m, "wrap_tool_call")]
    if not wrapping:
        return None

    def composed(request: ToolCallRequest, handler):
        chain = handler
        for mw in reversed(wrapping):

            def step(req: ToolCallRequest, _next=chain, _mw=mw):
                return _mw.wrap_tool_call(req, _next)

            chain = step
        return chain(request)

    return composed


def compose_awrap_tool_call(middlewares: Sequence[AgentMiddleware]):
    """Async twin of `compose_wrap_tool_call`, passed to `ToolNode` as
    `awrap_tool_call`. Without it, once *any* middleware defines a sync
    `wrap_tool_call`, `ToolNode`'s async path falls back to that sync wrapper
    plus a sync tool executor — which runs async-only tools and any nested
    subagent graph (sharing the async checkpointer) synchronously on the
    event loop thread, raising `AsyncSqliteSaver` / `StructuredTool` errors.
    Passing this alongside `compose_wrap_tool_call` keeps `ToolNode` on its
    real async path regardless of which middleware in the stack defines
    which hook."""
    wrapping = [m for m in middlewares if overrides(m, "awrap_tool_call")]
    if not wrapping:
        return None

    async def composed(request: ToolCallRequest, handler):
        chain = handler
        for mw in reversed(wrapping):

            async def step(req: ToolCallRequest, _next=chain, _mw=mw):
                return await _mw.awrap_tool_call(req, _next)

            chain = step
        return await chain(request)

    return composed


def normalize_model_result(result) -> ModelResponse:
    """`wrap_model_call` handlers may return `ModelResponse | AIMessage | ExtendedModelResponse`."""
    if isinstance(result, AIMessage):
        return ModelResponse(result=[result])
    if isinstance(result, ExtendedModelResponse):
        # `.command` is intentionally dropped — see design doc.
        return result.model_response
    return result
