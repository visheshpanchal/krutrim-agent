"""`JsonConfigStore` — one JSON file under `<home_root>/users/<user_id>/`,
holding a single pydantic model, read with an mtime cache and written
atomically at `0600`.

Used for the runtime config files that are **not** environment-backed and are
managed entirely from the app: `mcp.json` (`mcp_config.py`) and
`credentials.json` (`credentials_config.py`). `config.json` (the `UserSettings`
tier) has its own bespoke handling in `config.py` — this is the same idea,
generalised, for the free-form stores.

Every call takes the `user_id` whose file to act on; the directory is resolved
fresh from `AppSettings.home_root_path(user_id)` so `settings.set_home_root()`
(tests, a desktop shell) repoints every store. The mtime cache is keyed by the
resolved path, so alternating users don't evict each other.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar

from krutrim_agent_utils import atomic_write_json
from loguru import logger
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def _home_root(user_id: str) -> Path:
    # Lazy import: `config` must not import this module back.
    from krutrim_agent_management.config import settings

    return settings.home_dir_path(user_id)


class JsonConfigStore(Generic[ModelT]):
    """A single validated JSON document at `<home_root>/users/<user_id>/<filename>`.

    `get(user_id)` returns the parsed model (an all-defaults instance when the
    file is absent, empty, malformed, or fails validation — a warning is
    logged, never an exception). `replace()` / `mutate()` write the whole
    document back atomically with `0600` permissions.
    """

    def __init__(
        self,
        filename: str,
        model_cls: type[ModelT],
        dir_getter: Callable[[str], Path] = _home_root,
    ) -> None:
        self._filename = filename
        self._model_cls = model_cls
        self._dir_getter = dir_getter
        self._lock = RLock()
        # Keyed by resolved path (per-user), value = (parsed model, mtime seen).
        self._cache: dict[Path, tuple[ModelT, int | None]] = {}

    def path(self, user_id: str) -> Path:
        return self._dir_getter(user_id) / self._filename

    def _mtime(self, path: Path) -> int | None:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def _parse(self, path: Path) -> ModelT:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return self._model_cls()
        except OSError as exc:
            logger.warning("Ignoring unreadable {} ({})", path, exc)
            return self._model_cls()
        if not text:
            return self._model_cls()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Ignoring malformed {} ({})", path, exc)
            return self._model_cls()
        if not isinstance(data, dict):
            logger.warning("Ignoring {}: expected a JSON object", path)
            return self._model_cls()
        try:
            return self._model_cls.model_validate(data)
        except ValidationError as exc:
            logger.warning("Ignoring invalid values in {} ({})", path, exc)
            return self._model_cls()

    def get(self, user_id: str) -> ModelT:
        path = self.path(user_id)
        with self._lock:
            mtime = self._mtime(path)
            cached = self._cache.get(path)
            if cached is None or cached[1] != mtime:
                model = self._parse(path)
                self._cache[path] = (model, mtime)
                return model
            return cached[0]

    def _write(self, path: Path, model: ModelT) -> None:
        atomic_write_json(path, model.model_dump(mode="json"))
        try:
            os.chmod(path, 0o600)
        except OSError:  # e.g. restrictive Windows FS — best effort
            pass
        self._cache[path] = (model, self._mtime(path))

    def replace(self, user_id: str, model: ModelT) -> ModelT:
        """Write `model` as the whole document (re-validated first)."""
        with self._lock:
            validated = self._model_cls.model_validate(model.model_dump())
            self._write(self.path(user_id), validated)
            return validated

    def mutate(self, user_id: str, fn: Callable[[ModelT], ModelT]) -> ModelT:
        """Read the current document, apply `fn` to a deep copy, re-validate,
        and write the result — all under the store lock."""
        with self._lock:
            updated = fn(self.get(user_id).model_copy(deep=True))
            return self.replace(user_id, updated)

    def reload(self, user_id: str) -> ModelT:
        with self._lock:
            self._cache.pop(self.path(user_id), None)
            return self.get(user_id)
