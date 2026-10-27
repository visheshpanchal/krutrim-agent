## Project

Krutrim Agent is an agent application for everyday tasks. The backend is a FastAPI service with a Celery worker, built on LangChain, LangGraph and Deepagents, and managed as a single `uv` workspace. The frontend is a React (Vite) app in an Nx workspace, managed with pnpm, that streams from the backend over the AG-UI protocol.

## Commands

All commands run from the repo root via `make`.

- Install: `make backend-sync` and `make frontend-sync`
- Env file: `make env dev` (`prod` / `full` / `docs` for other modes, `FORCE=1` to overwrite)
- Verify install: `make backend-check` (inside the activated backend venv) and `make frontend-check`
- Dev server: `make frontend-web`
- Build: `make frontend-build`
- Format backend: `make backend-style`

## After making a code change

Run the checks for the side you touched; all must pass before you're done. These cover everything CI runs.

Backend:

- `make backend-check-code-quality` — ruff lint, format check, vulture
- `make backend-typing` — ty (report-only in CI for now; don't add new errors)
- `make backend-test` — pytest

Frontend:

- `make frontend-lint`
- `make frontend-build`
- `make frontend-test`
