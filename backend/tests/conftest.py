"""Session-wide test setup.

faisslite (via faiss-cpu) and krutrim_agent_doc's docling parsers (via
torch) can both load into this one pytest process across different test
modules, and each links its own bundled OpenMP runtime. Loading both
natively aborts the process on macOS ("OMP: Error #15") unless
KMP_DUPLICATE_LIB_OK is set before either is first imported — but that alone
only silences the duplicate-init *check*; two OpenMP thread pools actually
running concurrently in one process can still segfault (observed running
the full suite, not just test_embeddings.py in isolation). Pinning both
libraries to a single thread removes the concurrent-execution case that
triggers it. Must be the first thing this file does, ahead of any test
module import that could pull in faiss or torch.
"""

from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
# The suite predates auth and hits routes with no token — run it with
# enforcement off by default. `test_auth*.py` re-enable it explicitly.
os.environ.setdefault("KRUTRIM_AGENT_AUTH_ENABLED", "false")

try:
    import faiss

    faiss.omp_set_num_threads(1)
except ImportError:
    pass

import pytest


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch):
    """The developer's real root `.env` is written for `docker compose` / manual
    dev use — e.g. `KRUTRIM_AGENT_VECTOR_STORE_BACKEND=qdrant` pointed at the
    compose network's `qdrant` host, `KRUTRIM_AGENT_RAG_INJECTION_ENABLED=true` —
    and must never leak into the suite, which assumes the code-level defaults
    (embedded faisslite, no RAG injection) unless a test opts in explicitly
    (e.g. `test_qdrant_vector_store.py`'s own `:memory:` override). Otherwise
    tests silently try to dial a real Qdrant server / embeddings API that only
    exists inside the compose network, failing with DNS/connection errors
    instead of running hermetically.

    Both layers matter: `ServerSettings`/`UserSettings` read `os.environ` first
    and then re-parse the `.env` file directly as a fallback, so clearing only
    one of the two leaves the polluted value in place.
    """
    from krutrim_agent_management.config import ServerSettings, UserSettings, settings

    for key in (
        "KRUTRIM_AGENT_VECTOR_STORE_BACKEND",
        "KRUTRIM_AGENT_QDRANT_URL",
        "KRUTRIM_AGENT_RAG_INJECTION_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(ServerSettings.model_config, "env_file", None)
    monkeypatch.setitem(UserSettings.model_config, "env_file", None)
    # The module-level `settings` singleton was already constructed (from the
    # real .env) before this fixture ever ran — patch its live fields too, the
    # same way the fixture below patches `home_root`.
    monkeypatch.setattr(settings, "vector_store_backend", "faisslite")
    monkeypatch.setattr(settings, "qdrant_url", None)


@pytest.fixture(autouse=True)
def _hermetic_krutrim_home(tmp_path_factory, monkeypatch):
    """Point `home_root` (`config.json`, `mcp.json`, `credentials.json`,
    `.jwt_secret`) and `home_root` (projects/sessions SQLite + `users.db`) at
    a throwaway dir per test, so nothing reads or writes the developer's real
    `~/.krutrim_agent/`. A test that needs its own `home_root` still
    overrides this one with its own `monkeypatch.setattr`."""
    from krutrim_agent_management.config import settings

    home = tmp_path_factory.mktemp("krutrim-home")
    monkeypatch.setattr(settings, "home_root", home)
    original_home_root = settings.base_home_root
    settings.set_home_root(home)
    try:
        yield home
    finally:
        settings.set_home_root(original_home_root)


@pytest.fixture
def authed_client(monkeypatch):
    """A `TestClient` for the full app with auth ENFORCED, pre-registered as an
    admin (the first user) and carrying its bearer token. Yields
    `(client, tokens)` where `tokens` is the register response's TokenPair."""
    from fastapi.testclient import TestClient
    from krutrim_agent_management.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True)

    from krutrim_agent_backend.main import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/auth/register",
        json={"username": "admin", "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    tokens = resp.json()["tokens"]
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    yield client, tokens
