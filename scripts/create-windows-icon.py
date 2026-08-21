#!/usr/bin/env python3
"""Write Taatik's multi-resolution Windows .ico using only the standard library."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taatik.icon import write_ico


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: create-windows-icon.py OUTPUT.ico", file=sys.stderr)
        return 2
    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_ico(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
