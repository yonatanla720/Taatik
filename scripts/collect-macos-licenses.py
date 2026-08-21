#!/usr/bin/env python3
"""Collect exact upstream license files for components in the macOS app."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import shutil
import sys
import sysconfig


def copy_distribution_licenses(distribution: str, destination: Path) -> None:
    dist = importlib.metadata.distribution(distribution)
    copied = 0
    for item in dist.files or []:
        lowered = str(item).lower()
        if "license" not in lowered and "copying" not in lowered:
            continue
        source = Path(dist.locate_file(item))
        if not source.is_file():
            continue
        relative = Path(*item.parts[1:]) if len(item.parts) > 1 else Path(item.name)
        target = destination / distribution / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    if copied == 0:
        metadata = dist.metadata
        notice = destination / f"{distribution}-package-metadata.txt"
        notice.write_text(
            "\n".join(
                filter(
                    None,
                    (
                        f"Name: {metadata.get('Name', distribution)}",
                        f"Version: {dist.version}",
                        f"License-Expression: {metadata.get('License-Expression', '')}",
                        f"License: {metadata.get('License', '')}",
                        f"Project-URL: {metadata.get('Project-URL', '')}",
                    ),
                )
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: collect-macos-licenses.py DEST WHISPER_SOURCE FFMPEG_SOURCE", file=sys.stderr)
        return 2
    destination, whisper_source, ffmpeg_source = map(lambda value: Path(value).resolve(), sys.argv[1:])
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(whisper_source / "LICENSE", destination / "whisper.cpp-MIT.txt")
    shutil.copy2(ffmpeg_source / "COPYING.LGPLv2.1", destination / "FFmpeg-LGPL-2.1.txt")
    for distribution in (
        "PySide6",
        "PySide6-Essentials",
        "PySide6-Addons",
        "shiboken6",
        "certifi",
        "pyinstaller",
    ):
        copy_distribution_licenses(distribution, destination)

    python_license = next(
        (
            candidate
            for candidate in (
                Path(sys.base_prefix) / "LICENSE",
                Path(sys.base_prefix) / "LICENSE.txt",
                Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
            )
            if candidate.is_file()
        ),
        None,
    )
    if python_license is None:
        raise RuntimeError(f"No Python license found under {sys.base_prefix}")
    shutil.copy2(python_license, destination / "Python-PSF.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
