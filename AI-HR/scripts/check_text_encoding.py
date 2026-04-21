"""Check UTF-8 encoding and detect common mojibake fragments."""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_EXTENSIONS = {".py", ".md", ".toml", ".yaml", ".yml", ".sql", ".txt", ".json"}
DEFAULT_EXCLUDE_PATH_PARTS = (
    ".venv",
    "__pycache__",
    "ten_framework/third_party",
    "scratch",
)
DEFAULT_EXCLUDE_FILES = {"scripts/check_text_encoding.py"}

# Common garbled fragments observed in UTF-8/GBK mis-decoding cases.
DEFAULT_MOJIBAKE_MARKERS = (
    "闈㈣瘯",
    "浼氳瘽",
    "缁存姢",
    "杩涚▼",
    "鍗曚緥",
    "鏈叧鑱",
    "椤圭洰娣辨寲",
    "鏃犲巻鍙",
    "澶囬€",
    "棣栬疆 AI 璇煶闈㈣瘯",
    "銆?",
    "鈹",
)


def _is_excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix().lower()
    if rel in DEFAULT_EXCLUDE_FILES:
        return True
    return any(part in rel for part in DEFAULT_EXCLUDE_PATH_PARTS)


def _iter_files(root: Path, extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        if _is_excluded(path, root):
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Check UTF-8 encoding and mojibake markers.")
    parser.add_argument("--root", default=".", help="Project root path")
    parser.add_argument("--strict-mojibake", action="store_true", help="Fail when mojibake markers are detected")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = _iter_files(root, DEFAULT_EXTENSIONS)

    non_utf8: list[Path] = []
    mojibake_hits: list[tuple[Path, int, str]] = []

    for file_path in files:
        data = file_path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            non_utf8.append(file_path)
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            for marker in DEFAULT_MOJIBAKE_MARKERS:
                if marker in line:
                    mojibake_hits.append((file_path, lineno, marker))
                    break

    if non_utf8:
        print("[encoding] Non-UTF8 files detected:")
        for item in non_utf8:
            print(f"  - {str(item).encode('ascii', 'backslashreplace').decode('ascii')}")

    if mojibake_hits:
        print("[mojibake] Suspicious text fragments detected:")
        for file_path, lineno, marker in mojibake_hits[:200]:
            safe_path = str(file_path).encode("ascii", "backslashreplace").decode("ascii")
            safe_marker = marker.encode("ascii", "backslashreplace").decode("ascii")
            print(f"  - {safe_path}:{lineno} marker={safe_marker}")
        if len(mojibake_hits) > 200:
            print(f"  ... truncated {len(mojibake_hits) - 200} more hits")

    if non_utf8:
        return 1
    if args.strict_mojibake and mojibake_hits:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
