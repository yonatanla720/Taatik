# Taatik

Taatik is a simple Windows desktop app that turns Hebrew audio or video into a plain-text transcript (`.txt`) and subtitles (`.srt`). Transcription runs locally with whisper.cpp; recordings are never uploaded.

## End-user workflow

1. Open Taatik and drop a recording onto the window (or click **Choose file**).
2. Choose where to save the result. By default, Taatik uses the recording's folder.
3. Click **Create transcript**.
4. On first use only, approve the roughly 1.6 GB Hebrew model download. Future transcription is offline.
5. Open the output folder when Taatik finishes.

Existing transcripts are never overwritten; Taatik adds `(2)`, `(3)`, and so on. Video is converted internally to mono, 16 kHz WAV audio before transcription. Hebrew is explicitly selected in whisper.cpp.

## Privacy and storage

- Audio/video and transcripts stay on the computer.
- The only network activity is the first-run model download directly from the official [ivrit.ai Hugging Face repository](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ggml).
- The model is stored in `%LOCALAPPDATA%\Taatik\models` and can be deleted to reclaim about 1.6 GB. Taatik will offer to download it again next time.

## Build the Windows installer

Build on a 64-bit Windows 10/11 machine. Install:

- Python 3.11 (including the `py` launcher)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php)
- PowerShell 5.1 or newer

From a PowerShell prompt in this directory, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-windows.ps1
```

The script downloads pinned whisper.cpp Windows binaries and a current FFmpeg essentials build, runs the tests, creates a standalone PyInstaller app, and then produces `release\Taatik-Setup-1.0.0.exe`. The resulting installer includes Python, Qt, FFmpeg, whisper.cpp, and their runtime libraries. It deliberately excludes the model, keeping the installer reasonably small.

To build without an installer, stop after the PyInstaller command in the script; the portable app is in `dist\Taatik`.

## Run from source (development)

The GUI can run on macOS/Linux for interface development, but a complete transcription run requires compatible `ffmpeg` and `whisper-cli` files in `vendor/bin`.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m taatik.app
python -m unittest discover -s tests -v
```

## Troubleshooting

- **Model download interrupted:** click **Create transcript** again. Partial downloads are discarded so a corrupt model is never used.
- **Installation incomplete:** reinstall using the generated setup file. The app checks for both bundled engines before starting.
- **Slow transcription:** the Large V3 Turbo model is demanding and CPU speed varies. Keep the laptop connected to power for long recordings.
- **Disk space:** allow roughly 2 GB for the model plus temporary space close to the uncompressed audio size.

## Third-party components

The app packages [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and [FFmpeg](https://ffmpeg.org/). The Hebrew model is `ivrit-ai/whisper-large-v3-turbo-ggml`, licensed under Apache-2.0. Review and distribute the corresponding third-party license files with production releases.
