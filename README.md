# Taatik

Taatik is a simple Windows and macOS desktop app that turns Hebrew audio or
video into a plain-text transcript (`.txt`) and subtitles (`.srt`).
Transcription runs locally with whisper.cpp; recordings and transcripts are
never uploaded.

## End-user workflow

1. Open Taatik and drop a recording onto the window (or click **Choose file**).
2. Choose where to save the result. By default, Taatik uses the recording's folder.
3. Click **Create transcript**.
4. On first use only, approve the roughly 1.6 GB Hebrew model download. Future
   transcription is offline.
5. Open the output folder when Taatik finishes.

Existing transcripts are never overwritten; Taatik adds `(2)`, `(3)`, and so
on. Video is converted internally to mono, 16 kHz WAV audio before
transcription. Hebrew is explicitly selected in whisper.cpp.

## Privacy and storage

- Audio/video and transcripts stay on the computer.
- The only network activity in the installed app is the first-run model
  download directly from the official
  [ivrit.ai Hugging Face repository](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ggml).
- The model is not part of the app or installer. It can be deleted to reclaim
  about 1.6 GB; Taatik will offer to download it again.

Model locations:

- macOS: `~/Library/Application Support/Taatik/models`
- Windows: `%LOCALAPPDATA%\Taatik\models`

## Build macOS app and DMG

Build on the Mac architecture you intend to distribute. The current dependency
set targets macOS 13.3 or newer. Install Python 3.11 or newer and Xcode Command
Line Tools (or Xcode). Homebrew is not required by the build and is not required
by end users.

```bash
xcode-select --install  # only if the command-line tools are not installed
./scripts/build-macos.sh
```

The script creates an isolated `.venv-macos`, downloads pinned FFmpeg and
whisper.cpp source archives, and compiles native static executables. Verified
native binaries are cached; set `TAATIK_REBUILD_NATIVE=1` for a clean rebuild. It rejects
Homebrew or `/usr/local` runtime dependencies, runs the full test suite, builds
and checks `dist/Taatik.app`, generates audio with the FFmpeg inside that app,
and creates:

```text
release/Taatik-1.0.0-macos-arm64.dmg
release/Taatik-1.0.0-macos-x86_64.dmg
```

Only the file matching the build Mac is produced. Build on Apple Silicon for
`arm64` and on an Intel Mac for `x86_64`; the script and source versions are the
same on both. PyInstaller can create a universal2 app only when Python, Qt, and
every native input are universal2, so this project deliberately produces clear
per-architecture DMGs instead of claiming that two thin binaries are universal.

The disk image contains `Taatik.app` and an Applications shortcut. The app
contains Python, Qt, FFmpeg, whisper.cpp, the generated placeholder app icon,
and the applicable third-party license texts. It deliberately excludes the
large Hebrew model.

### Unsigned local builds and Gatekeeper

With no configuration, PyInstaller ad-hoc signs the app. This is suitable for
local testing, but an app copied from an unsigned/unnotarized DMG may be blocked
or show an unidentified-developer warning on another Mac. A tester can use
Finder's **Open** context-menu action and confirm the warning, or allow the app
in **System Settings → Privacy & Security**. Ad-hoc builds are not appropriate
for general public distribution.

For a release, provide a real Developer ID Application identity already present
in the build Mac's keychain:

```bash
TAATIK_SIGN_IDENTITY="Developer ID Application: YOUR CERTIFICATE NAME" \
  ./scripts/build-macos.sh
```

To notarize as part of the same build, first create a `notarytool` keychain
profile using credentials from your own Apple Developer account, then set its
profile name:

```bash
xcrun notarytool store-credentials "YOUR_PROFILE_NAME"
TAATIK_SIGN_IDENTITY="Developer ID Application: YOUR CERTIFICATE NAME" \
TAATIK_NOTARY_PROFILE="YOUR_PROFILE_NAME" \
  ./scripts/build-macos.sh
```

The script submits the signed DMG with `notarytool`, waits for Apple's result,
and staples and validates the ticket. It contains no certificate names, Apple
IDs, team IDs, passwords, or other invented credentials.

## Build the Windows installer

Build on a 64-bit Windows 10/11 machine. Install Python 3.11 (including the `py`
launcher), [Inno Setup 6](https://jrsoftware.org/isinfo.php), and PowerShell 5.1
or newer. Then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-windows.ps1
```

The script downloads whisper.cpp Windows binaries and an FFmpeg essentials
build, runs the tests, creates a standalone PyInstaller app, and produces
`release\Taatik-Setup-1.0.0.exe`. The model remains a first-use download.

The Windows build bundles two transcription engines: the CPU engine and an
NVIDIA GPU engine (whisper.cpp cuBLAS, CUDA 12.4). At runtime Taatik uses the
GPU engine when an NVIDIA driver is present and otherwise falls back to the CPU
engine, so the app runs on any 64-bit Windows machine. The bundled CUDA runtime
libraries make the installer substantially larger (roughly half a gigabyte).

## Run from source

For GUI development:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m taatik.app
python -m unittest discover -s tests -v
```

On Windows, use `.venv\Scripts\Activate.ps1` instead. A complete source-mode
transcription requires compatible `ffmpeg` and `whisper-cli` files available to
the checkout; the packaged builds always use their bundled copies.

## Troubleshooting

- **Model download interrupted:** click **Create transcript** again. Partial
  downloads are discarded so a corrupt model is never used.
- **Installation incomplete:** reinstall from the DMG or Windows setup file.
  The app checks both bundled engines before starting.
- **Slow transcription:** the Large V3 Turbo model is demanding. On Windows
  machines with an NVIDIA GPU, Taatik uses the GPU engine automatically and is
  much faster; without one it runs on the CPU, where speed varies. macOS uses
  the GPU on Apple Silicon. Keep laptops connected to power for long recordings.
- **Disk space:** allow roughly 2 GB for the model plus temporary space close to
  the uncompressed audio size.
- **macOS app will not open:** an ad-hoc local build has the Gatekeeper
  limitations above. Publicly distributed builds should use Developer ID and
  notarization.

## Third-party components

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The packaging process
copies the applicable license texts and installed-package metadata for FFmpeg,
whisper.cpp, PySide6/Qt, Python, PyInstaller, and the downloaded model into the
application bundle.
