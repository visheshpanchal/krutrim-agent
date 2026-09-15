from __future__ import annotations

from deepagents.backends.filesystem import FilesystemBackend
from krutrim_agent_backend.chat.graph import build_chat_graph
from langchain_core.language_models import GenericFakeChatModel


def _model() -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([]))


def test_build_chat_graph_without_backend_has_no_filesystem_tools():
    """Today's callers (e.g. `sessions_routes.py`'s read-only `aget_state()`
    caller) pass no `backend` — this must stay a tool-free compile."""
    graph = build_chat_graph(_model())

    assert "tools" not in graph.nodes


def test_build_chat_graph_with_backend_adds_filesystem_tools(tmp_path):
    """`chat_routes.py` passes the session's sandboxed workspace backend
    explicitly — that opts the graph into `write_file`/`read_file`/etc."""
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    graph = build_chat_graph(_model(), backend=backend)

    tool_names = set(graph.nodes["tools"].bound.tools_by_name)
    assert {
        "write_file",
        "read_file",
        "edit_file",
        "ls",
        "glob",
        "grep",
        "delete",
    } <= tool_names


def test_build_chat_graph_tools_param_still_merged_alongside_filesystem_tools(tmp_path):
    from langchain_core.tools import tool

    @tool
    def _dummy(x: str) -> str:
        """A dummy tool used only to prove `tools=` still reaches the graph."""
        return x

    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    graph = build_chat_graph(_model(), tools=[_dummy], backend=backend)

    tool_names = set(graph.nodes["tools"].bound.tools_by_name)
    assert "_dummy" in tool_names
    assert "write_file" in tool_names
