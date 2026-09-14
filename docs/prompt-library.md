# PromptLibrary

Lightweight loader for composable prompt fragments — the in-repo replacement for the external `promptstore` package.

Code: [`backend/libs/krutrim_agents_core/src/krutrim_agents_core/harness/prompts.py`](../backend/libs/krutrim_agents_core/src/krutrim_agents_core/harness/prompts.py)
Tests: [`backend/tests/test_prompt_library.py`](../backend/tests/test_prompt_library.py)

(The older `load_prompt(agent_key, name)` in the same module — one flat file, no header, no composition — is unchanged and still used where composition isn't needed.)

## Fragment file format

One prompt per `.md` file: an HTML-comment header, then the body.

```
<!--
name: research_core
scope: default          # optional — defaults to "default"
description: one-liner   # optional
variables:
  - user_request
  - available_tools
-->
The task is: {user_request}

{topology}
```

- `name` is required. `scope` defaults to `"default"`. `description` is optional. `variables` is an optional `- item` list. Unknown header keys are ignored.
- `{token}` in the body is an identifier in braces, and is only recognised when it **stands alone** — at the start or end of the body, or with a space or newline on each side:
  - if `token` is one of this fragment's declared `variables` → a **value slot**, filled at render time;
  - otherwise → an **include** of the fragment named `token`, rendered and spliced in.
- A declared variable **shadows** a same-named fragment (it stays a value slot).
- A brace touching any other character is **literal text** — `{"k": "v"}`, `{ spaced }`, `S{section_number}[.{slug}]`, `env={HOME}` all pass through unchanged. (So there's no `{{`/`}}` escape and no need for one.)
- `(name, scope)` is the primary key. Two files may share a `name` only with different `scope`s.

## Rendering

```python
from krutrim_agents_core.harness.prompts import PromptLibrary

lib = PromptLibrary("path/to/prompt/fragments")

text = lib.render(
    "system_main",
    variables={"user_request": "...", "available_tools": "..."},
)
```

`render(name, *, scope=None, variables=None, scopes=None) -> str`

- Composes `name` and everything it includes, **leaves first** (a child is fully rendered, then its text is substituted into the parent).
- `variables` is **one flat dict for the whole tree** — it must contain **exactly** the union of the declared `variables` of the target and every fragment it transitively includes. A missing key *or* an unexpected key raises `PromptVariableError`. The same variable name gets the same value everywhere it appears.
- Use `lib.required_variables(name, scope=None, *, scopes=None)` to get that exact set without rendering.

## `scope` vs `scopes`

Both select among fragments that share a `name`, but at different positions in the call:

| Argument | Selects the variant of… | Shape | When you need it |
| --- | --- | --- | --- |
| `scope` | the **target** you called `render()` on | `str` | the target `name` is registered under more than one scope |
| `scopes` | each fragment the target **`{includes}`**, at any depth | `{name: scope}` | an included `name` is registered under more than one scope |

A `name` with a single scope needs neither — it resolves on its own. They're independent: you can pass `scope=` for the target and `scopes=` for its includes in the same call. `scope` also applies to `header()` and `required_variables()` (which target row to describe).

### Worked example

```
brief.md    name: greeting  scope: brief   variables: [who]           body:  Hi {who}
formal.md   name: greeting  scope: formal  variables: [who]           body:  Good evening {who}

short.md    name: report    scope: short   variables: [point]         body:  {greeting}
                                                                             quick note: {point}
full.md     name: report    scope: full    variables: [who, point]    body:  {greeting}

                                                                             # Report for {who}

                                                                             {point}
```

Each fragment declares **every `{token}` it uses directly** — `report/full` lists `who` even though `greeting` also uses it. The one flat `variables` dict then satisfies all of them. (Each `{token}` stands alone on its line or is space-bordered — that's what the loader recognises.)

```python
lib.render(
    "report",
    scope="full",  # ← which `report` (target has 2 scopes)
    scopes={"greeting": "formal"},  # ← which `greeting` the tree pulls in
    variables={"who": "Ada", "point": "ship it"},
)
```

Resolution order: `scope` picks `report/full`; walking its body, `{greeting}` is an include with two scopes, so `scopes["greeting"]` picks `greeting/formal`; `{who}` / `{point}` are value slots. Output:

```
Good evening Ada

# Report for Ada

ship it
```

Leaving out a needed selector is an error, not a guess:

```python
lib.render("report", variables=...)
# PromptResolutionError: fragment 'report' is registered under scopes ['full', 'short'] — pass scope=...

lib.render("report", scope="full", variables=...)
# PromptResolutionError: 'report' (scope 'full') includes {greeting}, ambiguous across scopes ['brief', 'formal'] — pass scopes={'greeting': <scope>}
```

## Validation and memory

Constructing a `PromptLibrary` validates the **whole directory** up front and raises on:

- a malformed header, or a missing `name`;
- a duplicate `(name, scope)` across files;
- an `{include}` that names no known fragment;
- an include **cycle** made of single-scope includes (a cycle that only exists through an ambiguous include is caught later, by `render` / `required_variables`, once a scope picks the looping branch).

It reads every body once to do this, then **drops the bodies**. Only the headers and a small per-fragment set of include names stay in memory, so a large tree of fragments costs kilobytes, not the full text. `render()` re-reads just the files in the tree it is composing and releases them when it returns.

## Errors

| Exception | Raised when |
| --- | --- |
| `PromptFormatError` | bad header, duplicate `(name, scope)`, or an `{include}` naming no fragment — all at construction |
| `PromptResolutionError` | unknown target name/scope, an ambiguous include with no `scopes` entry (or a wrong one), or an include cycle |
| `PromptVariableError` | `variables` passed to `render()` isn't exactly the tree's required set (missing or unexpected keys) |

## `prompt_library()` helper

```python
from krutrim_agents_core.harness.prompts import prompt_library

lib = prompt_library("research", "system")  # rooted at harness/prompts/research/system
```

Cached (built and validated once per distinct root), rooted at `settings.prompts_root_dir` joined with the given subdirs; no arguments means the whole `harness/prompts` tree.
