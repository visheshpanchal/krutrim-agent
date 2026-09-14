"""Loads system prompts from `harness/prompts/<agent_key>/*.md`.

Two loaders live here, side by side:

* ``load_prompt(agent_key, name)`` — the original: one file, whole body, no
  header, no composition. Unchanged.
* ``PromptLibrary`` — a lightweight in-repo stand-in for the external
  ``promptstore`` package. A directory of headed ``.md`` fragments, keyed by
  ``(name, scope)``, that pull one another in by name and render from the
  leaves upward.

Fragment file format — exactly one prompt per ``.md`` file::

    <!--
    name: research_core
    scope: default
    description: optional one-liner
    variables:
      - user_request
      - available_tools
    -->
    The task is: {user_request}

    {topology}

* The header is an HTML comment at the very top of the file. ``name`` is
  required; ``scope`` defaults to ``"default"``; ``description`` is optional;
  ``variables`` is an optional ``- item`` list. Unknown header keys are ignored.
* Everything after the header comment is the body.
* ``{token}`` in the body is an identifier in braces, recognised only when it
  stands alone — at the start/end of the body, or with a space or newline on
  each side. If ``token`` is one of this fragment's declared ``variables`` it
  is a value slot filled at render time; otherwise it is an *include* of the
  fragment named ``token``, rendered and spliced in. A brace touching any
  other character is literal text: ``{"k": v}``, ``{ spaced }``,
  ``S{section_number}[.{slug}]`` and ``env={HOME}`` all pass through unchanged.
* ``(name, scope)`` is the primary key. Two files may share a ``name`` only
  with different ``scope`` values; the caller picks one per include at
  render time via ``scopes=``.

Memory model: constructing a ``PromptLibrary`` reads every fragment body once
to validate the whole set — malformed header, duplicate ``(name, scope)``,
an ``{include}`` naming no known fragment, or an unambiguous include cycle
all raise here — then discards the bodies. Only the headers and a small
per-fragment set of include names stay resident. ``render()`` re-reads the
few files in the tree it is composing and drops them again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from krutrim_agent_management.config import settings

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "DEFAULT_SCOPE",
    "PromptFormatError",
    "PromptHeader",
    "PromptLibrary",
    "PromptResolutionError",
    "PromptVariableError",
    "load_prompt",
    "prompt_library",
]


@cache
def load_prompt(agent_key: str, name: str) -> str:
    path = settings.prompts_dir(agent_key) / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file at {path}")
    return path.read_text(encoding="utf-8").strip()


# --------------------------------------------------------------------------
# PromptLibrary
# --------------------------------------------------------------------------

DEFAULT_SCOPE = "default"

_HEADER_RE = re.compile(r"\A\s*<!--(.*?)-->", re.DOTALL)
_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")
_TOKEN_RE = re.compile(r"(?<![^\n ])\{([A-Za-z_][A-Za-z0-9_]*)\}(?=[\n ]|$)")


class PromptFormatError(ValueError):
    """A fragment's header or on-disk layout is malformed, or two share a key."""


class PromptResolutionError(ValueError):
    """An include can't be resolved: unknown name, unresolved scope, or a cycle."""


class PromptVariableError(ValueError):
    """The variables passed to ``render()`` don't match what the tree declares."""


@dataclass(frozen=True)
class PromptHeader:
    name: str
    scope: str
    description: str
    variables: frozenset[str]


@dataclass(frozen=True)
class _Entry:
    path: Path
    header: PromptHeader
    include_names: frozenset[str]  # body tokens that aren't declared variables


def _dequote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _unique_tokens(body: str) -> list[str]:
    """Distinct ``{identifier}`` tokens in `body`, in first-seen order."""
    seen: dict[str, None] = {}
    for match in _TOKEN_RE.finditer(body):
        seen.setdefault(match.group(1), None)
    return list(seen)


def _fmt_key(key: tuple[str, str]) -> str:
    name, scope = key
    return repr(name) if scope == DEFAULT_SCOPE else f"{name!r} (scope {scope!r})"


def _split_header(text: str, path: Path) -> tuple[str, str]:
    """(header-comment-inner-text, body) — raises if the file has no header."""
    match = _HEADER_RE.match(text)
    if not match:
        raise PromptFormatError(
            f"{path}: expected an '<!-- ... -->' header comment at the top of the file"
        )
    return match.group(1), text[match.end() :].strip()


