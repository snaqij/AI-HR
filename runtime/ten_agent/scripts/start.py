#!/usr/bin/env python3
"""Cross-platform startup script for the AI-HR Python TEN app."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def prepend_env_paths(name: str, paths: list[Path]) -> None:
    existing = os.environ.get(name, "")
    valid_paths = [str(path) for path in paths if path.exists()]
    if existing:
        valid_paths.append(existing)
    if valid_paths:
        os.environ[name] = os.pathsep.join(valid_paths)


def materialize_property_file(app_root: Path, property_arg: str | None) -> None:
    property_path = property_arg or os.environ.get("AI_HR_TEN_PROPERTY_FILE")
    if not property_path:
        return

    source = Path(property_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"TEN property file not found: {source}")

    target = app_root / "property.json"
    if source != target:
        shutil.copy2(source, target)
    print(f"[start.py] using property file: {source}", flush=True)
    print(f"[start.py] materialized runtime property to: {target}", flush=True)


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--property", dest="property_file")
    return parser.parse_known_args(argv)


def main() -> int:
    args, passthrough = parse_args(sys.argv[1:])

    app_root = Path(__file__).resolve().parent.parent
    project_root = app_root.parent
    os.chdir(app_root)

    load_env_file(app_root / ".env")
    materialize_property_file(app_root, args.property_file)

    if sys.platform == "win32":
        dll_path = app_root / "ten_packages" / "system" / "ten_runtime_python" / "lib" / "ten_runtime_python.dll"
        pyd_path = app_root / "ten_packages" / "system" / "ten_runtime_python" / "lib" / "libten_runtime_python.pyd"
        if dll_path.exists() and not pyd_path.exists():
            shutil.copy2(dll_path, pyd_path)

    prepend_env_paths(
        "PYTHONPATH",
        [
            project_root,
            app_root,
            app_root / "ten_packages" / "system" / "ten_runtime_python" / "lib",
            app_root / "ten_packages" / "system" / "ten_runtime_python" / "interface",
            app_root / "ten_packages" / "system" / "ten_ai_base" / "interface",
            app_root / "ten_packages" / "system",
        ],
    )
    prepend_env_paths(
        "NODE_PATH",
        [app_root / "ten_packages" / "system" / "ten_runtime_nodejs" / "lib"],
    )

    is_windows = sys.platform == "win32"
    lib_var = "PATH" if is_windows else "LD_LIBRARY_PATH"
    prepend_env_paths(
        lib_var,
        [
            app_root / "ten_packages" / "system" / "ten_runtime" / "lib",
            app_root / "ten_packages" / "system" / "agora_rtc_sdk" / "lib",
            app_root / "ten_packages" / "extension" / "agora_rtc" / "lib",
        ],
    )

    main_py = app_root / "main.py"
    if not main_py.exists():
        print(f"[start.py] Error: {main_py} not found", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(main_py), *passthrough]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
