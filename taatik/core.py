from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .config import SUPPORTED_EXTENSIONS

ProgressCallback = Callable[[int, str], None]


class TranscriptionError(RuntimeError):
    pass


class TranscriptionCancelled(Exception):
    """Raised when the user stops transcription before it finishes."""


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


def parse_duration(text: str) -> float | None:
    """Extract a media duration in seconds from ffmpeg's ``Duration:`` output."""
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def media_duration(ffmpeg: Path, source: Path) -> float | None:
    """Best-effort media duration in seconds; returns None if it cannot be read."""
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-i", str(source)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # ffmpeg writes the stream summary (including Duration) to stderr and exits
    # non-zero because no output was requested; that is expected here.
    return parse_duration(result.stderr)


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def run_process(
    command: list[str],
    progress: ProgressCallback | None = None,
    on_start: Callable[[subprocess.Popen], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=creationflags,
        )
    except OSError as exc:
        raise TranscriptionError(f"Could not start a required component: {exc}") from exc

    if on_start:
        on_start(process)

    tail: list[str] = []
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            line = line.strip()
            if line:
                tail.append(line)
                tail = tail[-12:]
                parsed = parse_progress(line)
                if parsed is not None:
                    # Progress lines drive the bar/status; keep them out of the
                    # log so it is not flooded with hundreds of percent lines.
                    if progress:
                        progress(parsed, "Transcribing…")
                elif log:
                    log(line)
    returncode = process.wait()
    if is_cancelled and is_cancelled():
        raise TranscriptionCancelled()
    if returncode != 0:
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
    on_start: Callable[[subprocess.Popen], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    engine_label: str = "",
    separate_speakers: bool = False,
    num_speakers: int = 0,
    diarization_models: tuple[Path, Path] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[Path, Path]:
    def note(message: str) -> None:
        if log:
            log(message)

    validate_input(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    for tool in (ffmpeg, whisper):
        if not tool.is_file():
            raise TranscriptionError("The installation is incomplete. Please reinstall Taatik.")
    if not model.is_file():
        raise TranscriptionError("The Hebrew transcription model is not installed.")

    progress(5, "Preparing the audio…")
    note(f"Converting {source.name} to 16 kHz mono audio…")
    run_process(
        conversion_command(ffmpeg, source, temporary_wav),
        on_start=on_start, is_cancelled=is_cancelled, log=log,
    )
    if is_cancelled and is_cancelled():
        raise TranscriptionCancelled()
    base = unique_output_base(source, output_dir)
    # whisper.cpp on Windows writes output through narrow fopen and cannot
    # create files at non-ASCII paths (e.g. Hebrew recording names), silently
    # producing nothing while still exiting zero. Write to an ASCII path inside
    # the temp directory, then move the results to the real destination with
    # Python, which handles Unicode names correctly.
    work_base = temporary_wav.parent / "transcript"
    where = f" on {engine_label}" if engine_label else ""
    progress(15, f"Transcribing in Hebrew{where}…")
    note(f"Transcribing in Hebrew{where}…")
    run_process(
        transcription_command(whisper, model, temporary_wav, work_base),
        lambda value, text: progress(15 + int(value * 0.84), f"Transcribing in Hebrew{where}… {value}%"),
        on_start=on_start, is_cancelled=is_cancelled, log=log,
    )
    work_txt, work_srt = output_file(work_base, ".txt"), output_file(work_base, ".srt")
    if not work_txt.is_file() or not work_srt.is_file():
        raise TranscriptionError("Transcription finished, but the output files were not created.")
    txt, srt = output_file(base, ".txt"), output_file(base, ".srt")
    if separate_speakers and diarization_models is not None:
        # Diarize in a separate process so the heavy, uninterruptible ONNX work
        # cannot freeze the app; the child writes the speaker segments as JSON,
        # then we merge them with the transcript here (fast, pure Python).
        from .config import diarization_command
        from .diarization import label_transcript

        progress(84, "Separating speakers…")
        note("Separating speakers…")
        segments_json = temporary_wav.parent / "diarization.json"
        run_process(
            diarization_command(temporary_wav, segments_json),
            lambda value, text: progress(84 + int(value * 0.15), f"Separating speakers… {value}%"),
            on_start=on_start, is_cancelled=is_cancelled, log=log,
        )
        segments = json.loads(segments_json.read_text(encoding="utf-8"))
        labelled_txt, labelled_srt = label_transcript(
            work_srt.read_text(encoding="utf-8"), segments, num_speakers
        )
        txt.write_text(labelled_txt, encoding="utf-8")
        srt.write_text(labelled_srt, encoding="utf-8")
    else:
        shutil.move(str(work_txt), str(txt))
        shutil.move(str(work_srt), str(srt))
    note(f"Saved {txt.name} and {srt.name}")
    progress(100, "Done")
    return txt, srt