def _parse_header(text: str, path: Path) -> PromptHeader:
    """
    Return header of prompt file.
    """

    section, _ = _split_header(text, path)
    fields: dict[str, str] = {}
    variables: list[str] = []
    lines = section.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if ":" not in line:
            raise PromptFormatError(
                f"{path}: malformed header line (want 'key: value'): {line!r}"
            )
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "variables":
            if value:
                raise PromptFormatError(
                    f"{path}: 'variables:' takes a '- item' list on the following lines, "
                    f"not an inline {value!r}"
                )
            while i < len(lines):
                item = lines[i].strip()
                if not item:
                    i += 1
                    continue
                m = _LIST_ITEM_RE.match(item)
                if not m:
                    break
                i += 1
                variables.append(_dequote(m.group(1).strip()))
            continue
        fields[key] = _dequote(value)

    name = fields.get("name", "").strip()
    if not name:
        raise PromptFormatError(f"{path}: header is missing a non-empty 'name'")
    scope = fields.get("scope", "").strip() or DEFAULT_SCOPE
    for var in variables:
        if not var.isidentifier():
            raise PromptFormatError(
                f"{path}: {var!r} in 'variables:' is not a valid identifier"
            )
    if len(set(variables)) != len(variables):
        raise PromptFormatError(f"{path}: 'variables:' has a duplicate entry")
    return PromptHeader(
        name=name,
        scope=scope,
        description=fields.get("description", ""),
        variables=frozenset(variables),
    )


