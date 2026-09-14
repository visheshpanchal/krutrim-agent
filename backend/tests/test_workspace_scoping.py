"""Per-user workspace: `project.db` / `agents.db` / `chats.db` /
`sessions.db` rows carry a `user_id`, passed as the first argument to every
`LocalStorage` call, and `get_*` / `list_*` filter on it. No cross-user
visibility.
"""

from __future__ import annotations

import sqlite3

import pytest
from krutrim_agent_management import LOCAL_USER_ID, LocalStorage


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path)


async def test_create_stamps_the_passed_user(storage):
    p = await storage.create_project("alice", "P")
    agent = await storage.create_agent("alice", p.project_id, "research", "R")
    chat = await storage.create_chat(
        "alice", "C", "openai", "gpt", project_id=p.project_id
    )
    sess = await storage.create_session("alice", "agent", agent.agent_id)
    assert p.user_id == agent.user_id == chat.user_id == sess.user_id == "alice"


async def test_default_owner_sentinel(storage):
    p = await storage.create_project(LOCAL_USER_ID, "P")
    assert p.user_id == LOCAL_USER_ID


async def test_projects_are_isolated_per_user(storage):
    pa = await storage.create_project("alice", "A")
    pb = await storage.create_project("bob", "B")

    assert [p.project_id for p in await storage.list_projects("bob")] == [pb.project_id]
    with pytest.raises(KeyError):
        await storage.get_project("bob", pa.project_id)

    assert [p.project_id for p in await storage.list_projects("alice")] == [
        pa.project_id
    ]
    with pytest.raises(KeyError):
        await storage.get_project("alice", pb.project_id)


async def test_cannot_mutate_another_users_project(storage):
    pa = await storage.create_project("alice", "A")
    with pytest.raises(KeyError):
        await storage.update_project("bob", pa.project_id, project_title="hijack")
    with pytest.raises(KeyError):
        await storage.delete_project("bob", pa.project_id)
    with pytest.raises(KeyError):
        await storage.update_project_sandbox_policy(
            "bob", pa.project_id, sharing="project-shared"
        )


async def test_agents_chats_sessions_isolated_per_user(storage):
    p = await storage.create_project("alice", "A")
    agent = await storage.create_agent("alice", p.project_id, "research", "R")
    chat = await storage.create_chat(
        "alice", "C", "openai", "gpt", project_id=p.project_id
    )
    sess = await storage.create_session("alice", "agent", agent.agent_id)

    with pytest.raises(KeyError):
        await storage.get_agent("bob", agent.agent_id)
    with pytest.raises(KeyError):
        await storage.get_chat("bob", chat.chat_id)
    with pytest.raises(KeyError):
        await storage.get_session("bob", sess.session_id)
    with pytest.raises(KeyError):
        await storage.delete_session("bob", sess.session_id)
    assert await storage.list_agents("bob", p.project_id) == []
    assert await storage.list_sessions("bob", "agent", agent.agent_id) == []


async def test_bob_cannot_create_in_alices_project(storage):
    p = await storage.create_project("alice", "A")
    with pytest.raises(KeyError):
        await storage.create_agent("bob", p.project_id, "research", "R")
    with pytest.raises(KeyError):
        await storage.create_chat("bob", "C", "openai", "gpt", project_id=p.project_id)


async def test_sandbox_registry_refuses_a_foreign_session(storage):
    from krutrim_agent_sandbox.registry import SandboxRegistry

    p = await storage.create_project("alice", "A")
    agent = await storage.create_agent("alice", p.project_id, "research", "R")
    sess = await storage.create_session("alice", "agent", agent.agent_id)

    registry = SandboxRegistry(store=storage)
    with pytest.raises(KeyError):
        await registry.get_or_create("bob", sess.session_id)


def test_startup_guard_rejects_a_pre_scoping_db(tmp_path):
    conn = sqlite3.connect(tmp_path / "project.db")
    conn.execute(
        "CREATE TABLE projects ("
        "project_id TEXT PRIMARY KEY, project_title TEXT NOT NULL, "
        "project_information TEXT NOT NULL DEFAULT '', "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="predates per-user scoping"):
        LocalStorage(tmp_path)
