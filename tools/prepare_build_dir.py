#!/usr/bin/env python3
"""Remove stale Zephyr build directories when project path changes.

When a build directory is copied between machines, CMake caches absolute source
paths (for example CMAKE_HOME_DIRECTORY). If those paths no longer match the
current workspace location, west pristine can fail before it can clean.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


CACHE_KEYS = (
    "CMAKE_HOME_DIRECTORY:INTERNAL=",
    "APPLICATION_SOURCE_DIR:PATH=",
)


def _read_cached_source(cache_file: Path) -> Path | None:
    try:
        for raw_line in cache_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            for key in CACHE_KEYS:
                if raw_line.startswith(key):
                    value = raw_line[len(key) :].strip()
                    if value:
                        return Path(value).resolve()
    except OSError:
        return None
    return None


def ensure_fresh_build_dir(build_dir: Path, source_dir: Path) -> int:
    cache_file = build_dir / "CMakeCache.txt"
    if not cache_file.exists():
        return 0

    cached_source = _read_cached_source(cache_file)
    if cached_source is None:
        return 0

    current_source = source_dir.resolve()
    if cached_source == current_source:
        return 0

    print(
        f">>> Removing stale build directory '{build_dir}'\n"
        f"    cached source: {cached_source}\n"
        f"    current source: {current_source}"
    )
    shutil.rmtree(build_dir, ignore_errors=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

    return ensure_fresh_build_dir(Path(args.build_dir), Path(args.source_dir))


if __name__ == "__main__":
    raise SystemExit(main())
