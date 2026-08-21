from __future__ import annotations

import ssl
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

import certifi
from PySide6.QtCore import QObject, Signal, Slot

from .config import MIN_MODEL_BYTES, MODEL_URL
from .core import TranscriptionCancelled, transcribe


class ModelDownloadWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(Path)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, destination: Path):
        super().__init__()
        self.destination = destination
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        partial = self.destination.with_suffix(".download")
        try:
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Taatik/1.0"})
            tls_context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(
                request, timeout=60, context=tls_context
            ) as response, partial.open("wb") as target:
                total = int(response.headers.get("Content-Length", "0"))
                received = 0
                while chunk := response.read(1024 * 1024):
                    if self._cancel.is_set():
                        partial.unlink(missing_ok=True)
                        self.cancelled.emit()
                        return
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
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))


class TranscriptionWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(Path, Path)
    failed = Signal(str)
    cancelled = Signal()
    log = Signal(str)

    def __init__(
        self, source: Path, output_dir: Path, model: Path, ffmpeg: Path, whisper_engines: list[Path],
        separate_speakers: bool = False, num_speakers: int = 0,
        diarization_models: tuple[Path, Path] | None = None,
    ):
        super().__init__()
        self.source, self.output_dir, self.model = source, output_dir, model
        self.ffmpeg = ffmpeg
        self.whisper_engines = list(whisper_engines)
        self.separate_speakers = separate_speakers
        self.num_speakers = num_speakers
        self.diarization_models = diarization_models
        self._cancel = threading.Event()
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Request cancellation and kill the active subprocess, if any."""
        self._cancel.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _on_start(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._process = process

    @Slot()
    def run(self) -> None:
        last_error: Exception | None = None
        for index, engine in enumerate(self.whisper_engines):
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            is_last = index == len(self.whisper_engines) - 1
            # Only distinguish GPU/CPU when more than one engine is bundled
            # (the Windows CUDA + CPU case). A single engine, such as the
            # Metal-accelerated macOS build, is left unlabelled to avoid
            # mislabelling GPU work as CPU.
            if engine.parent.name == "bin-cuda":
                engine_label = "GPU"
            elif len(self.whisper_engines) > 1:
                engine_label = "CPU"
            else:
                engine_label = ""
            try:
                with tempfile.TemporaryDirectory(prefix="taatik-") as temp_dir:
                    txt, srt = transcribe(
                        self.source, self.output_dir, self.model, self.ffmpeg, engine,
                        Path(temp_dir) / "audio.wav",
                        lambda value, text: self.progress.emit(value, text),
                        on_start=self._on_start,
                        is_cancelled=self._cancel.is_set,
                        engine_label=engine_label,
                        separate_speakers=self.separate_speakers,
                        num_speakers=self.num_speakers,
                        diarization_models=self.diarization_models,
                        log=self.log.emit,
                    )
                self.completed.emit(txt, srt)
                return
            except TranscriptionCancelled:
                self.cancelled.emit()
                return
            except Exception as exc:
                last_error = exc
                if self._cancel.is_set():
                    self.cancelled.emit()
                    return
                if not is_last:
                    # The GPU engine failed to run; retry on the CPU engine.
                    self.progress.emit(5, "GPU engine unavailable — switching to CPU…")
                    continue
                self.failed.emit(str(exc))
                return
        if last_error is not None:
            self.failed.emit(str(last_error))
