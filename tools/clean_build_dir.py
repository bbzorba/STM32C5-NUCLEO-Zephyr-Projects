#!/usr/bin/env python3
"""Remove a build directory in a shell-agnostic way."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args()

    build_dir = Path(args.build_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=False)
        print(f"Cleaned: {build_dir}")
    else:
        print(f"Nothing to clean: {build_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
