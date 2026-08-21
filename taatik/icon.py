"""Render Taatik's app icon as PNG bytes using only the standard library.

The artwork is a brand-green rounded tile holding a cream page: an audio
waveform at the top resolves into text lines below, i.e. "audio to transcript".
Shapes are drawn on a supersampled buffer and box-downsampled so edges and
rounded corners are anti-aliased without any imaging dependency.
"""

from __future__ import annotations

import binascii
import struct
import zlib

# Palette shared with the app UI.
TILE = (23, 107, 75)       # #176b4b brand green
PAGE = (248, 246, 237)     # warm cream
INK = (20, 58, 43)         # #143a2b deep green for waveform + text


def _blend(buf: bytearray, R: int, x0: int, y0: int, x1: int, y1: int,
           rx0: int, ry0: int, rx1: int, ry1: int, radius: int,
           color: tuple[int, int, int]) -> None:
    """Paint an opaque rounded rectangle onto the RGBA buffer."""
    r2 = radius * radius
    x0 = max(x0, 0); y0 = max(y0, 0); x1 = min(x1, R); y1 = min(y1, R)
    for y in range(y0, y1):
        for x in range(x0, x1):
            cx = rx0 + radius if x < rx0 + radius else (rx1 - radius - 1 if x > rx1 - radius - 1 else x)
            cy = ry0 + radius if y < ry0 + radius else (ry1 - radius - 1 if y > ry1 - radius - 1 else y)
            if (x - cx) ** 2 + (y - cy) ** 2 > r2:
                continue
            i = (y * R + x) * 4
            buf[i] = color[0]; buf[i + 1] = color[1]; buf[i + 2] = color[2]; buf[i + 3] = 255


def _round_rect(buf, R, x0, y0, x1, y1, radius, color):
    _blend(buf, R, x0, y0, x1, y1, x0, y0, x1, y1, radius, color)


def _render_supersampled(R: int) -> bytearray:
    buf = bytearray(R * R * 4)  # transparent

    def u(v: float) -> int:  # unit (0..1) -> pixels
        return int(round(v * R))

    # Green tile with a small transparent margin.
    m, tr = u(0.055), u(0.22)
    _round_rect(buf, R, m, m, R - m, R - m, tr, TILE)

    # Cream page, portrait, centred.
    px0, px1, py0, py1, pr = u(0.255), u(0.745), u(0.20), u(0.80), u(0.045)
    _round_rect(buf, R, px0, py0, px1, py1, pr, PAGE)

    # Audio waveform: symmetric vertical bars in the upper third of the page.
    heights = (0.34, 0.60, 0.85, 1.0, 0.72, 0.48, 0.30)
    bar_w = u(0.028)
    gap = u(0.0225)
    span = len(heights) * bar_w + (len(heights) - 1) * gap
    start = (R - span) // 2
    mid = u(0.345)
    max_h = u(0.11)
    for k, h in enumerate(heights):
        bx = start + k * (bar_w + gap)
        half = max(int(max_h * h), bar_w // 2)
        _round_rect(buf, R, bx, mid - half, bx + bar_w, mid + half, bar_w // 2, INK)

    # Transcript: text lines below the waveform.
    lx = u(0.335)
    line_h = u(0.032)
    for ly, rx in ((0.505, 0.665), (0.595, 0.605), (0.685, 0.665), (0.775, 0.560)):
        _round_rect(buf, R, lx, u(ly), u(rx), u(ly) + line_h, line_h // 2, INK)

    return buf


def _downsample(buf: bytearray, R: int, ss: int) -> bytearray:
    size = R // ss
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            ar = ag = ab = aa = 0
            for dy in range(ss):
                row = (y * ss + dy) * R
                for dx in range(ss):
                    i = (row + x * ss + dx) * 4
                    a = buf[i + 3]
                    ar += buf[i] * a
                    ag += buf[i + 1] * a
                    ab += buf[i + 2] * a
                    aa += a
            o = (y * size + x) * 4
            n = ss * ss
            if aa:
                out[o] = ar // aa
                out[o + 1] = ag // aa
                out[o + 2] = ab // aa
            out[o + 3] = aa // n
    return out


def _png(rgba: bytearray, size: int) -> bytes:
    rows = bytearray()
    stride = size * 4
    for y in range(size):
        rows.append(0)  # no filter
        rows.extend(rgba[y * stride:(y + 1) * stride])

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = binascii.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def icon_png(size: int, ss: int = 4) -> bytes:
    """Return a PNG of the icon at the given pixel size, anti-aliased."""
    return _png(_downsample(_render_supersampled(size * ss), size * ss, ss), size)


def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Write a multi-resolution Windows .ico with PNG-encoded entries."""
    images = [(s, icon_png(s)) for s in sizes]
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = bytearray()
    blob = bytearray()
    for size, png in images:
        b = size if size < 256 else 0
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(png), offset)
        blob += png
        offset += len(png)
    from pathlib import Path
    Path(path).write_bytes(header + bytes(entries) + bytes(blob))
