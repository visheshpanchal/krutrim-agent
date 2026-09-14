"""The composed research-agent system prompt (`harness/prompts/research/` +
the shared fragments it pulls in), rendered through
`krutrim_agents.profiles.research.prompts.render_system_prompt`.

Guards that the real fragment tree stays valid (no broken include, cycle, or
undeclared `{token}`) and that the deliverable contract actually reaches the
composed prompt with the variable set unchanged.
"""

from __future__ import annotations

from krutrim_agents.profiles.research.prompts import render_system_prompt
from krutrim_agents_core.harness.prompts import prompt_library

_RENDER_KWARGS = {
    "user_request": "u",
    "conversation_context": "c",
    "research_state": "s",
    "known_information": "k",
    "unknown_information": "x",
    "available_tools": "t",
}

# The union of declared variables across `research_main` and everything it
# includes. A new fragment that adds a required variable would change this and
# break `render_system_prompt`, which passes exactly these keys.
_EXPECTED_VARIABLES = set(_RENDER_KWARGS)


def test_real_prompt_tree_builds_and_registers_the_deliverable_fragments():
    lib = prompt_library()  # raises on a broken include / cycle / undeclared token
    names = lib.names()
    assert "deliverables" in names
    assert "research_deliverable_protocol" in names


def test_research_main_variable_set_is_unchanged():
    required = prompt_library().required_variables(
        "research_main", scopes={"research_topology": "swarm_agent"}
    )
    assert required == _EXPECTED_VARIABLES


def test_rendered_prompt_carries_the_deliverable_contract():
    out = render_system_prompt(**_RENDER_KWARGS)

    # shared contract
    assert "write_file" in out
    assert "/workspace/" in out
    assert "Write the file first." in out
    # a different-format request is routed to the export skill
    assert "document-export" in out
    # research-specific tie-in to the hand-off marker
    assert "<research_deliverable>" in out
    assert "===FINAL_REPORT===" in out
