from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Taatik"
MODEL_FILENAME = "ivrit-ai-whisper-large-v3-turbo.bin"
MODEL_URL = (
    "https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ggml/"
    "resolve/main/ggml-model.bin?download=true"
)
# Reject HTML/error pages and clearly incomplete downloads. The published file is 1.62 GB.
MIN_MODEL_BYTES = 1_500_000_000

SUPPORTED_EXTENSIONS = {
    ".aac", ".aiff", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".ogg", ".opus", ".wav", ".webm", ".wma", ".wmv",
}


def data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / ".taatik"


def model_path() -> Path:
    return data_dir() / "models" / MODEL_FILENAME


def model_is_ready(path: Path | None = None) -> bool:
    candidate = path or model_path()
    try:
        return candidate.is_file() and candidate.stat().st_size >= MIN_MODEL_BYTES
    except OSError:
        return False


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def bundled_tool(name: str) -> Path:
    """Locate an executable in a PyInstaller bundle or a source checkout."""
    base = _bundle_root()
    suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [base / "bin" / f"{name}{suffix}", base / f"{name}{suffix}"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _nvidia_driver_present() -> bool:
    """True when the NVIDIA CUDA driver is installed, so the GPU engine can run."""
    if sys.platform != "win32":
        return False
    import ctypes

    try:
        ctypes.WinDLL("nvcuda.dll")
        return True
    except OSError:
        return False


def whisper_engines() -> list[Path]:
    """whisper-cli engines to try, GPU first when an NVIDIA driver is present.

    The CUDA build lives in ``bin-cuda`` beside the CPU build in ``bin``. On
    machines without an NVIDIA driver, only the CPU engine is offered.
    """
    base = _bundle_root()
    suffix = ".exe" if sys.platform == "win32" else ""
    cuda = base / "bin-cuda" / f"whisper-cli{suffix}"
    cpu = base / "bin" / f"whisper-cli{suffix}"
    engines: list[Path] = []
    if _nvidia_driver_present() and cuda.is_file():
        engines.append(cuda)
    if cpu.is_file():
        engines.append(cpu)
    return engines or [cpu]
