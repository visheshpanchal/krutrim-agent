from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.api import sessions_routes
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_management import LOCAL_USER_ID, LocalStorage


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.include_router(sessions_router)
    return TestClient(app)


def _create_session(client: TestClient) -> str:
    storage = client.app.state.storage

    async def _create():
        project = await storage.create_project(LOCAL_USER_ID, "P")
        agent = await storage.create_agent(
            LOCAL_USER_ID, project.project_id, "research", "Test Agent"
        )
        session = await storage.create_session(LOCAL_USER_ID, "agent", agent.agent_id)
        return session.session_id

    return asyncio.run(_create())


def _write_workspace(
    client: TestClient, session_id: str, files: list[tuple[str, bytes]]
) -> None:
    storage = client.app.state.storage
    asyncio.run(storage.sync_workspace_from_container(LOCAL_USER_ID, session_id, files))


def test_lists_workspace_files_with_size_and_modified(client):
    session_id = _create_session(client)
    _write_workspace(
        client,
        session_id,
        [("report.md", b"# Tata Motors\n\nbody"), ("figs/chart.txt", b"x" * 10)],
    )

    body = client.get(f"/api/sessions/{session_id}/files").json()
    by_path = {f["path"]: f for f in body["files"]}

    assert set(by_path) == {"report.md", "figs/chart.txt"}
    assert by_path["report.md"]["size"] == len(b"# Tata Motors\n\nbody")
    assert by_path["figs/chart.txt"]["size"] == 10
    # `modified` round-trips as an ISO 8601 timestamp
    assert datetime.fromisoformat(by_path["report.md"]["modified"])


def test_lists_empty_for_a_fresh_session(client):
    session_id = _create_session(client)
    assert client.get(f"/api/sessions/{session_id}/files").json() == {"files": []}


def test_download_returns_bytes_with_attachment_headers(client):
    session_id = _create_session(client)
    _write_workspace(client, session_id, [("report.md", b"# Heading\n\ncontent")])

    res = client.get(f"/api/sessions/{session_id}/files/report.md")

    assert res.status_code == 200
    assert res.content == b"# Heading\n\ncontent"
    assert res.headers["content-type"].startswith("text/markdown")
    assert res.headers["content-disposition"] == 'attachment; filename="report.md"'


def test_download_reads_a_nested_path(client):
    session_id = _create_session(client)
    _write_workspace(client, session_id, [("a/b/c.txt", b"deep")])

    res = client.get(f"/api/sessions/{session_id}/files/a/b/c.txt")
    assert res.status_code == 200
    assert res.content == b"deep"
    assert res.headers["content-disposition"] == 'attachment; filename="c.txt"'


def test_download_missing_file_returns_404(client):
    session_id = _create_session(client)
    assert client.get(f"/api/sessions/{session_id}/files/nope.md").status_code == 404


def test_download_rejects_parent_traversal(client):
    session_id = _create_session(client)
    # `%2E%2E%2F` -> `../` in the decoded path param; must not collapse to a
    # sibling route or read outside the workspace.
    res = client.get(f"/api/sessions/{session_id}/files/%2E%2E%2F%2E%2E%2Fsecret.txt")
    assert res.status_code == 400


def test_download_rejects_absolute_path(client):
    session_id = _create_session(client)
    res = client.get(f"/api/sessions/{session_id}/files/%2Fetc%2Fpasswd")
    assert res.status_code == 400


def test_download_rejects_symlink_escape(client, tmp_path):
    session_id = _create_session(client)
    _write_workspace(
        client, session_id, [("keep.txt", b"keep")]
    )  # materialises the dir

    secret = tmp_path / "outside-secret.txt"
    secret.write_bytes(b"top secret")
    workspace_root = client.app.state.storage.session_dir(session_id) / "workspace"
    (workspace_root / "escape.txt").symlink_to(secret)

    res = client.get(f"/api/sessions/{session_id}/files/escape.txt")
    assert res.status_code == 400


def test_unknown_session_returns_404(client):
    assert client.get("/api/sessions/nope/files").status_code == 404
    assert client.get("/api/sessions/nope/files/report.md").status_code == 404


def test_non_owning_user_returns_404(client, monkeypatch):
    session_id = _create_session(client)
    _write_workspace(client, session_id, [("report.md", b"mine")])

    monkeypatch.setattr(
        sessions_routes, "current_user_id", lambda _request: "someone-else"
    )

    assert client.get(f"/api/sessions/{session_id}/files").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/files/report.md").status_code == 404
