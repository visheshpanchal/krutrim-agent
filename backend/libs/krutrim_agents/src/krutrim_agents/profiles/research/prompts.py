from __future__ import annotations

from krutrim_agents_core.harness.prompts import prompt_library

registry = prompt_library()


def render_system_prompt(
    *,
    user_request: str,
    conversation_context: str,
    research_state: str,
    known_information: str,
    unknown_information: str,
    available_tools: str,
    topology: str = "swarm_agent",
) -> str:
    """Render the full research agent system prompt.

    `topology` selects which alternate execution-topology fragment fills the
    `{topology}` slot: one of `react_agent`, `planner_executor`, `swarm_agent`
    (the three `scope`s the `topology`-named prompt is registered under).
    """
    composed = registry.render(
        "research_main",
        scope="default",
        variables={
            "user_request": user_request,
            "conversation_context": conversation_context,
            "research_state": research_state,
            "known_information": known_information,
            "unknown_information": unknown_information,
            "available_tools": available_tools,
        },
        scopes={"research_topology": topology},
    )

    return composed
