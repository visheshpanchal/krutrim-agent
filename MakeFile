BACKEND_DIR := backend
ENV_MODES := dev prod full docs

# `make env <mode>`: take the word after `env` as the mode and no-op it as a goal
ifeq (env,$(firstword $(MAKECMDGOALS)))
ENV_MODE := $(word 2,$(MAKECMDGOALS))
.PHONY: $(ENV_MODES)
$(ENV_MODES):
	@:
endif

.PHONY: env backend-style backend-typing backend-check-code-quality backend-test \
	backend-sync backend-check \
	frontend-build frontend-web frontend-test frontend-sync frontend-check \
	frontend-lint frontend-graph

# make env [dev|prod|full|docs] [FORCE=1] [OUT=<path>] — no mode shows options
env:
	python3 -m scripts.generate_env $(ENV_MODE) $(if $(FORCE),--force) $(if $(OUT),--out $(OUT))

# ── Backend ────────────────────────────────────────────────────────────

# Sort imports, apply lint fixes, format
backend-style:
	cd $(BACKEND_DIR) && uv run ruff check --select I --fix .
	cd $(BACKEND_DIR) && uv run ruff check --fix .
	cd $(BACKEND_DIR) && uv run ruff format .

backend-typing:
	cd $(BACKEND_DIR) && uvx ty check .

# Lint, format check and dead-code scan (no changes made)
backend-check-code-quality:
	cd $(BACKEND_DIR) && uv run ruff check .
	cd $(BACKEND_DIR) && uv run ruff format --check .
	cd $(BACKEND_DIR) && uv run vulture libs services --min-confidence 80 --exclude "*/.venv/*"

backend-test:
	cd $(BACKEND_DIR) && uv run pytest

# Create backend/.venv if missing, then install every workspace package into it
backend-sync:
	cd $(BACKEND_DIR) && (test -d .venv || uv venv .venv)
	cd $(BACKEND_DIR) && UV_PROJECT_ENVIRONMENT=.venv uv sync --all-packages

# Needs an activated venv: source backend/.venv/bin/activate
backend-check:
	python -m scripts.check_backend

# ── Frontend ───────────────────────────────────────────────────────────

frontend-build:
	pnpm run build

frontend-web:
	pnpm run web

frontend-test:
	pnpm run test

frontend-sync:
	pnpm install

frontend-check:
	python3 -m scripts.check_frontend

frontend-lint:
	pnpm run lint

frontend-graph:
	pnpm exec nx graph --print
