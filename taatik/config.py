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
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / ".taatik"


def model_path() -> Path:
    return data_dir() / "models" / MODEL_FILENAME


def bundled_tool(name: str) -> Path:
    """Locate an executable in a PyInstaller bundle or a source checkout."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [base / "bin" / f"{name}{suffix}", base / f"{name}{suffix}"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]

