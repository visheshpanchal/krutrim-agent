"""Celery task wrappers thread the `user_id` the dispatching route passes
straight into their `*_once` core, defaulting to `LOCAL_USER_ID`.
"""

from __future__ import annotations

import pytest
from krutrim_agent_celery.tasks import precompute_embeddings as pe_mod
from krutrim_agent_celery.tasks import process_rag_document as prd_mod


class _Stop(Exception):
    pass


def _capture_user_id(seen: list[str]):
    def _fake_once(*args, **kwargs):
        seen.append(kwargs["user_id"])
        raise _Stop()

    return _fake_once


def test_process_rag_document_passes_user_id_through(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(prd_mod, "process_rag_document_once", _capture_user_id(seen))
    # neutralise the Redis lock / pubsub the wrapper sets up before the core call
    monkeypatch.setattr(
        prd_mod.redis.Redis, "from_url", staticmethod(lambda *a, **k: _FakeRedis())
    )
    monkeypatch.setattr(prd_mod, "RedisPubSubBackend", lambda *a, **k: object())

    with pytest.raises(_Stop):
        prd_mod.process_rag_document("sess", "doc", "f.txt", "Title", "alice")
    assert seen == ["alice"]


def test_precompute_embeddings_passes_user_id_through(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(pe_mod, "precompute_embeddings_once", _capture_user_id(seen))
    monkeypatch.setattr(pe_mod, "RedisPubSubBackend", lambda *a, **k: object())

    with pytest.raises(_Stop):
        pe_mod.precompute_embeddings("sess", ["a.txt"], "bob")
    assert seen == ["bob"]


def test_precompute_embeddings_defaults_to_local(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(pe_mod, "precompute_embeddings_once", _capture_user_id(seen))
    monkeypatch.setattr(pe_mod, "RedisPubSubBackend", lambda *a, **k: object())

    with pytest.raises(_Stop):
        pe_mod.precompute_embeddings("sess", ["a.txt"])
    assert seen == ["local"]


class _FakeRedis:
    def lock(self, *a, **k):
        return _FakeLock()


class _FakeLock:
    def acquire(self, *a, **k):
        return True

    def release(self):
        pass
