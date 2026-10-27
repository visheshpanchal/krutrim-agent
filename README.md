# Krutrim Agent

An agent application for everyday tasks. The core is built with LangChain, LangGraph and Deepagents, and the React frontend streams from it over the AG-UI protocol.

- **Backend** — FastAPI service and Celery worker (`backend/`, a single `uv` workspace)
- **Frontend** — React (Vite) web app in an Nx workspace (`apps/`, `libs/`)

## Features

### Chat

The plain chat screen (`POST /api/chat`) — a ReAct loop on one model with a fixed toolset, separate from the agent profiles.

| Feature | Status | Notes |
| --- | --- | --- |
|||

## Setup

Requires [uv](https://docs.astral.sh/uv/), Node 20+ and [pnpm](https://pnpm.io).

```bash
make env dev           # writes .env for local dev — fill in OPENROUTER_API_KEY and TAVILY_API_KEY
make backend-sync      # creates backend/.venv and installs every workspace package
make frontend-sync     # installs frontend libraries
```

Verify the install:

```bash
source backend/.venv/bin/activate
make backend-check     # checks backend libraries and prints every env var
make frontend-check    # checks node/pnpm and frontend libraries
```


Start the web dev server with `make frontend-web`.

### Environment variables

`scripts/env_schema.py` is the single source of truth for every env var this project reads; `make env` runs `scripts/generate_env.py` to generate a `.env` from it:

```bash
make env               # show options
make env dev           # local development — most fields, terse comments
make env prod          # production deploy — required + prod-relevant fields only
make env full          # every field, all commented, section-wise (reference dump)
make env docs          # regenerate ENV.md from the same schema
```

Add `FORCE=1` to overwrite an existing output file, or `OUT=<path>` to write somewhere other than the repo-root `.env` (e.g. `make env prod FORCE=1`). See [ENV.md](ENV.md) for what every field does.

## Testing

```bash
make backend-test                 # pytest
make backend-check-code-quality   # ruff lint + format check, vulture dead-code scan
make backend-typing               # ty type check
make backend-style                # sort imports, fix lint, format (rewrites files)

make frontend-lint                # eslint
make frontend-build               # build every Nx project
make frontend-test                # vitest
make frontend-graph               # print the Nx project graph
```

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Author

Vishesh Panchal
