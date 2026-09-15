# Krutrim Agent

A pluggable, multi-agent-type platform. A LangGraph + [deepagents](https://docs.langchain.com/oss/python/deepagents/overview) backend (Python) hosts independent agent **profiles** — this build’s is `research` — and streams to a pure-React frontend (web + Tauri desktop) over the AG-UI protocol via `@ag-ui/client`’s `HttpAgent`, with no runtime process in between. Chat sits in a left pane; the agent’s finished deliverable renders in a right-hand canvas.

## Core / plugin split

The one load-bearing design decision. **Core** is never touched to add an agent: the FastAPI app, the provider system, the sandbox registry, the harness loaders, `krutrim_agents_core`’s `registry.py` (auto-discovery) and `builder.py` (generic graph assembly), `libs/ui`, and the `agent-ui` frame (`components/{auth, conversation,dialogs, settings, workspace}/`, `api/`, `hooks/`, `store/`).

**Adding an agent type** touches only:

-   **Backend** — one folder `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/` declaring an `AgentProfile` (prompts, tools, subagents, default models) that self-registers, plus its `harness/{prompts,skills,memory}/<key>/` content. Zero edits to existing files — `registry.py` scans each configured profile package’s filesystem path at import.
    
-   **Frontend** — optional: one folder `libs/agent-ui/src/screens/<key>/` exporting an `AgentScreenModule` plus one line in `screens/registry.ts`. Omit it and the `default` screen (shared thread + built-in markdown/chart renderer) is used.
    

This split isn’t a single mechanism — it’s several independent registries (agent profiles, storage backends, vector stores/retrieval strategies, security/governance extensions, sandbox profiles), each discovered its own way. 
## Features

### Research agent

`research` is the only profile that ships today. It only runs as a full agentic run over `POST /agents/{agent_id}` — it has **no plain-chat mode**; `/api/chat` is a structurally separate graph (fixed tools, static prompt) that doesn’t know profiles exist at all. See [Chat](#chat) below for that path.

| Feature | Status | Notes |
| --- | --- | --- |
| Web research | Completed | `web_search` (Tavily) + `web_fetch` |
| RAG over session documents | Completed | `rag_tool`, per-session vector store |
| RAG silent-injection mode | Completed | Off by default; `RagInjectionMiddleware` prepends context to the system prompt with no visible tool call |
| Filesystem workspace | Completed | `ls` / `read` / `write` / `edit` / `glob` / `grep`, via `FilesystemMiddleware` |
| Live scratchpad + per-turn dynamic system prompt | Completed | `/workspace/.research/{state,known,unknown}.md`, re-read from disk and re-rendered into the prompt on every model call |
| Clarification / approval / choice protocol | Completed | A 5-way decision framework (`continue` / `ask_clarification` / `request_approval` / `request_choice` / `finish`), enforced by prompt instructions only — not a graph router |
| Skills + per-agent memory | Completed | Loaded from `harness/skills/` + `harness/memory/AGENTS.md`, mounted read-only into the sandbox |
| Context management (`trim` / `summarize`) | Completed | Off by default; a third `rag` strategy is declared but currently falls back to `summarize` (not implemented) |
| Run-transcript recording | Completed | One JSONL record per model/tool call per session, for eval / replay |
| Report/narration split | Completed | Everything before the `===FINAL_REPORT===` marker streams as live narration; only the content after it is the persisted deliverable |
| Deliverable persistence | Completed | Report saved to `/workspace/<topic>.md`; follow-ups edit the same file in place |
| Cross-agent messaging | Completed | `message_agent` tool, available when a reachable sibling agent session exists in the same project |
| Plain (non-agentic) chat mode | Not built | Research only runs via `/agents/{id}`; there is no code path that puts the `research` profile behind `/api/chat` |
| Subagent flow | Not built | The profile registers an empty `subagents_factory` — no subagents ever attach, despite the graph builder supporting them |
| “Swarm” multi-agent topology | Prompt-only, not architecturally built | The system prompt describes Orchestrator / Search / RAG / Analysis / Critic roles, but this is one ReAct loop on one model — no multi-node graph, no role handoff. Two other topology prompts (`react_agent`, `planner_executor`) exist but are never selected in code |
| PDF export | Beta, effectively unreachable by default | The `document-export` skill shells out via the `execute` tool, which the **default** sandbox profile doesn’t grant — it only exists under the opt-in `local-exec` profile. Built and unit-tested, but not reachable out of the box |
| Sandboxed data analysis (Python) | Beta, same gap as PDF export | Also depends on `execute` |
| Sandbox | Completed, filesystem-only | Session-scoped `/workspace/` (read-write) + read-only `/skills/` and `/memory/` mounts. No process, container, or network isolation — the old Docker/gRPC runtime was removed; see [Platform](#platform) |
| Sandbox via hooks | Not built | No such mechanism exists in the codebase today. The closest thing is `SandboxPolicyMiddleware` — a tool-call policy gate (deny/approve/allow + human-approval interrupt), not isolation and not a general extension point |

### Chat

The plain, profile-less chat screen (`POST /api/chat`). Deliberately minimal by design — it shares session/project storage and the RAG pipeline with agent runs, but not skills, memory, or the sandbox.

| Feature | Status | Notes |
| --- | --- | --- |
| Streaming responses | Completed | Same AG-UI SSE translator as agent runs |
| Model + provider selection | Completed | One model per chat (`provider:model`), changeable after creation without losing history |
| Multi-turn history | Completed | LangGraph `AsyncSqliteSaver` checkpoint per session |
| Sessions / projects | Completed | Optional project grouping; chats can be created standalone or moved into a project later |
| RAG over uploaded documents | Completed | Same session-scoped ingestion/retrieval pipeline as the research agent (`.txt`/`.md`/`.pdf`/`.docx` upload, `rag_tool`, optional silent injection) |
| Tool use (web search/fetch, RAG, datetime) | Completed | Fixed toolset available on every turn |
| Token usage tracking | Completed | Per-turn usage plus running per-session totals |
| Stop generation (backend) | Completed | Client aborts the SSE fetch; server catches the cancellation and persists the partial reply with `interrupted: true` |
| History reload / message list | Completed | `GET /api/sessions/{id}/messages`, read straight from the checkpoint |
| Stop-generation button (UI) | Not built | The composer component supports an `isRunning`/`onStop` pair (the agent screen uses it), but the chat screen never wires it up |
| Copy / regenerate / edit message | Not built | No such affordance on the message bubble |
| Interrupted-turn indicator (UI) | Not built | Backend flags a cut-off turn (`interrupted: true`); the chat UI doesn’t render that flag |
| System prompt override | Not built | Hardcoded to the fixed `chat_system` prompt; no per-chat override field |
| Temperature / sampling params | Not built | Not surfaced anywhere in the request path |
| Skills / memory / sandbox execution | Not built (deliberate) | The underlying chat graph builder accepts these params, but the chat route never supplies them |
| Agent-profile switching | Not applicable | Chat is a separate, profile-less screen — one model/provider pair, no roles, not one of the registered `agent_key`s |
| Rate limiting | Not built |  |

### Platform

| Feature | Status | Notes |
| --- | --- | --- |
| LLM provider: OpenRouter | Completed | Every catalog model (Anthropic / Google / Meta / Mistral / Qwen / …) is routed through OpenRouter’s OpenAI-compatible API, not a native SDK per vendor |
| LLM provider: others | Not built | Provider registry supports adding one (lazy-import `ProviderSpec`); only OpenRouter is registered today |
| Web search: Tavily | Completed |  |
| Web search: other providers | Not built | A provider registry exists but only Tavily is in it; the per-user `web_search_provider` setting is currently a no-op — the tool is resolved once at import time, not per request |
| RAG vector store: faisslite / Qdrant | Completed | faisslite is the default (embedded); Qdrant is opt-in via env |
| RAG retrieval: `vector_only` | Completed |  |
| RAG retrieval: hybrid / BM25 (reciprocal rank fusion) | Built, not reachable | Fully implemented and registered, but the factory always resolves the frozen default strategy and never consults the live per-user setting — same class of bug as the web-search-provider gap above |
| RAG retrieval: rerank | Not built |  |
| Document parsing: text / markdown | Completed | Direct UTF-8 decode |
| Document parsing: PDF | Completed | 3-stage escalation (raw text layer → OCR → full table/layout ML via docling); OCR and ML stages are off by default behind env flags |
| Document parsing: DOCX | Completed | Via docling |
| Async RAG ingestion | Completed | Celery worker; a cluster-wide Redis mutex currently serializes ingestion jobs one-at-a-time (no parallelism yet) |
| Async embedding precompute | Completed | Bulk-embeds a session’s already-uploaded files |
| Frontend: web + Tauri desktop | Completed | One React renderer |
| Plain non-agentic chat screen | Completed | `/api/chat` — see [Chat](#chat) |
| Live model / provider settings | Completed | Per-role selection is genuinely live — the graph is rebuilt per request, so a change applies on the next turn with no restart |
| Live retrieval-strategy / web-search-provider settings | Broken / no-op | Declared as hot-reloadable in the settings schema, but never read by the code path that would need them (see the two rows above) |
| Server/infra settings (vector store backend, Qdrant connection, sandbox profile, host/port) | Needs restart | Frozen at process start by design (`ServerSettings`, env-bound) |
| Sandbox: per-session filesystem workspace | Completed | Read-write `/workspace/`, read-only `/skills/` and `/memory/` mounts |
| Sandbox: opt-in host shell (`local-exec` profile) | Completed, zero isolation | A real subprocess on the backend host with a curated env allowlist (no API keys/secrets forwarded) — not sandboxed in any container/VM sense, not for shared or production hosts |
| Sandbox: container / network / resource isolation | Not built (removed) | The Docker + gRPC in-sandbox runtime was removed 2026-08-30; the current backend is a deliberate placeholder (“no container, no isolation”) |
| Domain tools (market data, quotes / OHLCV, …) | Not built |  |
| `shared-types` codegen from Pydantic models | Not built | Hand-synced |
| Desktop: real app icon | Completed | Custom-designed icon, not Tauri’s default |
| Desktop: auto-spawn backend | Not built | No sidecar/process-spawn code exists in `src-tauri` |
| Dataset-driven eval runner | Not built | Run-transcript recording exists (JSONL), but there’s no dataset/replay/scoring harness that consumes it |
| More agent profiles (trading / sales) | Not built |  |
| Coding / PR-drafting agent | Not built | Deliberate — needs a more privileged sandbox (egress-allowlisted, git-capable, no credentials exposed to the shell) plus a human-approval gate before any push |

## In-depth public API features to customize

This project already splits “core” from “plugin” along several **independent axes** — agent profiles, storage, RAG backends, security/governance extensions, sandbox — but each axis grew its own registry with a different level of polish, and there’s no single “install one plugin” surface yet. This section inventories what’s already pluggable, what’s a clear gap, and what other agent-harness projects (Claude Code, Codex CLI, Hermes Agent) do that’s worth borrowing if/when a public hook API gets built here.

### What already exists

| Extension point | Mechanism | Configured via | Status |
| --- | --- | --- | --- |
| Custom agent profile (prompts, tools, subagents, models) | `AgentProfile` frozen dataclass, self-registers on import | `settings.agent_profile_sources` | Completed |
| Custom graph topology per profile | `AgentProfile.graph_pattern` override, still gets the rest of `build_agent`’s assembly for free | Profile-level field | Completed |
| Per-run stream instrumentation | `AguiPlugin` protocol (`before_run` / `on_event` / `after_run` async generators); a plugin that raises is logged and skipped, never breaks the stream | `register_plugin()` | Mechanism is complete; zero built-in plugins ship today (`default_plugins()` returns `[]`) |
| Custom skills | Filesystem convention, `harness/skills/<key>/*/SKILL.md` (+ optional `.py`), mounted read-only | `AgentProfile.skills_sources` | Completed |
| Alternate harness content per deployment (prompts/skills/memory) | Swap the entire content tree with zero code change | `KRUTRIM_AGENT_HARNESS_DIR` | Completed |
| Custom storage backend | `Storage` / `AuthStorage` ABCs (~30 methods covering projects/agents/sessions/memory/etc.) + registry | `settings.storage_backend_sources` | Completed |
| Custom vector store / retrieval strategy | Registry-based factories, same pattern as storage | `settings.vector_store_backend_sources`, `retrieval_strategy_sources` | Completed |
| Custom sandbox backend | `SandboxProfile(build, execute)` registered into a backend registry; real subclassable `KrutrimBackend`/`DelegatingBackend` base classes | Only two profiles (`default`, `local-exec`) are hardcoded at import — **no settings-driven discovery list** | Partial — same registration *shape* as agent profiles, but not third-party-installable via config alone |
| Tool-call policy gate | `SandboxPolicyMiddleware` — deny/approve/allow verdicts per write/edit/delete/execute call, `approve` pauses the run for human-in-the-loop approval via LangGraph `interrupt()` | Profile/session policy config | Completed, but single-purpose - this is the closest thing to a “PreToolUse hook,” not a general extension point a third party can attach arbitrary logic to |
| Session-delete cleanup callbacks | Plain callback list, fired before cascade delete | `register_session_delete_hook()` | Completed, narrow |
| Frontend per-agent screen/renderer | `AgentScreenModule` (`Center` pane, `OutputRenderer`, `turnSplitter`) | One line in `screens/registry.ts` | Completed |
| MCP server configuration | Full CRUD (`mcp.json`, `credentials.json`, `/api/mcp` routes), with secret redaction. | Per-user settings UI/API | Partial |

### Prerequisites

-   Node 20+, [pnpm](https://pnpm.io) 10+
    
-   Python via [uv](https://docs.astral.sh/uv/) (`brew install uv`) — uv manages its own Python 3.11; your system Python doesn’t matter
    
-   An `OPENROUTER_API_KEY` (LLM + RAG embeddings) and a `TAVILY_API_KEY` (web search)
    
-   Optional: Docker — only for the full `docker/` compose stack, or a standalone Redis (Celery / RAG ingestion) or Qdrant
    
-   Desktop app only: a Rust toolchain (`rustup`/`cargo`) plus Tauri’s [system dependencies](https://v2.tauri.app/start/prerequisites/)
    

## Setup

```bash
pnpm install
python3 -m scripts.generate_env dev   # writes .env with the fields a dev needs — fill in OPENROUTER_API_KEY and TAVILY_API_KEY
cd backend && uv sync && cd ..
```

`backend/` is one `uv` workspace — the libs, the FastAPI service, and the Celery worker share a single venv; run `uv run` from `backend/`. There’s one real `.env` at the repo root; `backend/.env`, `apps/web/.env.local`, and `docker/.env` are committed symlinks to it — edit the root file only.

### Environment variables

`scripts/env_schema.py` is the single source of truth for every env var this project reads; `scripts/generate_env.py` (stdlib only, no `uv run` needed) generates a `.env` from it:

```bash
python3 -m scripts.generate_env            # show options
python3 -m scripts.generate_env dev        # local development — most fields, terse comments
python3 -m scripts.generate_env prod       # production deploy — required + prod-relevant fields only
python3 -m scripts.generate_env full       # every field, all commented, section-wise (reference dump)
python3 -m scripts.generate_env docs       # regenerate ENV.md from the same schema
```

Add `--force` to overwrite an existing output file, or `--out <path>` to write somewhere other than the repo-root `.env`. See [ENV.md](ENV.md) for what every field does.

## Running it

```bash
# Backend (FastAPI) — the frontend talks to it directly over AG-UI, no runtime hop
cd backend && uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000

# Frontend — web
pnpm run web                       # apps/web → http://localhost:4200
# ...or desktop (needs the Rust toolchain)
pnpm exec nx run desktop:serve     # runs `tauri dev`

# Optional — RAG document ingestion + embedding precompute (needs Redis)
docker compose -f docker/docker-compose.yml up redis
cd backend && uv run krutrim-agent-worker
```

Open `http://localhost:4200/?agent=research` (omitting `?agent=` lands on `home`). The whole stack also runs via `docker/docker-compose.yml` — see `docker/README.md`.

## Adding a new agent type

1.  `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/__init__.py` — define an `AgentProfile` and call `register_profile(...)`. Copy `research` as a starting point.
    
2.  `backend/harness/{prompts,skills,memory}/<key>/` — at minimum `memory/<key>/AGENTS.md` and a prompt per declared role.
    
3.  *(optional)* `libs/agent-ui/src/screens/<key>/` + one line in `screens/registry.ts` — skip it to use the `default` screen.
    
4.  Restart the backend. Visit `?agent=<key>`.
    

No core file changes for any of the above.

## Testing

```bash
cd backend && uv run pytest    # providers, registry, graph assembly, AG-UI translator, chat, doc parsers, cross-agent
pnpm run lint                  # frontend eslint
pnpm run build                 # build every Nx project
```

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Author

Vishesh Panchal