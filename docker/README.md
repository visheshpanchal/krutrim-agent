# docker/

Everything needed to run the whole stack — frontend, backend, Celery worker, Redis — on your laptop's Docker engine with one `docker compose up`, instead of starting each piece by hand (`uv run uvicorn ...`, `uv run celery ...`, `pnpm run web`, ...).

## Files in this folder

| File | Builds | Used by |
|---|---|---|
| [`backend.Dockerfile`](./backend.Dockerfile) | `services/krutrim_agent_backend` — the FastAPI app. Multi-stage: `dev` (hot-reload) / `prod` (minimal, non-root) targets | both compose files' `backend` service |
| [`celery.Dockerfile`](./celery.Dockerfile) | `services/krutrim_agent_celery` — the Celery worker (RAG document ingestion, embeddings precompute). Same `dev` / `prod` targets | both compose files' `celery-worker` service |
| [`frontend.Dockerfile`](./frontend.Dockerfile) | `apps/web` — Vite/React. `dev` target = Vite dev server + HMR; `prod` target = static build served by unprivileged nginx | both compose files' `frontend` service |
| [`nginx.conf`](./nginx.conf) | Static-file + SPA fallback config for the frontend image (listens on 8080, non-root) | `frontend.Dockerfile` |
| [`docker-compose.yml`](./docker-compose.yml) | **Production** stack — `prod` image targets, no source mounted, immutable | You, directly |
| [`docker-compose.dev.yml`](./docker-compose.dev.yml) | **Local dev** stack — `dev` image targets, source bind-mounted, in-container reloaders | You, directly |

