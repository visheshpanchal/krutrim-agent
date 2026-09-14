from __future__ import annotations

import pytest
from krutrim_agent_management import LOCAL_USER_ID, LocalStorage
from krutrim_agent_management.config import ServerSettings


def test_default_home_root_is_under_home(monkeypatch):
    # `settings` is the module singleton the `_hermetic_krutrim_home` autouse
    # fixture always points at a throwaway tmp dir (so no test ever touches the
    # developer's real ~/.krutrim_agent) — so it can't be used to observe the
    # true default here. Build an independent instance instead.
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("KRUTRIM_AGENT_HOME_ROOT", raising=False)
    fresh = ServerSettings()
    assert "krutrim_agent" in str(fresh.home_root).lower()


# -- projects -----------------------------------------------------------------


async def test_create_project_creates_row_and_dir(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Research on X", "some info")
    assert project.project_title == "Research on X"
    assert project.project_information == "some info"
    assert storage.project_dir(project.project_id).is_dir()
    assert (tmp_path / "project.db").is_file()


async def test_get_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.get_project(LOCAL_USER_ID, "does-not-exist")


async def test_list_projects(tmp_path):
    storage = LocalStorage(tmp_path)
    await storage.create_project(LOCAL_USER_ID, "A")
    await storage.create_project(LOCAL_USER_ID, "B")
    titles = {p.project_title for p in await storage.list_projects(LOCAL_USER_ID)}
    assert titles == {"A", "B"}


async def test_update_project_partial_update(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Original", "orig info")
    updated = await storage.update_project(LOCAL_USER_ID, project.project_id, project_title="Renamed")
    assert updated.project_title == "Renamed"
    assert updated.project_information == "orig info"  # untouched


async def test_delete_project_removes_row_and_dir(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Gone soon")
    project_dir = storage.project_dir(project.project_id)
    await storage.delete_project(LOCAL_USER_ID, project.project_id)
    with pytest.raises(KeyError):
        await storage.get_project(LOCAL_USER_ID, project.project_id)
    assert not project_dir.exists()


# -- agents ---------------------------------------------------------------


async def test_create_agent_row(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    agent = await storage.create_agent(LOCAL_USER_ID,
        project.project_id, "research", "Business Analysis"
    )
    assert agent.project_id == project.project_id
    assert agent.agent_key == "research"
    assert agent.display_name == "Business Analysis"
    assert agent.sandbox_sharing is None  # inherits project default


async def test_create_agent_for_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.create_agent(LOCAL_USER_ID, "nope", "research", "X")


async def test_list_agents_scoped_to_project(tmp_path):
    storage = LocalStorage(tmp_path)
    project_a = await storage.create_project(LOCAL_USER_ID, "A")
    await storage.create_agent(LOCAL_USER_ID, project_a.project_id, "research", "A1")
    await storage.create_agent(LOCAL_USER_ID, project_a.project_id, "research", "A2")

    assert {
        a.display_name for a in await storage.list_agents(LOCAL_USER_ID, project_a.project_id)
    } == {"A1", "A2"}


async def test_update_agent_renames(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "Original")
    updated = await storage.update_agent(LOCAL_USER_ID, agent.agent_id, display_name="Renamed")
    assert updated.display_name == "Renamed"


async def test_delete_agent_cascades_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    session = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)

    await storage.delete_agent(LOCAL_USER_ID, agent.agent_id)

    with pytest.raises(KeyError):
        await storage.get_agent(LOCAL_USER_ID, agent.agent_id)
    with pytest.raises(KeyError):
        await storage.get_session(LOCAL_USER_ID, session.session_id)


async def test_delete_project_cascades_agents_and_their_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    session = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)

    await storage.delete_project(LOCAL_USER_ID, project.project_id)

    with pytest.raises(KeyError):
        await storage.get_agent(LOCAL_USER_ID, agent.agent_id)
    with pytest.raises(KeyError):
        await storage.get_session(LOCAL_USER_ID, session.session_id)


# -- chats ------------------------------------------------------------------


async def test_create_standalone_chat(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID,
        "General", "openrouter", "deepseek/deepseek-v4-flash-0731"
    )
    assert chat.project_id is None
    assert chat.display_name == "General"


async def test_create_project_scoped_chat(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    chat = await storage.create_chat(LOCAL_USER_ID,
        "Q&A",
        "openrouter",
        "deepseek/deepseek-v4-flash-0731",
        project_id=project.project_id,
    )
    assert chat.project_id == project.project_id


async def test_create_chat_for_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.create_chat(LOCAL_USER_ID, "X", "openrouter", "m", project_id="nope")


async def test_list_chats_standalone_vs_project_scoped(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    await storage.create_chat(LOCAL_USER_ID, "Standalone", "openrouter", "m")
    await storage.create_chat(LOCAL_USER_ID,
        "Scoped", "openrouter", "m", project_id=project.project_id
    )

    assert {c.display_name for c in await storage.list_chats(LOCAL_USER_ID, None)} == {"Standalone"}
    assert {c.display_name for c in await storage.list_chats(LOCAL_USER_ID, project.project_id)} == {
        "Scoped"
    }


async def test_move_chat_into_and_out_of_project(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)
    assert session.project_id is None

    moved = await storage.move_chat(LOCAL_USER_ID, chat.chat_id, project_id=project.project_id)
    assert moved.project_id == project.project_id
    # Sessions already under the chat are re-scoped to the new project too.
    assert (
        await storage.get_session(LOCAL_USER_ID, session.session_id)
    ).project_id == project.project_id

    detached = await storage.move_chat(LOCAL_USER_ID, chat.chat_id, project_id=None)
    assert detached.project_id is None
    assert (await storage.get_session(LOCAL_USER_ID, session.session_id)).project_id is None


async def test_move_chat_unknown_target_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    with pytest.raises(KeyError):
        await storage.move_chat(LOCAL_USER_ID, chat.chat_id, project_id="nope")


async def test_delete_chat_cascades_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)

    await storage.delete_chat(LOCAL_USER_ID, chat.chat_id)

    with pytest.raises(KeyError):
        await storage.get_chat(LOCAL_USER_ID, chat.chat_id)
    with pytest.raises(KeyError):
        await storage.get_session(LOCAL_USER_ID, session.session_id)


async def test_delete_project_cascades_chats_and_their_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    chat = await storage.create_chat(LOCAL_USER_ID,
        "C", "openrouter", "m", project_id=project.project_id
    )
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)

    await storage.delete_project(LOCAL_USER_ID, project.project_id)

    with pytest.raises(KeyError):
        await storage.get_chat(LOCAL_USER_ID, chat.chat_id)
    with pytest.raises(KeyError):
        await storage.get_session(LOCAL_USER_ID, session.session_id)


# -- agent memory ---------------------------------------------------------


async def test_memory_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Mem test")
    assert await storage.read_memory(LOCAL_USER_ID, project.project_id) == ""
    await storage.write_memory(LOCAL_USER_ID, project.project_id, "# Memory\nlearned something")
    assert (
        await storage.read_memory(LOCAL_USER_ID, project.project_id) == "# Memory\nlearned something"
    )


async def test_memory_for_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.read_memory(LOCAL_USER_ID, "nope")


# -- sessions -----------------------------------------------------------------


async def test_session_lifecycle_under_agent(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Sessions")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    session = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)
    assert session.owner_type == "agent"
    assert session.owner_id == agent.agent_id
    assert session.project_id == project.project_id
    assert await storage.get_session(LOCAL_USER_ID, session.session_id) == session
    assert [
        s.session_id for s in await storage.list_sessions(LOCAL_USER_ID, "agent", agent.agent_id)
    ] == [session.session_id]
    await storage.delete_session(LOCAL_USER_ID, session.session_id)
    with pytest.raises(KeyError):
        await storage.get_session(LOCAL_USER_ID, session.session_id)


async def test_session_under_standalone_chat_has_no_project(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)
    assert session.owner_type == "chat"
    assert session.project_id is None


async def test_create_session_for_unknown_owner_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.create_session(LOCAL_USER_ID, "agent", "nope")


async def test_update_session_renames(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)
    updated = await storage.update_session(LOCAL_USER_ID,
        session.session_id, display_name="Scoped run"
    )
    assert updated.display_name == "Scoped run"


async def test_checkpoint_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)
    assert await storage.read_checkpoint(session.session_id) is None
    await storage.write_checkpoint(session.session_id, {"step": 3})
    assert await storage.read_checkpoint(session.session_id) == {"step": 3}


async def test_usage_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)
    assert await storage.read_usage(session.session_id) is None
    await storage.write_usage(session.session_id, {"input_tokens": 100})
    assert await storage.read_usage(session.session_id) == {"input_tokens": 100}


# -- cache (still project-scoped) --------------------------------------------


async def test_cache_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Cache")
    assert await storage.cache_get(project.project_id, "search", "query:foo") is None
    await storage.cache_set(
        project.project_id, "search", "query:foo", {"results": [1, 2, 3]}
    )
    assert await storage.cache_get(project.project_id, "search", "query:foo") == {
        "results": [1, 2, 3]
    }


async def test_cache_is_namespaced(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Cache NS")
    await storage.cache_set(project.project_id, "mcp", "same-key", "mcp-value")
    await storage.cache_set(project.project_id, "rag", "same-key", "rag-value")
    assert await storage.cache_get(project.project_id, "mcp", "same-key") == "mcp-value"
    assert await storage.cache_get(project.project_id, "rag", "same-key") == "rag-value"


async def test_reopening_storage_preserves_data(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Persisted")
    await storage.write_memory(LOCAL_USER_ID, project.project_id, "remember me")

    reopened = LocalStorage(tmp_path)
    assert (await reopened.get_project(LOCAL_USER_ID, project.project_id)).project_title == "Persisted"
    assert await reopened.read_memory(LOCAL_USER_ID, project.project_id) == "remember me"


# -- sandbox sharing policy ------------------------------------------------


async def test_new_project_and_session_default_to_isolated(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Defaults")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    session = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)
    assert project.sandbox_sharing == "isolated"
    assert project.sandbox_idle_timeout_seconds is None
    assert project.sandbox_resource_overrides is None
    assert agent.sandbox_sharing is None
    assert session.sandbox_sharing == "isolated"
    assert session.attached_to_session_id is None
    assert session.linked_session_ids == []


async def test_update_project_sandbox_policy_partial_update(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Policy")
    updated = await storage.update_project_sandbox_policy(LOCAL_USER_ID,
        project.project_id, sharing="project-shared", idle_timeout_seconds=120
    )
    assert updated.sandbox_sharing == "project-shared"
    assert updated.sandbox_idle_timeout_seconds == 120
    assert updated.sandbox_resource_overrides is None  # untouched

    with_overrides = await storage.update_project_sandbox_policy(LOCAL_USER_ID,
        project.project_id, resource_overrides={"memory_mb": 1024}
    )
    assert with_overrides.sandbox_sharing == "project-shared"  # untouched by this call
    assert with_overrides.sandbox_resource_overrides == {"memory_mb": 1024}


async def test_update_project_sandbox_policy_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.update_project_sandbox_policy(LOCAL_USER_ID, "nope", sharing="isolated")


async def test_update_agent_sandbox_policy_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "P")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    updated = await storage.update_agent_sandbox_policy(LOCAL_USER_ID,
        agent.agent_id, sharing="project-shared"
    )
    assert updated.sandbox_sharing == "project-shared"


async def test_update_chat_sandbox_policy_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    updated = await storage.update_chat_sandbox_policy(LOCAL_USER_ID,
        chat.chat_id, sharing="project-shared"
    )
    assert (
        updated.sandbox_sharing == "project-shared"
    )  # stored even though project_id is None


async def test_update_session_sandbox_policy_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Session Policy")
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    session_a = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)
    session_b = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)

    updated = await storage.update_session_sandbox_policy(LOCAL_USER_ID,
        session_a.session_id, attached_to_session_id=session_b.session_id
    )
    assert updated.attached_to_session_id == session_b.session_id
    assert updated.sandbox_sharing == "isolated"  # untouched

    linked = await storage.update_session_sandbox_policy(LOCAL_USER_ID,
        session_a.session_id,
        sharing="session-shared",
        linked_session_ids=[session_b.session_id],
    )
    assert linked.sandbox_sharing == "session-shared"
    assert linked.linked_session_ids == [session_b.session_id]
    assert (
        linked.attached_to_session_id == session_b.session_id
    )  # untouched by this call


async def test_update_session_sandbox_policy_unknown_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.update_session_sandbox_policy(LOCAL_USER_ID, "nope", sharing="isolated")


# -- session workspace -------------------------------------------------------


async def test_workspace_files_empty_for_fresh_session(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)
    assert await storage.read_workspace_files(LOCAL_USER_ID, session.session_id) == []
    assert await storage.read_workspace_file(LOCAL_USER_ID, session.session_id, "missing.txt") is None


async def test_sync_workspace_from_container_then_read(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(LOCAL_USER_ID, "C", "openrouter", "m")
    session = await storage.create_session(LOCAL_USER_ID, "chat", chat.chat_id)

    await storage.sync_workspace_from_container(LOCAL_USER_ID,
        session.session_id, [("notes.txt", b"hello"), ("sub/data.json", b'{"a": 1}')]
    )

    files = await storage.read_workspace_files(LOCAL_USER_ID, session.session_id)
    assert sorted(files) == ["notes.txt", "sub/data.json"]
    assert (
        await storage.read_workspace_file(LOCAL_USER_ID, session.session_id, "notes.txt") == b"hello"
    )


async def test_workspace_methods_for_unknown_session_raise(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.read_workspace_files(LOCAL_USER_ID, "nope")


async def test_reopening_storage_preserves_sandbox_policy(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project(LOCAL_USER_ID, "Persisted Policy")
    await storage.update_project_sandbox_policy(LOCAL_USER_ID,
        project.project_id, sharing="project-shared"
    )
    agent = await storage.create_agent(LOCAL_USER_ID, project.project_id, "research", "A")
    session = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)
    await storage.update_session_sandbox_policy(LOCAL_USER_ID,
        session.session_id, linked_session_ids=["peer-1"]
    )

    reopened = LocalStorage(tmp_path)
    reopened_project = await reopened.get_project(LOCAL_USER_ID, project.project_id)
    reopened_session = await reopened.get_session(LOCAL_USER_ID, session.session_id)
    assert reopened_project.sandbox_sharing == "project-shared"
    assert reopened_session.linked_session_ids == ["peer-1"]
