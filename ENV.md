# Environment variables

Every env var this project reads, generated from `scripts/env_schema.py` — that file is the source of truth; edit it, then run `python3 -m scripts.generate_env docs` to refresh this page.

Don't hand-write a `.env` from scratch. Instead:

```bash
python3 -m scripts.generate_env dev    # local development
python3 -m scripts.generate_env prod   # production deploy
python3 -m scripts.generate_env full   # every field, all commented (reference)
```

**Tags**

- **required** — a normal install will not work without this being set.
- **server** — `ServerSettings`: env/.env only, read once at process start; changing one needs a restart.
- **user** — `UserSettings`: hot-reloads with no restart; also editable per-user from the settings UI, which takes precedence over the value set here.
- fields with neither tag are bare names (not read through the `KRUTRIM_AGENT_` prefix) — provider SDKs, Vite, docker-compose, or Redis/Langfuse's own conventions.

## LLM / embeddings provider

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `OPENROUTER_API_KEY` | yes |  |  | OpenRouter API key — powers every LLM call (agents + chat) and RAG embeddings. Nothing works without it. |
| `OPENROUTER_BASE_URL` |  |  | `https://openrouter.ai/api/v1` | Override the OpenRouter endpoint (e.g. a local dev proxy). |
| `LITELLM_MASTER_KEY` |  |  |  | Only when OPENROUTER_BASE_URL points at a local proxy that authenticates with its own master key. Must match that proxy's own LITELLM_MASTER_KEY setting. |

## Web search

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `TAVILY_API_KEY` | yes |  |  | Tavily API key. Tavily is currently the only registered web-search provider — without this, `web_search` runs but returns an error instead of results. |
| `TAVILY_SEARCH_API_BASE` |  |  | `https://api.tavily.com` | Point tavily-python at a proxy / self-hosted gateway instead of api.tavily.com. |
| `KRUTRIM_AGENT_WEB_SEARCH_PROVIDER` |  | user | `tavily` | Web search provider selector. Only 'tavily' is registered today, so this currently has no other valid value. |

## Compose (docker/docker-compose*.yml)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `COMPOSE_PROJECT_NAME` |  |  | `krutrim-agent[-dev]` | Override to run a fully isolated second copy of a stack (own containers/network/volumes). |
| `COMPOSE_PROFILES` |  |  |  | Activates optional services. Set to `qdrant` to start the qdrant container. |

## Backend core [server]

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_HOST` |  | server | `0.0.0.0` | Bind address. |
| `KRUTRIM_AGENT_PORT` |  | server | `8000` | Bind port. |
| `KRUTRIM_AGENT_HOME_ROOT` |  | server | `~/.krutrim_agent` | Root of the runtime-config tree (.jwt_secret, user table, per-user config/mcp/credentials, storage, logs). A desktop build points this at an OS app-data dir instead. |
| `KRUTRIM_AGENT_GRAPH_RECURSION_LIMIT` |  | server | `100` | LangGraph super-step cap per agent turn — raise for deep research / subagent loops. |
| `KRUTRIM_AGENT_RAG_EMBEDDING_MODEL` |  | server | `qwen/qwen3-embedding-8b` | Embedding model for RAG ingestion + query. Server tier because it must match what's already stored in the vector index. |
| `KRUTRIM_AGENT_CORS_ORIGINS` |  | server | `["http://localhost:4200","http://localhost:5173"]` | Allowed frontend origins. Add the Vite dev-server origins locally; set to your real frontend origin(s) in production. |
| `KRUTRIM_AGENT_EDITION` |  | server | `community` | Deployment edition. |

## Backend auth [server] (krutrim_agent_backend/auth/)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_AUTH_ENABLED` |  | server | `true` | Master switch — when true, every route except register/login/refresh/health/docs needs a Bearer access token. |
| `KRUTRIM_AGENT_AUTH_JWT_SECRET` |  | server |  | HS256 signing secret. Leave unset to auto-generate and store at <HOME_ROOT>/.jwt_secret (0600) — fine for one instance. Set explicitly in production to share one secret across replicas / survive a redeploy. |
| `KRUTRIM_AGENT_AUTH_ACCESS_TTL_MINUTES` |  | server | `30` | Access token lifetime. |
| `KRUTRIM_AGENT_AUTH_REFRESH_TTL_DAYS` |  | server | `14` | Refresh token lifetime. |
| `KRUTRIM_AGENT_ADMIN_USERNAME` |  | server |  | Optional first-boot admin (only while the users table is still empty; otherwise the first /api/auth/register becomes admin). |
| `KRUTRIM_AGENT_ADMIN_PASSWORD` |  | server |  | Paired with KRUTRIM_AGENT_ADMIN_USERNAME. |

