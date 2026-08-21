#!/usr/bin/env python3
"""Write Taatik's macOS icon PNG using the shared icon design."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taatik.icon import icon_png


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: create-macos-icon.py OUTPUT.png", file=sys.stderr)
        return 2
    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # 1024px is the macOS app-icon master size; ss=2 keeps rendering quick.
    output.write_bytes(icon_png(1024, ss=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
