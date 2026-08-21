from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .config import MIN_MODEL_BYTES, MODEL_URL
from .core import transcribe


class ModelDownloadWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(Path)
    failed = Signal(str)

    def __init__(self, destination: Path):
        super().__init__()
        self.destination = destination

    @Slot()
    def run(self) -> None:
        partial = self.destination.with_suffix(".download")
        try:
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Taatik/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as target:
                total = int(response.headers.get("Content-Length", "0"))
                received = 0
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
                    received += len(chunk)
                    percent = int(received * 100 / total) if total else 0
                    self.progress.emit(percent, f"Downloading Hebrew model… {received / 1e9:.1f} GB")
            if partial.stat().st_size < MIN_MODEL_BYTES:
                raise RuntimeError("The model download was incomplete. Check the internet connection and try again.")
            partial.replace(self.destination)
            self.completed.emit(self.destination)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            self.failed.emit(str(exc))


class TranscriptionWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(Path, Path)
    failed = Signal(str)

    def __init__(self, source: Path, output_dir: Path, model: Path, ffmpeg: Path, whisper: Path):
        super().__init__()
        self.source, self.output_dir, self.model = source, output_dir, model
        self.ffmpeg, self.whisper = ffmpeg, whisper

    @Slot()
    def run(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="taatik-") as temp_dir:
                txt, srt = transcribe(
                    self.source, self.output_dir, self.model, self.ffmpeg, self.whisper,
                    Path(temp_dir) / "audio.wav",
                    lambda value, text: self.progress.emit(value, text),
                )
            self.completed.emit(txt, srt)
        except Exception as exc:
            self.failed.emit(str(exc))
