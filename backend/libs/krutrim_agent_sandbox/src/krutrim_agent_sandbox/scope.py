from __future__ import annotations

from krutrim_agent_management.models import OwnerType
from pydantic import BaseModel


class ProjectInfo(BaseModel):
    """Which project/agent/session a graph build belongs to.

    `owner_type`/`owner_id` follow `SessionInfo` (an `Agent` or a `Chat` owns
    the session; a session never belongs to a `Project` directly). `project_id`
    is `None` for a project-less standalone chat. `agent_key` is the registered
    profile key, `None` when the owner is a chat.
    """

    session_id: str
    owner_type: OwnerType = "agent"
    owner_id: str
    project_id: str | None = None
    agent_key: str | None = None