## Backend behaviour [user] (hot-reloads, also editable from the settings UI)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_DEFAULT_MODEL` |  | user | `deepseek/deepseek-v4-flash-0731` | Default OpenRouter model when nothing more specific is configured. |
| `KRUTRIM_AGENT_CONTEXT_MANAGEMENT_STRATEGY` |  | user | `off` | Auto context-window management for long turns: off \| trim \| summarize \| rag (reserved, falls back to summarize). |
| `KRUTRIM_AGENT_CONTEXT_TRIGGER_TOKENS` |  | user | `120000` | Token count that triggers the 'summarize' strategy. |
| `KRUTRIM_AGENT_CONTEXT_KEEP_MESSAGES` |  | user | `20` | Messages kept verbatim by the 'summarize' strategy. |
| `KRUTRIM_AGENT_CROSS_AGENT_CALL_TIMEOUT_SECONDS` |  | user | `60` | Max wait (1-3600s) on a peer's turn via the cross-agent message_agent tool. |
| `KRUTRIM_AGENT_RETRIEVAL_STRATEGY` |  | user | `vector_only` | Retrieval ranking/query strategy for the active vector store. |
| `KRUTRIM_AGENT_RAG_INJECTION_ENABLED` |  | user | `false` | Silently inject retrieved project context into the research agent's turn. |
| `KRUTRIM_AGENT_EVAL_RECORD_FULL_PAYLOADS` |  | user | `false` | Capture full tool-call args + a truncated result preview into the run-transcript JSONL. |
| `KRUTRIM_AGENT_EVAL_RECORD_PAYLOAD_MAX_CHARS` |  | user | `4000` | Truncation length for the above. |

## Redis / Celery

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_REDIS_URL` |  | server | `redis://localhost:6379/0` | Celery broker/result-backend. The docker stacks set this automatically; use this for a backend run directly on the host. |

## Logging [server] (krutrim_agent_management/logging_config.py — server + Celery worker)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_LOG_DIR` |  | server | `~/.krutrim_agent/logs` | Log directory root (server/server.log, worker/worker.log). |
| `KRUTRIM_AGENT_LOG_LEVEL` |  | server | `INFO` | File-sink threshold. DEBUG gives the full step-by-step trace. |
| `KRUTRIM_AGENT_LOG_CONSOLE_LEVEL` |  | server | `INFO` | stderr threshold. Forced to DEBUG when DEV_MODE=true. |
| `KRUTRIM_AGENT_LOG_ROTATION` |  | server | `1 day` | Rotation trigger — a period ('1 day'), a wall-clock time ('00:00'), or a size ('20 MB'). |
| `KRUTRIM_AGENT_LOG_RETENTION` |  | server | `14 days` | How long rotated files are kept. |
| `KRUTRIM_AGENT_LOG_COMPRESSION` |  | server |  | '' keeps rotated files plain; 'zip'/'gz'/'tar.gz' compresses them. |
| `KRUTRIM_AGENT_LOG_BACKTRACE` |  | server | `false` | Extended (variable-free) tracebacks in the file sink. Also on when DEV_MODE. |
| `KRUTRIM_AGENT_LOG_INTERCEPT_STD` |  | server | `true` | Route stdlib logging (uvicorn/celery/httpx/...) through loguru so everything shares one format/file. |

