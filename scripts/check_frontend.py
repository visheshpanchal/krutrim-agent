"""Check node/pnpm are on PATH and every package.json dependency is installed.

    python3 -m scripts.check_frontend
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ok = True
    for tool in ("node", "pnpm"):
        if not shutil.which(tool):
            print(f"{tool} not found on PATH")
            ok = False

    package = json.loads((REPO_ROOT / "package.json").read_text())
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    missing = [
        name
        for name in sorted(deps)
        if not (REPO_ROOT / "node_modules" / name / "package.json").is_file()
    ]
    if missing:
        print("Missing libraries (run `pnpm install`):")
        for name in missing:
            print(f"  {name}")
        ok = False
    else:
        print(f"All {len(deps)} frontend libraries installed.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
