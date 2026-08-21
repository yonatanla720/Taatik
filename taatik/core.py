from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from .config import SUPPORTED_EXTENSIONS

ProgressCallback = Callable[[int, str], None]


class TranscriptionError(RuntimeError):
    pass


def validate_input(path: Path) -> None:
    if not path.is_file():
        raise TranscriptionError("The selected file no longer exists.")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise TranscriptionError("This file type is not supported. Choose a common audio or video file.")


def output_base(input_path: Path, output_dir: Path) -> Path:
    return output_dir / input_path.stem


def output_file(base: Path, extension: str) -> Path:
    """Append an output extension without discarding dots in the recording name."""
    return Path(f"{base}{extension}")


def unique_output_base(input_path: Path, output_dir: Path) -> Path:
    candidate = output_base(input_path, output_dir)
    number = 2
    while output_file(candidate, ".txt").exists() or output_file(candidate, ".srt").exists():
        candidate = output_dir / f"{input_path.stem} ({number})"
        number += 1
    return candidate


def conversion_command(ffmpeg: Path, source: Path, wav: Path) -> list[str]:
    return [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav),
    ]


def transcription_command(whisper: Path, model: Path, wav: Path, destination: Path) -> list[str]:
    return [
        str(whisper), "-m", str(model), "-f", str(wav), "-l", "he", "-otxt", "-osrt",
        "-of", str(destination), "-pp",
    ]


def parse_progress(line: str) -> int | None:
    match = re.search(r"progress\s*=\s*(\d+)%", line, flags=re.IGNORECASE)
    return min(100, int(match.group(1))) if match else None


def run_process(command: list[str], progress: ProgressCallback | None = None) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=creationflags,
        )
    except OSError as exc:
        raise TranscriptionError(f"Could not start a required component: {exc}") from exc

    tail: list[str] = []
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            line = line.strip()
            if line:
                tail.append(line)
                tail = tail[-12:]
                parsed = parse_progress(line)
                if parsed is not None and progress:
                    progress(parsed, "Transcribing…")
    if process.wait() != 0:
        detail = "\n".join(tail) or "The component stopped unexpectedly."
        raise TranscriptionError(detail)


def transcribe(
    source: Path,
    output_dir: Path,
    model: Path,
    ffmpeg: Path,
    whisper: Path,
    temporary_wav: Path,
    progress: ProgressCallback,
) -> tuple[Path, Path]:
    validate_input(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    for tool in (ffmpeg, whisper):
        if not tool.is_file():
            raise TranscriptionError("The installation is incomplete. Please reinstall Taatik.")
    if not model.is_file():
        raise TranscriptionError("The Hebrew transcription model is not installed.")

    progress(5, "Preparing the audio…")
    run_process(conversion_command(ffmpeg, source, temporary_wav))
    base = unique_output_base(source, output_dir)
    progress(15, "Transcribing in Hebrew…")
    run_process(
        transcription_command(whisper, model, temporary_wav, base),
        lambda value, text: progress(15 + int(value * 0.84), text),
    )
    txt, srt = output_file(base, ".txt"), output_file(base, ".srt")
    if not txt.is_file() or not srt.is_file():
        raise TranscriptionError("Transcription finished, but the output files were not created.")
    progress(100, "Done")
    return txt, srt