Env files (`.env`, `.env.dev`, `.env.prod`) are generated from the repo root, not committed — see the root [README](../README.md#environment-variables) and [ENV.md](../ENV.md).

## The architecture this sets up

```
Your laptop's Docker engine
├─ frontend        (nginx, static build)          :4200 → browser
├─ backend         (FastAPI)                       :8000 → browser (AG-UI/SSE)
├─ celery-worker   (RAG ingestion + embeddings precompute)
├─ redis           (Celery broker/result-backend)  :6379
```

The agent graph runs **in-process** inside the `backend` container against a
plain filesystem sandbox scoped to each session's workspace dir under
`HOME_ROOT` — no per-session containers, no `/var/run/docker.sock` mount,
no Docker-in-Docker.

## One-time setup

### 1. faisslite over HTTPS (private repo)

`krutrim-agent-management` (used by both `krutrim_agent_backend` and `krutrim_agent_celery`) depends on `faisslite`, hosted at [github.com/visheshpanchal/faisslite](https://github.com/visheshpanchal/faisslite) — a **private** repo. `pyproject.toml`/`uv.lock` already point at it over HTTPS. `uv sync` inside the build needs credentials to clone it — no SSH key is set up on this machine, so instead the build takes a **GitHub token as a BuildKit secret**, mounted only for that one layer and never written into any image layer (see the `RUN --mount=type=secret,...` step in `backend.Dockerfile`/`celery.Dockerfile`).

One-time setup:

1. Create the token file (gitignored — `docker/.secrets/` — never committed):
   ```bash
   mkdir -p docker/.secrets
   gh auth token > docker/.secrets/github_token   # reuses your existing gh CLI login
   chmod 600 docker/.secrets/github_token
   ```
   `gh auth token` reuses whatever broad-scoped session token `gh auth login` set up (scopes: `repo`, `gist`, `read:org`, `workflow`). That's fine to get started, but it's more than this build needs — swap in a [fine-grained PAT](https://github.com/settings/personal-access-tokens/new) scoped to read-only **Contents** on just the `faisslite` repo when you want tighter scoping (same file, same format, just the token string).
2. `docker-compose.yml` already references this file via its top-level `secrets:` block and passes it to `backend`/`celery-worker`'s builds — no extra flags needed for `docker compose build`.
3. Building a single Dockerfile manually (outside compose) needs the flag explicitly:
   ```bash
   docker build --secret id=github_token,src=docker/.secrets/github_token \
     -f docker/backend.Dockerfile -t krutrim_agent-backend backend
   ```

If `docker/.secrets/github_token` doesn't exist, the build fails fast (`required=true` on the secret mount) rather than silently baking in a broken auth state.

### 2. Env vars — one shared `.env`

```bash
python3 -m scripts.generate_env dev   # from the repo root — fill in OPENROUTER_API_KEY, TAVILY_API_KEY
```

There's exactly **one** real env file, at the repo root. `backend/.env`, `apps/web/.env.local`, and `docker/.env` are committed *symlinks* pointing at it. Edit values in the root `.env` only. See the root [README](../README.md#environment-variables) / [ENV.md](../ENV.md) for the generator and every field.

`docker-compose.yml` also loads the root `.env` directly via `env_file` on `backend`/`celery-worker`, and overrides the Redis URL / storage root to the in-network values.

`REDIS_USER`/`REDIS_PASSWORD` gate Redis auth for the `redis` service — see "Redis auth" below.

## Running it

### Production stack (`docker-compose.yml`)

```bash
python3 -m scripts.generate_env prod   # writes .env — fill in required keys
cp .env .env.prod                      # same content, used as env_file for backend/celery
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
```

(both `.env` and `.env.prod` are git-ignored)

- Frontend: http://localhost:4200
- Backend: http://localhost:8000
- Redis: localhost:6379

Images are built from each Dockerfile's `prod` target: no `uv`/`pnpm`/git, no
build caches, non-root (every service, including `frontend` on
nginx-unprivileged).
`no-new-privileges`, `init: true`, and — for the frontend — a `read_only`
rootfs with tmpfs scratch are set. Nothing from your working tree is mounted
in, so a **code change means `build` + `up` again**.

### Local dev stack (`docker-compose.dev.yml`)

```bash
python3 -m scripts.generate_env dev --out .env.dev   # once (git-ignored); optional — starts without it, minus API keys
docker compose -f docker/docker-compose.dev.yml up --build
```

- Frontend (Vite dev server + HMR): http://localhost:4200
- Backend (uvicorn `--reload`): http://localhost:8000

Built from the `dev` targets. Your `backend/` tree and the repo root are
**bind-mounted** into the containers, so editing a file on the host needs
**no rebuild** — the change is live in the container immediately:

| service | reloader | notes |
|---|---|---|
| `backend` | `uvicorn --reload` | scoped to `services/` + `libs/` (not `harness/`, which the app writes to) |
| `frontend` | Vite HMR | `nx serve web` bound to `0.0.0.0:4200` |
| `celery-worker` | none — restart by hand | a worker restart re-imports torch/docling, too expensive per save. After a task-code change: `docker compose -f docker/docker-compose.dev.yml restart celery-worker` |

Env comes from `../.env.dev` (git-ignored; `python3 -m scripts.generate_env dev --out .env.dev`). The project name defaults to
`krutrim-agent-dev` (override with `COMPOSE_PROJECT_NAME`), so its containers
and volumes never collide with the production stack's.

Only a **dependency-manifest change** needs a rebuild:

```bash
# after editing pyproject.toml / uv.lock / package.json / pnpm-lock.yaml
docker compose -f docker/docker-compose.dev.yml up --build
```

Don't use `docker compose watch` here: it **copies** changed files into the
container instead of relying on the bind mount, and rebuilds the whole image
on any manifest touch. Plain `up` (with `--build` when a manifest changed) is
the loop.

The frontend's `node_modules` lives in a named volume (`krutrim-web-node-modules-dev`)
seeded from the image, so a dependency change after `--build` also needs that
volume dropped: `docker compose -f docker/docker-compose.dev.yml down -v`. The
backend/celery venv is baked into the image (`/opt/venv`, not a volume), so a
plain `--build` refreshes it cleanly.

**macOS / Windows:** native filesystem events don't reach bind mounts through
the Docker VM. If a save isn't picked up, set `WATCHFILES_FORCE_POLLING=true`
(backend) and/or `CHOKIDAR_USEPOLLING=true` / `WATCHPACK_POLLING=true`
(frontend) in `.env.dev`.

### CPU / GPU and the vector store (both stacks)

Backend settings use the **`KRUTRIM_AGENT_` env prefix** — pydantic-settings
strips it and assigns to the field (`KRUTRIM_AGENT_QDRANT_URL` → `qdrant_url`).
`DEV_MODE`, `REDIS_*` and `LANGFUSE_*` also accept a bare name; `OPENROUTER_*`,
`TAVILY_*`, `TORCH_BACKEND`, `COMPOSE_*`, `VITE_BACKEND_URL` and the `*_POLLING`
toggles are always bare. See the root [README](../README.md#environment-variables) / [ENV.md](../ENV.md).

- **`TORCH_BACKEND=cpu` (default) | `gpu`** — build arg (bare), read by the
  `builder` stage, so it applies to **dev and prod alike**. `gpu` pulls CUDA
  torch + `faiss-gpu-cu12`; helps only on a CUDA linux/amd64 host, and you must
  also uncomment the `deploy:` device-reservation block on `backend` /
  `celery-worker` (needs `nvidia-container-toolkit`). Rebuild after changing it.
- **Vector store: `faisslite` (default) or `qdrant`** — *not* a build-time
  choice (both clients ship in every image). In your env file set
  `KRUTRIM_AGENT_VECTOR_STORE_BACKEND=qdrant`, `COMPOSE_PROFILES=qdrant`, and
  `KRUTRIM_AGENT_QDRANT_URL=http://qdrant:6333` — no rebuild.
- **Tavily search** — set `TAVILY_API_KEY=…` (bare). Tavily is currently the
  only registered web-search provider; without the key, `web_search` returns
  an error instead of results.
- **`COMPOSE_PROJECT_NAME`** — both compose files use
  `name: ${COMPOSE_PROJECT_NAME:-krutrim-agent[-dev]}`, so setting it (shell or
  repo-root `.env`) runs a fully isolated second copy of a stack — its own
  containers, network, and named volumes.

---

`docker compose down` stops everything; add `-v` only if you also want to drop
the *named volumes* (this does **not** touch your bind-mounted data — see below).

## Persistent data

Two things are bind-mounted from your real home directory / repo, not stored inside the containers, so `docker compose down` / image rebuilds — even `down -v` — never lose them:

- `${HOME}/.krutrim_agent` → `/data/krutrim_agent` inside `backend` and `celery-worker` (`HOME_ROOT` point at that fixed in-container path) — projects, sessions, per-session workspaces, plus `config.json` / `mcp.json` / `credentials.json` / `user.db` / `.jwt_secret` (see `krutrim_agent_management/local.py`'s docstring for the full layout). Bind-mounted to your real home dir so it survives `docker compose down`/rebuilds and stays directly inspectable, and shared between the two services so RAG ingestion sees the same workspaces the backend writes. An unset `$HOME` in the shell running `docker compose` makes the mount fail loudly rather than silently falling back to in-image storage.
- `backend/harness/memory` → `/app/harness/memory` — per-agent provider settings (`settings.json`) and run transcripts. Gitignored, written at runtime.

Both processes point at the *same* `HOME_ROOT` (matching how the non-Docker dev setup already runs backend + Celery against one shared `~/.krutrim_agent`) — see that module's docstring for the "not safe for concurrent writes across processes" caveat, which is an existing constraint, not something Docker introduces.

## Redis auth

Off by default — leave `REDIS_USER`/`REDIS_PASSWORD` blank in `.env` and `redis` starts with no password, same as before, with its port published straight to your host (`6379:6379`).

Set both to turn it on:

```bash
# in .env
REDIS_USER=default   # Redis's built-in user name — not a placeholder, leave as "default"
REDIS_PASSWORD=some-real-password
```

`docker-compose.yml` threads this two places:
- `redis`'s own `command:` passes `--requirepass ${REDIS_PASSWORD}` (as an array, not a shell string — see the comment in `docker-compose.yml` for why that distinction matters for the blank case).
- `backend`/`celery-worker`'s `KRUTRIM_AGENT_REDIS_URL` only embeds `user:pass@` when `REDIS_PASSWORD` is actually set (`${REDIS_PASSWORD:+...}`) — sending `AUTH` to a `redis-server` that has no password configured is itself a Redis error, so the credentialed and uncredentialed forms of the URL can't be the same string.

This project doesn't set up Redis ACLs (multiple named users with different permissions) — `REDIS_USER` exists so the connection URL has a username segment to put in front of the password (`redis://user:pass@host:port`, the standard Redis URI form), not because there's more than one user configured.

## Frontend build-time URL

`VITE_BACKEND_URL` is baked into the frontend's static JS at *build* time (Vite convention — there's no server to read env vars from at runtime). It must be a URL your **browser** can reach, which is the backend's port published to the host (`http://localhost:8000` by default, sourced from `.env`) — never the internal compose service name `http://backend:8000`, since the browser runs outside the compose network entirely.

To point at a different backend, either change `VITE_BACKEND_URL` in `.env` and rebuild, or override the build arg directly for a one-off:

```bash
docker compose -f docker/docker-compose.yml build \
  --build-arg VITE_BACKEND_URL=https://your-deployed-backend.example.com frontend
```
