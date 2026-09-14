from enum import StrEnum


class RetrivalStrategy(StrEnum):
    vector_only = "vector_only"
    hybrid = "hybrid"


class SandboxProfileType(StrEnum):
    """The sandbox profile to use for the agent."""

    default = "default"
    local_exec = "local-exec"


class SandboxFilesPolicy(StrEnum):
    """The sandbox files policy to use for the agent.
    sandbox_files_policy:
        "auto"      — the file tools write freely under /workspace (default)
        "read_only" — write_file / edit_file / delete are refused
        "edit_only" — writes allowed only under sandbox_write_paths
        "interrupt" — every write_file / edit_file / delete pauses for a
                    human approve/reject before it runs
    """

    auto = "auto"
    read_only = "read_only"
    edit_only = "edit_only"
    interrupt = "interrupt"


class ContextManagementStrategy(StrEnum):
    """The context management strategy to use for the agent.
    "off"       — nothing (default)
    "trim"      — clears the oldest tool outputs once the window fills.
    "summarize" — replaces old messages with an LLM-written summary once the
                    running message total passes `..._trigger_tokens`, keeping
                    the last `..._keep_messages`.
    "rag"       — reserved; not implemented yet, falls back to "summarize".
    """

    off = "off"
    trim = "trim"
    summarize = "summarize"
    rag = "rag"
