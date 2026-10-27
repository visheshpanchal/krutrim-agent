"""Check the backend venv: every declared dependency is installed, and print
every env var from scripts/env_schema.py with its resolved value.

    source backend/.venv/bin/activate
    python -m scripts.check_backend

Must run inside a virtualenv (not the global python).
"""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import tomllib

from scripts.env_schema import all_fields

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
SECRET_HINTS = ("KEY", "SECRET", "PASSWORD", "TOKEN")


def _requirements() -> list[str]:
    root = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())
    reqs = list(root.get("dependency-groups", {}).get("dev", []))
    for pyproject in sorted(BACKEND_ROOT.glob("*/*/pyproject.toml")):
        reqs += (
            tomllib.loads(pyproject.read_text())
            .get("project", {})
            .get("dependencies", [])
        )
    return reqs


def check_libraries() -> list[str]:
    from packaging.requirements import Requirement

    missing = []
    for raw in sorted(set(_requirements())):
        req = Requirement(raw)
        if req.marker and not req.marker.evaluate():
            continue
        try:
            installed = version(req.name)
        except PackageNotFoundError:
            missing.append(f"{req.name} (not installed)")
            continue
        if req.specifier and not req.specifier.contains(installed, prereleases=True):
            missing.append(f"{req.name} {installed} (needs {req.specifier})")
    return missing


def _dotenv() -> dict[str, str]:
    override = os.getenv("KRUTRIM_AGENT_ENV_FILE", "").strip()
    path = BACKEND_ROOT / (override or ".env")
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def print_env() -> list[str]:
    dotenv = _dotenv()
    missing_required = []
    for f in all_fields():
        if f.key in os.environ:
            value, source = os.environ[f.key], "env"
        elif f.key in dotenv:
            value, source = dotenv[f.key], ".env"
        else:
            value, source = f.default or "", "default"
        if not value and f.required:
            missing_required.append(f.key)
        if value and f.key.endswith(SECRET_HINTS):
            value = "****"
        flag = " [required]" if f.required else ""
        print(f"  {f.key}{flag} = {value or '<unset>'}  ({source})")
    return missing_required


def main() -> int:
    if sys.prefix == sys.base_prefix:
        print("Not in a virtualenv — run `source backend/.venv/bin/activate` first.")
        return 1
    if Path(sys.prefix).resolve() != (BACKEND_ROOT / ".venv").resolve():
        print(f"Warning: active venv is {sys.prefix}, not backend/.venv")

    print(f"Python {sys.version.split()[0]} ({sys.prefix})\n")
    missing = check_libraries()
    if missing:
        print("Missing / mismatched libraries:")
        for item in missing:
            print(f"  {item}")
    else:
        print("All backend libraries installed.")

    print("\nEnvironment variables:")
    missing_env = print_env()
    if missing_env:
        print(f"\nRequired but unset: {', '.join(missing_env)}")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
