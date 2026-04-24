#!/usr/bin/env python3
"""Resolve and install Python extension dependencies for the TEN app."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    app_root = Path(__file__).resolve().parent.parent
    deps_resolver = (
        app_root
        / "ten_packages"
        / "system"
        / "ten_runtime_python"
        / "tools"
        / "deps_resolver.py"
    )

    if not deps_resolver.exists():
        print(f"[bootstrap.py] Error: {deps_resolver} not found", file=sys.stderr)
        return 1

    result = subprocess.run([sys.executable, str(deps_resolver)], cwd=app_root)
    if result.returncode != 0:
        return result.returncode

    merged_requirements = app_root / "merged_requirements.txt"
    if not merged_requirements.exists():
        return 0

    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(merged_requirements)],
        cwd=app_root,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
