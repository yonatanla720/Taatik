#!/usr/bin/env python3
"""Generate Taatik's explicit placeholder icon using only the standard library."""

from __future__ import annotations

import binascii
from pathlib import Path
import struct
import sys
import zlib


def pixel(size: int, x: int, y: int) -> tuple[int, int, int, int]:
    scale = size / 1024
    left, top, right, bottom = (int(value * scale) for value in (72, 72, 952, 952))
    radius = int(160 * scale)
    inside = left <= x < right and top <= y < bottom
    if inside:
        corner_x = left + radius if x < left + radius else right - radius - 1
        corner_y = top + radius if y < top + radius else bottom - radius - 1
        if (x < left + radius or x >= right - radius) and (y < top + radius or y >= bottom - radius):
            inside = (x - corner_x) ** 2 + (y - corner_y) ** 2 <= radius ** 2
    if not inside:
        return (0, 0, 0, 0)

    # Green tile, cream page, and transcription lines. This is intentionally a
    # placeholder rather than final brand artwork.
    color = (24, 104, 76, 255)
    if int(270 * scale) <= x < int(754 * scale) and int(194 * scale) <= y < int(830 * scale):
        color = (248, 246, 237, 255)
    for line_y, line_right in ((360, 670), (470, 620), (580, 690), (690, 570)):
        if int(line_y * scale) <= y < int((line_y + 42) * scale):
            if int(350 * scale) <= x < int(line_right * scale):
                color = (24, 104, 76, 255)
    return color


def write_png(path: Path, size: int) -> None:
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            rows.extend(pixel(size, x, y))

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = binascii.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: create-macos-icon.py OUTPUT.png", file=sys.stderr)
        return 2
    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_png(output, 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
