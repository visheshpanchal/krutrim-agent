"""Filesystem locations a sandbox needs, resolved from `AppSettings`.

Kept here (not in `krutrim_agents_core.builder`) so the sandbox-profile
factory can build harness routes without importing the graph builder. Mirrors
the layout `krutrim_agent_management.storage.local` writes on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from krutrim_agent_management.config import settings


def session_workspace_dir(session_id: str) -> Path:
    """`<home_root>/sessions/<session_id>/workspace` — the same bytes on
    disk that `SandboxRegistry.get_or_create` roots its `FilesystemBackend`
    at, and that RAG / the sessions file API read through `Storage`."""
    return settings.home_root / "sessions" / session_id / "workspace"


@dataclass(frozen=True)
class HarnessPaths:
    """Read-only host directories mounted into every agent sandbox: shared
    skills, this profile's skills, and this profile's long-term memory."""

    common_skills_dir: Path
    skills_root: Path
    memory_root: Path

    @classmethod
    def from_settings(cls) -> HarnessPaths:
        return cls(
            common_skills_dir=settings.common_skills_dir,
            skills_root=settings.skills_dir,
            memory_root=settings.memory_dir,
        )

    def agent_skills_dir(self, agent_key: str) -> Path:
        return self.skills_root / agent_key

    def agent_memory_dir(self, agent_key: str) -> Path:
        return self.memory_root / agent_key
