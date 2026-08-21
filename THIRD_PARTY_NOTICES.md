# Taatik third-party notices

Taatik packages the following third-party software. The macOS build places the
corresponding complete license texts in the app's `Contents/Resources/licenses`
directory. Those files must remain with redistributed copies of the app.

## Packaged components

- **FFmpeg** — https://ffmpeg.org/ — built without GPL or non-free options and
  distributed under the GNU Lesser General Public License, version 2.1 or later.
- **whisper.cpp / ggml** — https://github.com/ggml-org/whisper.cpp — MIT License.
- **sherpa-onnx** — https://github.com/k2-fsa/sherpa-onnx — Apache License
  2.0. Provides the offline speaker-diarization engine used for the optional
  "Separate speakers" feature.
- **ONNX Runtime** — https://github.com/microsoft/onnxruntime — MIT License.
  Bundled with sherpa-onnx to run the diarization models on the CPU.
- **pyannote speaker-segmentation 3.0 model** —
  https://huggingface.co/pyannote/segmentation-3.0 — MIT License. Used, in its
  ONNX form, to segment audio into speaker turns.
- **3D-Speaker embedding model** — https://github.com/modelscope/3D-Speaker —
  Apache License 2.0. Used, in its ONNX form, to cluster speaker turns.
- **NumPy** — https://numpy.org/ — BSD 3-Clause License.
- **libsndfile** (via the SoundFile package) — https://libsndfile.github.io/libsndfile/
  — GNU Lesser General Public License, version 2.1 or later. Reads the prepared
  audio for diarization. SoundFile itself is under the BSD 3-Clause License.
- **NVIDIA CUDA runtime libraries** (Windows only) — cuBLAS, cuBLASLt, CUDA
  runtime, and NVRTC redistributable DLLs from the CUDA Toolkit, redistributed
  under the NVIDIA CUDA Toolkit End User License Agreement
  (https://docs.nvidia.com/cuda/eula/). These accompany the prebuilt cuBLAS
  whisper.cpp binaries and are used only to accelerate transcription on machines
  with an NVIDIA GPU; the app runs the CPU engine everywhere else.
- **PySide6, Shiboken6, and Qt** — https://www.qt.io/qt-for-python — distributed
  under the license choices included with the installed PySide6 packages,
  including the GNU Lesser General Public License, version 3. The generated app
  includes the upstream license files from the exact installed wheels.
- **Python** — https://www.python.org/ — Python Software Foundation License.
- **PyInstaller bootloader** — https://pyinstaller.org/ — GPL license with the
  upstream exception permitting distribution of bundled applications. The
  generated app includes the exact installed package's license files.
- **Certifi** — https://github.com/certifi/python-certifi — Mozilla Public
  License 2.0. Its CA certificate bundle is used to verify the first-use HTTPS
  model download on machines without a developer toolchain.
- **OpenSSL** — https://www.openssl.org/ — Apache License 2.0. PyInstaller may
  collect it from the build Python to support HTTPS model downloads.
- **GNU gettext runtime (`libintl`)** — https://www.gnu.org/software/gettext/ —
  GNU Lesser General Public License, version 2.1 or later. PyInstaller may
  collect it from the build Python.
- **XZ Utils (`liblzma`)** — https://tukaani.org/xz/ — the upstream public-domain
  and permissive notices in `XZ-Utils-COPYING.txt`. PyInstaller may collect it
  from the build Python.

## Downloaded on first use (not packaged)

- **ivrit-ai/whisper-large-v3-turbo-ggml** —
  https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ggml — Apache License
  2.0. The model is downloaded directly from the publisher after user approval
  and is not included in Taatik's app bundle or disk image.

Taatik itself does not modify FFmpeg, whisper.cpp, Qt, or Python. Source code for
the exact FFmpeg and whisper.cpp versions used by a macOS build is identified in
`scripts/build-macos.sh`; their unmodified source archives are downloaded from
the upstream projects during the build.
