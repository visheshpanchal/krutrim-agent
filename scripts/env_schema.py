"""Single source of truth for every env var this project reads.

`scripts/generate_env.py` (writes .env for dev/prod/full) and `ENV.md`
(human-readable docs) are both generated from `SECTIONS` below. Add or change
a field here once and both stay in sync — never hand-edit a generated .env
comment or ENV.md row directly.

Field naming follows what the backend actually does (see
`krutrim_agent_management/config.py`): most backend settings are read with
the `KRUTRIM_AGENT_` prefix stripped case-insensitively; a handful of names
are bare (OPENROUTER_*, TAVILY_*, VITE_BACKEND_URL, TORCH_BACKEND, COMPOSE_*,
QDRANT_HTTP_PORT/GRPC_PORT, *_POLLING, REDIS_*, DEV_MODE, LANGFUSE_*).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    key: str
    description: str
    # Extra detail only shown in `full` mode and ENV.md — omit for
    # self-explanatory fields to keep dev/prod output terse.
    context: str | None = None
    tier: str | None = None  # "server" | "user" | None (bare / not a backend setting)
    required: bool = False
    default: str | None = None
    # Placeholder written into the *active* (uncommented) line for a
    # required field, or shown as the commented default otherwise.
    example: str | None = None
    in_dev: bool = True
    in_prod: bool = True


@dataclass(frozen=True)
class Section:
    title: str
    fields: tuple[Field, ...] = field(default_factory=tuple)


SECTIONS: list[Section] = [
    Section(
        "LLM / embeddings provider",
        (
            Field(
                "OPENROUTER_API_KEY",
                "OpenRouter API key — powers every LLM call (agents + chat) and RAG embeddings. Nothing works without it.",
                required=True,
            ),
            Field(
                "OPENROUTER_BASE_URL",
                "Override the OpenRouter endpoint (e.g. a local dev proxy).",
                default="https://openrouter.ai/api/v1",
            ),
            Field(
                "LITELLM_MASTER_KEY",
                "Only when OPENROUTER_BASE_URL points at a local proxy that authenticates with its own master key.",
                context="Must match that proxy's own LITELLM_MASTER_KEY setting.",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Web search",
        (
            Field(
                "TAVILY_API_KEY",
                "Tavily API key. Tavily is currently the only registered web-search provider — without this, `web_search` runs but returns an error instead of results.",
                required=True,
            ),
            Field(
                "TAVILY_SEARCH_API_BASE",
                "Point tavily-python at a proxy / self-hosted gateway instead of api.tavily.com.",
                default="https://api.tavily.com",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_WEB_SEARCH_PROVIDER",
                "Web search provider selector. Only 'tavily' is registered today, so this currently has no other valid value.",
                tier="user",
                default="tavily",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Compose (docker/docker-compose*.yml)",
        (
            Field(
                "COMPOSE_PROJECT_NAME",
                "Override to run a fully isolated second copy of a stack (own containers/network/volumes).",
                default="krutrim-agent[-dev]",
                in_dev=False,
            ),
            Field(
                "COMPOSE_PROFILES",
                "Activates optional services. Set to `qdrant` to start the qdrant container.",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Backend core [server]",
        (
            Field("KRUTRIM_AGENT_HOST", "Bind address.", tier="server", default="0.0.0.0"),
            Field("KRUTRIM_AGENT_PORT", "Bind port.", tier="server", default="8000"),
            Field(
                "KRUTRIM_AGENT_HOME_ROOT",
                "Root of the runtime-config tree (.jwt_secret, user table, per-user config/mcp/credentials, storage, logs).",
                context="A desktop build points this at an OS app-data dir instead.",
                tier="server",
                default="~/.krutrim_agent",
            ),
            Field(
                "KRUTRIM_AGENT_GRAPH_RECURSION_LIMIT",
                "LangGraph super-step cap per agent turn — raise for deep research / subagent loops.",
                tier="server",
                default="100",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_RAG_EMBEDDING_MODEL",
                "Embedding model for RAG ingestion + query. Server tier because it must match what's already stored in the vector index.",
                tier="server",
                default="qwen/qwen3-embedding-8b",
            ),
            Field(
                "KRUTRIM_AGENT_CORS_ORIGINS",
                "Allowed frontend origins. Add the Vite dev-server origins locally; set to your real frontend origin(s) in production.",
                tier="server",
                default='["http://localhost:4200","http://localhost:5173"]',
            ),
            Field("KRUTRIM_AGENT_EDITION", "Deployment edition.", tier="server", default="community"),
        ),
    ),
    Section(
        "Backend auth [server] (krutrim_agent_backend/auth/)",
        (
            Field(
                "KRUTRIM_AGENT_AUTH_ENABLED",
                "Master switch — when true, every route except register/login/refresh/health/docs needs a Bearer access token.",
                tier="server",
                default="true",
            ),
            Field(
                "KRUTRIM_AGENT_AUTH_JWT_SECRET",
                "HS256 signing secret. Leave unset to auto-generate and store at <HOME_ROOT>/.jwt_secret (0600) — fine for one instance.",
                context="Set explicitly in production to share one secret across replicas / survive a redeploy.",
                tier="server",
                in_prod=True,
            ),
            Field(
                "KRUTRIM_AGENT_AUTH_ACCESS_TTL_MINUTES",
                "Access token lifetime.",
                tier="server",
                default="30",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_AUTH_REFRESH_TTL_DAYS",
                "Refresh token lifetime.",
                tier="server",
                default="14",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_ADMIN_USERNAME",
                "Optional first-boot admin (only while the users table is still empty; otherwise the first /api/auth/register becomes admin).",
                tier="server",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_ADMIN_PASSWORD",
                "Paired with KRUTRIM_AGENT_ADMIN_USERNAME.",
                tier="server",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Backend behaviour [user] (hot-reloads, also editable from the settings UI)",
        (
            Field(
                "KRUTRIM_AGENT_DEFAULT_MODEL",
                "Default OpenRouter model when nothing more specific is configured.",
                tier="user",
                default="deepseek/deepseek-v4-flash-0731",
            ),
            Field(
                "KRUTRIM_AGENT_CONTEXT_MANAGEMENT_STRATEGY",
                "Auto context-window management for long turns: off | trim | summarize | rag (reserved, falls back to summarize).",
                tier="user",
                default="off",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_CONTEXT_TRIGGER_TOKENS",
                "Token count that triggers the 'summarize' strategy.",
                tier="user",
                default="120000",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_CONTEXT_KEEP_MESSAGES",
                "Messages kept verbatim by the 'summarize' strategy.",
                tier="user",
                default="20",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_CROSS_AGENT_CALL_TIMEOUT_SECONDS",
                "Max wait (1-3600s) on a peer's turn via the cross-agent message_agent tool.",
                tier="user",
                default="60",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_RETRIEVAL_STRATEGY",
                "Retrieval ranking/query strategy for the active vector store.",
                tier="user",
                default="vector_only",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_RAG_INJECTION_ENABLED",
                "Silently inject retrieved project context into the research agent's turn.",
                tier="user",
                default="false",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_EVAL_RECORD_FULL_PAYLOADS",
                "Capture full tool-call args + a truncated result preview into the run-transcript JSONL.",
                tier="user",
                default="false",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_EVAL_RECORD_PAYLOAD_MAX_CHARS",
                "Truncation length for the above.",
                tier="user",
                default="4000",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Redis / Celery",
        (
            Field(
                "KRUTRIM_AGENT_REDIS_URL",
                "Celery broker/result-backend. The docker stacks set this automatically; use this for a backend run directly on the host.",
                tier="server",
                default="redis://localhost:6379/0",
            ),
        ),
    ),
    Section(
        "Logging [server] (krutrim_agent_management/logging_config.py — server + Celery worker)",
        (
            Field(
                "KRUTRIM_AGENT_LOG_DIR",
                "Log directory root (server/server.log, worker/worker.log).",
                tier="server",
                default="~/.krutrim_agent/logs",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_LEVEL",
                "File-sink threshold. DEBUG gives the full step-by-step trace.",
                tier="server",
                default="INFO",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_CONSOLE_LEVEL",
                "stderr threshold. Forced to DEBUG when DEV_MODE=true.",
                tier="server",
                default="INFO",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_ROTATION",
                "Rotation trigger — a period ('1 day'), a wall-clock time ('00:00'), or a size ('20 MB').",
                tier="server",
                default="1 day",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_RETENTION",
                "How long rotated files are kept.",
                tier="server",
                default="14 days",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_COMPRESSION",
                "'' keeps rotated files plain; 'zip'/'gz'/'tar.gz' compresses them.",
                tier="server",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_BACKTRACE",
                "Extended (variable-free) tracebacks in the file sink. Also on when DEV_MODE.",
                tier="server",
                default="false",
                in_dev=False,
            ),
            Field(
                "KRUTRIM_AGENT_LOG_INTERCEPT_STD",
                "Route stdlib logging (uvicorn/celery/httpx/...) through loguru so everything shares one format/file.",
                tier="server",
                default="true",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Vector store [server] (krutrim_agent_rag — faisslite default, or qdrant)",
        (
            Field(
                "KRUTRIM_AGENT_VECTOR_STORE_BACKEND",
                "'faisslite' (default, embedded) or 'qdrant'. Not a build-time choice — both clients ship in every image.",
                context="For qdrant, also set COMPOSE_PROFILES=qdrant and KRUTRIM_AGENT_QDRANT_URL.",
                tier="server",
                default="faisslite",
            ),
            Field(
                "KRUTRIM_AGENT_QDRANT_URL",
                "Qdrant service address (e.g. http://qdrant:6333 in-compose).",
                tier="server",
                in_dev=False,
            ),
            Field("KRUTRIM_AGENT_QDRANT_API_KEY", "Optional Qdrant auth key.", tier="server", in_dev=False),
            Field(
                "KRUTRIM_AGENT_QDRANT_PREFER_GRPC",
                "Use Qdrant's gRPC port instead of HTTP.",
                tier="server",
                default="false",
                in_dev=False,
            ),
            Field("KRUTRIM_AGENT_QDRANT_HTTPS", "Use HTTPS for Qdrant.", tier="server", default="false", in_dev=False),
            Field(
                "KRUTRIM_AGENT_QDRANT_LOCATION",
                "':memory:' runs an embedded Qdrant (tests / no server); overrides QDRANT_URL.",
                tier="server",
                in_dev=False,
            ),
            Field(
                "QDRANT_HTTP_PORT",
                "Host-published Qdrant HTTP port (compose port mapping).",
                default="6343",
                in_dev=False,
            ),
            Field(
                "QDRANT_GRPC_PORT",
                "Host-published Qdrant gRPC port (compose port mapping).",
                default="6344",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "RAG document parsing [server] (krutrim_agent_doc)",
        (
            Field(
                "PDF_PARSER_ENABLE_OCR_STAGE",
                "PDF parsing escalates raw-text -> OCR -> full ML layout; OCR/ML are off by default (fast raw-text stage only).",
                tier="server",
                default="false",
                in_dev=False,
            ),
            Field(
                "PDF_PARSER_ENABLE_ML_STAGE",
                "Full table/layout ML stage (docling) for PDF parsing.",
                tier="server",
                default="false",
                in_dev=False,
            ),
        ),
    ),
    Section(
        "Frontend (apps/web)",
        (
            Field(
                "VITE_BACKEND_URL",
                "Where the BROWSER reaches the backend. Baked in at build time for the Docker prod image; live for `vite dev`.",
                default="http://localhost:8000",
            ),
        ),
    ),
    Section(
        "Dev mode + Langfuse tracing (dev-stack only — inert in production)",
        (
            Field(
                "KRUTRIM_AGENT_DEV_MODE",
                "Gates local-only tooling (Langfuse, verbose errors, DEBUG console/file logging). Wins over bare DEV_MODE if both are set.",
                default="true",
                in_prod=False,
            ),
            Field("DEV_MODE", "Bare alias for KRUTRIM_AGENT_DEV_MODE.", in_prod=False),
            Field(
                "KRUTRIM_AGENT_LANGFUSE_ENABLED",
                "Force Langfuse tracing off even in dev mode (e.g. LANGFUSE_BASE_URL points at a host not running Langfuse).",
                tier="server",
                default="true",
                in_prod=False,
            ),
            Field("LANGFUSE_PUBLIC_KEY", "Langfuse public key. Only traced while dev mode is on.", in_prod=False),
            Field("LANGFUSE_SECRET_KEY", "Langfuse secret key.", in_prod=False),
            Field(
                "LANGFUSE_BASE_URL",
                "Self-hosted Langfuse URL; omit for Langfuse Cloud.",
                default="http://localhost:3000",
                in_prod=False,
            ),
            Field(
                "LANGFUSE_HOST",
                "Fallback Langfuse Cloud host if LANGFUSE_BASE_URL is unset.",
                default="https://cloud.langfuse.com",
                in_prod=False,
            ),
            Field(
                "LANGFUSE_DOCKER_BASE_URL",
                "Read inside the docker compose files — repoints the CONTAINERS at a real Langfuse URL.",
                in_prod=False,
            ),
        ),
    ),
    Section(
        "File-watch reliability (docker-compose.dev.yml only)",
        (
            Field(
                "WATCHFILES_FORCE_POLLING",
                "macOS/Windows: flip true if the backend's --reload stops noticing bind-mount edits (costs idle CPU). Leave false on Linux.",
                default="false",
                in_prod=False,
            ),
            Field(
                "CHOKIDAR_USEPOLLING",
                "Same, for Vite HMR (frontend).",
                default="false",
                in_prod=False,
            ),
            Field(
                "WATCHPACK_POLLING",
                "Same, for Vite HMR (frontend, alternate watcher).",
                default="false",
                in_prod=False,
            ),
        ),
    ),
    Section(
        "Redis auth (production)",
        (
            Field(
                "REDIS_USER",
                "Leave both blank for no auth. Set both to require auth — compose threads them into KRUTRIM_AGENT_REDIS_URL.",
                default="default",
                in_dev=False,
            ),
            Field("REDIS_PASSWORD", "Paired with REDIS_USER.", in_dev=False),
        ),
    ),
    Section(
        "CPU / GPU torch build (docker/{backend,celery}.Dockerfile)",
        (
            Field(
                "TORCH_BACKEND",
                "'cpu' (default) skips ~5GB of nvidia-* CUDA libs. Only set 'gpu' on a real CUDA (linux/amd64) host.",
                context="Also uncomment the `deploy:` device-reservation block on backend/celery-worker in the compose file.",
                default="cpu",
                in_dev=False,
            ),
        ),
    ),
]


def all_fields() -> list[Field]:
    return [f for section in SECTIONS for f in section.fields]
