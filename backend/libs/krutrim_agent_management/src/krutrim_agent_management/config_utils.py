import os
from pathlib import Path


def find_backend_root(start: Path) -> Path:
    """Walks up from `start` for the `backend/` checkout root (holds `harness/` and `.env`)."""
    for candidate in (start, *start.parents):
        if (candidate / "harness").is_dir():
            return candidate
    return start


def env_files(backend_root: Path) -> tuple[Path, ...]:
    """Ordered dotenv paths, lowest priority first.

    Always `<BACKEND_ROOT>/.env`, then an optional environment-specific file
    named by KRUTRIM_AGENT_ENV_FILE (e.g. `.env.dev`, `.env.prod`). That var
    must come from the real environment — a shell export or the docker-compose
    `environment:` block — it cannot live in the file it selects. A relative
    value resolves against BACKEND_ROOT; a missing file is skipped.
    """
    files = []
    override = os.getenv("KRUTRIM_AGENT_ENV_FILE", "").strip()
    if override:
        candidate = Path(override)
        files.append(candidate if candidate.is_absolute() else backend_root / candidate)
    if not files:
        files.append(backend_root / ".env")
    return tuple(files)


def get_redis_url() -> str:
    """Builds a Redis URL from env vars; REDIS_URL overrides everything else if set."""
    direct_url = os.getenv("REDIS_URL")
    if direct_url:
        return direct_url

    user = os.getenv("REDIS_USER", "")
    password = os.getenv("REDIS_PASSWORD", "")
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv("REDIS_DB", "0")
    use_tls = os.getenv("REDIS_USE_TLS", "false").lower() == "true"

    scheme = "rediss" if use_tls else "redis"

    if user and password:
        auth = f"{user}:{password}@"
    elif password:
        auth = f":{password}@"
    else:
        auth = ""

    return f"{scheme}://{auth}{host}:{port}/{db}"