## Vector store [server] (krutrim_agent_rag — faisslite default, or qdrant)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_VECTOR_STORE_BACKEND` |  | server | `faisslite` | 'faisslite' (default, embedded) or 'qdrant'. Not a build-time choice — both clients ship in every image. For qdrant, also set COMPOSE_PROFILES=qdrant and KRUTRIM_AGENT_QDRANT_URL. |
| `KRUTRIM_AGENT_QDRANT_URL` |  | server |  | Qdrant service address (e.g. http://qdrant:6333 in-compose). |
| `KRUTRIM_AGENT_QDRANT_API_KEY` |  | server |  | Optional Qdrant auth key. |
| `KRUTRIM_AGENT_QDRANT_PREFER_GRPC` |  | server | `false` | Use Qdrant's gRPC port instead of HTTP. |
| `KRUTRIM_AGENT_QDRANT_HTTPS` |  | server | `false` | Use HTTPS for Qdrant. |
| `KRUTRIM_AGENT_QDRANT_LOCATION` |  | server |  | ':memory:' runs an embedded Qdrant (tests / no server); overrides QDRANT_URL. |
| `QDRANT_HTTP_PORT` |  |  | `6343` | Host-published Qdrant HTTP port (compose port mapping). |
| `QDRANT_GRPC_PORT` |  |  | `6344` | Host-published Qdrant gRPC port (compose port mapping). |

## RAG document parsing [server] (krutrim_agent_doc)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `PDF_PARSER_ENABLE_OCR_STAGE` |  | server | `false` | PDF parsing escalates raw-text -> OCR -> full ML layout; OCR/ML are off by default (fast raw-text stage only). |
| `PDF_PARSER_ENABLE_ML_STAGE` |  | server | `false` | Full table/layout ML stage (docling) for PDF parsing. |

## Frontend (apps/web)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `VITE_BACKEND_URL` |  |  | `http://localhost:8000` | Where the BROWSER reaches the backend. Baked in at build time for the Docker prod image; live for `vite dev`. |

## Dev mode + Langfuse tracing (dev-stack only — inert in production)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `KRUTRIM_AGENT_DEV_MODE` |  |  | `true` | Gates local-only tooling (Langfuse, verbose errors, DEBUG console/file logging). Wins over bare DEV_MODE if both are set. |
| `DEV_MODE` |  |  |  | Bare alias for KRUTRIM_AGENT_DEV_MODE. |
| `KRUTRIM_AGENT_LANGFUSE_ENABLED` |  | server | `true` | Force Langfuse tracing off even in dev mode (e.g. LANGFUSE_BASE_URL points at a host not running Langfuse). |
| `LANGFUSE_PUBLIC_KEY` |  |  |  | Langfuse public key. Only traced while dev mode is on. |
| `LANGFUSE_SECRET_KEY` |  |  |  | Langfuse secret key. |
| `LANGFUSE_BASE_URL` |  |  | `http://localhost:3000` | Self-hosted Langfuse URL; omit for Langfuse Cloud. |
| `LANGFUSE_HOST` |  |  | `https://cloud.langfuse.com` | Fallback Langfuse Cloud host if LANGFUSE_BASE_URL is unset. |
| `LANGFUSE_DOCKER_BASE_URL` |  |  |  | Read inside the docker compose files — repoints the CONTAINERS at a real Langfuse URL. |

## File-watch reliability (docker-compose.dev.yml only)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `WATCHFILES_FORCE_POLLING` |  |  | `false` | macOS/Windows: flip true if the backend's --reload stops noticing bind-mount edits (costs idle CPU). Leave false on Linux. |
| `CHOKIDAR_USEPOLLING` |  |  | `false` | Same, for Vite HMR (frontend). |
| `WATCHPACK_POLLING` |  |  | `false` | Same, for Vite HMR (frontend, alternate watcher). |

## Redis auth (production)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `REDIS_USER` |  |  | `default` | Leave both blank for no auth. Set both to require auth — compose threads them into KRUTRIM_AGENT_REDIS_URL. |
| `REDIS_PASSWORD` |  |  |  | Paired with REDIS_USER. |

## CPU / GPU torch build (docker/{backend,celery}.Dockerfile)

| Variable | Required | Tier | Default | Description |
| --- | --- | --- | --- | --- |
| `TORCH_BACKEND` |  |  | `cpu` | 'cpu' (default) skips ~5GB of nvidia-* CUDA libs. Only set 'gpu' on a real CUDA (linux/amd64) host. Also uncomment the `deploy:` device-reservation block on backend/celery-worker in the compose file. |