class PromptLibrary:
    """A directory of headed ``.md`` prompt fragments composed via ``{include}``.

    See the module docstring for the file format and the memory model.
    Construction validates the whole directory; ``render()`` composes one
    fragment and its transitive includes with a single flat variable dict.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        if not self._root.is_dir():
            raise NotADirectoryError(
                f"prompt library root is not a directory: {self._root}"
            )

        self._entries: dict[tuple[str, str], _Entry] = {}
        self._scopes_by_name: dict[str, list[str]] = {}

        # Pass 1 — headers only, into a transient map. Every body is read here
        # too, but kept only until pass 2 has scanned it; nothing keeps a
        # reference afterwards, so the bodies are freed when __init__ returns.
        headers: dict[tuple[str, str], PromptHeader] = {}
        bodies: dict[tuple[str, str], str] = {}
        for path in sorted(self._root.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            header = _parse_header(text, path)
            key = (header.name, header.scope)
            if key in headers:
                raise PromptFormatError(
                    f"two fragments share (name={header.name!r}, scope={header.scope!r}): "
                    f"{self._entries[key].path} and {path}"
                )
            headers[key] = header
            _, bodies[key] = _split_header(text, path)
            self._entries[key] = _Entry(
                path=path, header=header, include_names=frozenset()
            )
            self._scopes_by_name.setdefault(header.name, []).append(header.scope)
        for scope_list in self._scopes_by_name.values():
            scope_list.sort()

        # Pass 2 — scan each body: a brace token is a value slot if declared,
        # otherwise an include that must name a known fragment.
        for key, body in bodies.items():
            header = headers[key]
            includes: list[str] = []
            for token in _unique_tokens(body):
                if token in header.variables:
                    continue
                if token not in self._scopes_by_name:
                    raise PromptFormatError(
                        f"{_fmt_key(key)} ({self._entries[key].path}): {{{token}}} is not a "
                        f"declared variable and no fragment is named {token!r}"
                    )
                includes.append(token)
            self._entries[key] = _Entry(
                path=self._entries[key].path,
                header=header,
                include_names=frozenset(includes),
            )

        self._check_unambiguous_cycles()

    # -- introspection ----------------------------------------------------

    def names(self) -> list[str]:
        """Every distinct fragment ``name``, sorted."""
        return sorted(self._scopes_by_name)

    def scopes(self, name: str) -> list[str]:
        """Every ``scope`` that ``name`` is registered under, sorted (``[]`` if unknown)."""
        return list(self._scopes_by_name.get(name, ()))

    def header(self, name: str, scope: str | None = None) -> PromptHeader:
        return self._entries[self._resolve_target(name, scope)].header

    def required_variables(
        self,
        name: str,
        scope: str | None = None,
        *,
        scopes: Mapping[str, str] | None = None,
    ) -> set[str]:
        """The exact set of variables ``render(name, ...)`` will require — the
        union of the declared ``variables`` of the target fragment and every
        fragment it transitively includes. ``scopes`` disambiguates includes
        whose name maps to more than one scope, same as ``render``."""
        key = self._resolve_target(name, scope)
        return self._walk(key, dict(scopes or {}), ())

    # -- rendering ------------------------------------------------------------

    def render(
        self,
        name: str,
        *,
        scope: str | None = None,
        variables: Mapping[str, object] | None = None,
        scopes: Mapping[str, str] | None = None,
    ) -> str:
        """Render ``(name, scope)`` and everything it includes, leaves first.

        ``variables`` must hold **exactly** the union of the declared
        ``variables`` of the target and every fragment it transitively
        includes — a missing key or an unexpected one raises
        ``PromptVariableError``. Included fragments and the target share this
        one flat namespace (a variable of the same name gets the same value
        everywhere it appears).

        ``scopes`` maps an included fragment's ``name`` to the ``scope`` to
        use when that name is registered under more than one; a name with a
        single scope needs no entry.
        """
        scope_map = dict(scopes or {})
        values = dict(variables or {})
        key = self._resolve_target(name, scope)

        required = self._walk(key, scope_map, ())
        provided = set(values)
        missing = required - provided
        unexpected = provided - required
        if missing or unexpected:
            detail = []
            if missing:
                detail.append(f"missing {sorted(missing)}")
            if unexpected:
                detail.append(f"unexpected {sorted(unexpected)}")
            raise PromptVariableError(
                f"{_fmt_key(key)}: {', '.join(detail)} "
                f"(needs exactly {sorted(required)})"
            )

        return self._render(key, values, scope_map, {})

    # -- internals ---------------------------------------------------------

    def _resolve_target(self, name: str, scope: str | None) -> tuple[str, str]:
        known = self._scopes_by_name.get(name)
        if not known:
            raise PromptResolutionError(
                f"no fragment named {name!r} (have {self.names()})"
            )
        if scope is not None:
            if scope not in known:
                raise PromptResolutionError(
                    f"no fragment {name!r} with scope {scope!r} (have {known})"
                )
            return (name, scope)
        if len(known) > 1:
            raise PromptResolutionError(
                f"fragment {name!r} is registered under scopes {known} — pass scope=..."
            )
        return (name, known[0])

    def _resolve_include(
        self, token: str, scope_map: Mapping[str, str], referrer: tuple[str, str]
    ) -> tuple[str, str]:
        known = self._scopes_by_name.get(token)
        if not known:  # unreachable after construction, kept for a direct call
            raise PromptResolutionError(
                f"{_fmt_key(referrer)} uses {{{token}}}, which names no known fragment"
            )
        if len(known) == 1:
            return (token, known[0])
        chosen = scope_map.get(token)
        if chosen is None:
            raise PromptResolutionError(
                f"{_fmt_key(referrer)} includes {{{token}}}, ambiguous across scopes "
                f"{known} — pass scopes={{{token!r}: <scope>}}"
            )
        if chosen not in known:
            raise PromptResolutionError(
                f"{_fmt_key(referrer)} includes {{{token}}} with scope {chosen!r}, but "
                f"{token!r} only has scopes {known}"
            )
        return (token, chosen)

    def _read_body(self, key: tuple[str, str]) -> str:
        """Re-read a fragment body from disk. Deliberately uncached — the
        caller holds it only for the length of one ``render``."""
        _, body = _split_header(
            self._entries[key].path.read_text(encoding="utf-8"), self._entries[key].path
        )
        return body

    def _walk(
        self,
        key: tuple[str, str],
        scope_map: Mapping[str, str],
        stack: tuple[tuple[str, str], ...],
    ) -> set[str]:
        """DFS the resolved include graph from `key`; return the union of
        declared variables. Raises on a cycle or an unresolvable include.
        Uses the in-memory include-name sets — no disk read."""
        if key in stack:
            trail = " -> ".join(_fmt_key(k) for k in (*stack, key))
            raise PromptResolutionError(f"include cycle: {trail}")
        entry = self._entries[key]
        required = set(entry.header.variables)
        for token in entry.include_names:
            child = self._resolve_include(token, scope_map, key)
            required |= self._walk(child, scope_map, (*stack, key))
        return required

    def _render(
        self,
        key: tuple[str, str],
        values: Mapping[str, object],
        scope_map: Mapping[str, str],
        memo: dict[tuple[str, str], str],
    ) -> str:
        # `render()` runs `_walk` first, so by here the tree is known acyclic
        # and every include resolves — `substitute` never has to re-check.
        if key in memo:  # a diamond dependency — identical output, read once
            return memo[key]
        declared = self._entries[key].header.variables

        def substitute(match: re.Match[str]) -> str:
            token = match.group(1)
            if token in declared:
                return str(values[token])
            child = self._resolve_include(token, scope_map, key)
            return self._render(child, values, scope_map, memo)

        rendered = _TOKEN_RE.sub(substitute, self._read_body(key))
        memo[key] = rendered
        return rendered

    def _check_unambiguous_cycles(self) -> None:
        """Flag an include cycle formed entirely by includes whose name has a
        single scope — those are real cycles no matter what ``scopes`` a
        caller passes. A cycle that runs through an ambiguous include is left
        for ``_walk`` to catch once a scope is chosen."""
        white, grey, black = 0, 1, 2
        color = dict.fromkeys(self._entries, white)
        stack: list[tuple[str, str]] = []

        def visit(key: tuple[str, str]) -> None:
            color[key] = grey
            stack.append(key)
            for token in self._entries[key].include_names:
                scope_list = self._scopes_by_name[token]
                if len(scope_list) != 1:
                    continue
                child = (token, scope_list[0])
                if color[child] == grey:
                    at = stack.index(child)
                    trail = " -> ".join(_fmt_key(k) for k in (*stack[at:], child))
                    raise PromptResolutionError(f"include cycle: {trail}")
                if color[child] == white:
                    visit(child)
            stack.pop()
            color[key] = black

        for key in self._entries:
            if color[key] == white:
                visit(key)


@cache
def prompt_library(*subdirs: str) -> PromptLibrary:
    """A cached ``PromptLibrary`` rooted at ``harness/prompts`` joined with
    ``subdirs`` (the whole prompts tree when called with no arguments).
    Built — and validated — once per distinct root."""
    if not subdirs:
        subdirs = [""]

    return PromptLibrary(settings.prompts_root_dir.joinpath(*subdirs))
