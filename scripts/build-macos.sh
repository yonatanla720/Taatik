#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    cat <<'EOF'
Usage: scripts/build-macos.sh

Builds native FFmpeg and whisper.cpp, then creates:
  dist/Taatik.app
  release/Taatik-<version>-macos-<arm64|x86_64>.dmg

The build architecture is the architecture of the current Mac and Python.
Optional distribution configuration:
  TAATIK_SIGN_IDENTITY   Developer ID Application identity used to sign the app and DMG
  TAATIK_NOTARY_PROFILE  notarytool keychain profile; requires TAATIK_SIGN_IDENTITY
  MACOSX_DEPLOYMENT_TARGET  minimum deployment target (default: 13.3)
  TAATIK_REBUILD_NATIVE  set to 1 to rebuild cached native tools

Without TAATIK_SIGN_IDENTITY, PyInstaller creates an ad-hoc-signed local build.
EOF
    exit 0
fi

if [[ $# -ne 0 ]]; then
    echo "Unknown argument: $1" >&2
    echo "Run scripts/build-macos.sh --help for usage." >&2
    exit 2
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "The macOS package must be built on macOS." >&2
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BOOTSTRAP="${PYTHON:-python3}"
APP_VERSION="$("$PYTHON_BOOTSTRAP" -c 'import pathlib, sys, tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]["version"])' "$PROJECT_ROOT/pyproject.toml")"
WHISPER_VERSION="v1.9.1"
FFMPEG_VERSION="7.1.5"
MAC_ARCH="$(uname -m)"
DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-13.3}"
SIGN_IDENTITY="${TAATIK_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${TAATIK_NOTARY_PROFILE:-}"
REBUILD_NATIVE="${TAATIK_REBUILD_NATIVE:-0}"

if [[ "$MAC_ARCH" != "arm64" && "$MAC_ARCH" != "x86_64" ]]; then
    echo "Unsupported Mac architecture: $MAC_ARCH" >&2
    exit 1
fi
if [[ -n "$NOTARY_PROFILE" && -z "$SIGN_IDENTITY" ]]; then
    echo "TAATIK_NOTARY_PROFILE requires TAATIK_SIGN_IDENTITY." >&2
    exit 1
fi

for required in xcode-select clang make curl tar lipo otool hdiutil codesign; do
    if ! command -v "$required" >/dev/null 2>&1; then
        echo "Missing required macOS build tool: $required" >&2
        exit 1
    fi
done
xcode-select -p >/dev/null

VENV="$PROJECT_ROOT/.venv-macos"
VENDOR_ROOT="$PROJECT_ROOT/vendor/macos/$MAC_ARCH"
DOWNLOADS="$PROJECT_ROOT/vendor/downloads"
SOURCES="$PROJECT_ROOT/vendor/sources"
NATIVE_BUILD="$PROJECT_ROOT/build/macos-native-$MAC_ARCH"
PACKAGE_BUILD="$PROJECT_ROOT/build/macos-pyinstaller-$MAC_ARCH"
LICENSES="$VENDOR_ROOT/licenses"
BIN="$VENDOR_ROOT/bin"
ICON="$PROJECT_ROOT/build/macos-icon/Taatik.png"
APP="$PROJECT_ROOT/dist/Taatik.app"
DMG="$PROJECT_ROOT/release/Taatik-$APP_VERSION-macos-$MAC_ARCH.dmg"

mkdir -p "$DOWNLOADS" "$SOURCES" "$BIN" "$PROJECT_ROOT/release" "$(dirname "$ICON")"

if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON_BOOTSTRAP" -m venv "$VENV"
fi
PYTHON="$VENV/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e "$PROJECT_ROOT[dev]"

PYTHON_ARCH="$("$PYTHON" -c 'import platform; print(platform.machine())')"
if [[ "$PYTHON_ARCH" != "$MAC_ARCH" ]]; then
    echo "Python architecture $PYTHON_ARCH does not match this Mac ($MAC_ARCH)." >&2
    exit 1
fi

download() {
    local url="$1"
    local destination="$2"
    if [[ ! -f "$destination" ]]; then
        local partial="$destination.partial"
        rm -f "$partial"
        curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$url" --output "$partial"
        mv "$partial" "$destination"
    fi
}

WHISPER_ARCHIVE="$DOWNLOADS/whisper.cpp-$WHISPER_VERSION.tar.gz"
FFMPEG_ARCHIVE="$DOWNLOADS/ffmpeg-$FFMPEG_VERSION.tar.xz"
LGPL3_LICENSE="$DOWNLOADS/LGPL-3.0.txt"
GPL3_LICENSE="$DOWNLOADS/GPL-3.0.txt"
APACHE2_LICENSE="$DOWNLOADS/Apache-2.0.txt"
XZ_LICENSE="$DOWNLOADS/XZ-Utils-COPYING.txt"
download "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/$WHISPER_VERSION.tar.gz" "$WHISPER_ARCHIVE"
download "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_ARCHIVE"
download "https://www.gnu.org/licenses/lgpl-3.0.txt" "$LGPL3_LICENSE"
download "https://www.gnu.org/licenses/gpl-3.0.txt" "$GPL3_LICENSE"
download "https://www.apache.org/licenses/LICENSE-2.0.txt" "$APACHE2_LICENSE"
download "https://raw.githubusercontent.com/tukaani-project/xz/v5.8.3/COPYING" "$XZ_LICENSE"

WHISPER_SOURCE="$SOURCES/whisper.cpp-$WHISPER_VERSION"
FFMPEG_SOURCE="$SOURCES/ffmpeg-$FFMPEG_VERSION"
if [[ ! -f "$WHISPER_SOURCE/CMakeLists.txt" ]]; then
    rm -rf "$WHISPER_SOURCE"
    mkdir -p "$WHISPER_SOURCE"
    tar -xzf "$WHISPER_ARCHIVE" --strip-components=1 -C "$WHISPER_SOURCE"
fi
if [[ ! -f "$FFMPEG_SOURCE/configure" ]]; then
    rm -rf "$FFMPEG_SOURCE"
    mkdir -p "$FFMPEG_SOURCE"
    tar -xJf "$FFMPEG_ARCHIVE" --strip-components=1 -C "$FFMPEG_SOURCE"
fi

WHISPER_BUILD="$NATIVE_BUILD/whisper"
if [[ "$REBUILD_NATIVE" == "1" ]] || \
   [[ ! -x "$BIN/whisper-cli" ]] || \
   ! "$BIN/whisper-cli" --version 2>&1 | grep -F "version: ${WHISPER_VERSION#v}" >/dev/null; then
    rm -rf "$WHISPER_BUILD"
    "$VENV/bin/cmake" -S "$WHISPER_SOURCE" -B "$WHISPER_BUILD" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_OSX_ARCHITECTURES="$MAC_ARCH" \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="$DEPLOYMENT_TARGET" \
        -DBUILD_SHARED_LIBS=OFF \
        -DGGML_ACCELERATE=ON \
        -DGGML_METAL=ON \
        -DGGML_NATIVE=OFF \
        -DWHISPER_BUILD_EXAMPLES=ON \
        -DWHISPER_BUILD_TESTS=OFF \
        -DWHISPER_BUILD_SERVER=OFF
    "$VENV/bin/cmake" --build "$WHISPER_BUILD" --config Release --target whisper-cli --parallel
    cp "$WHISPER_BUILD/bin/whisper-cli" "$BIN/whisper-cli"
fi

FFMPEG_BUILD="$NATIVE_BUILD/ffmpeg"
FFMPEG_ASM_ARGS=()
if [[ "$MAC_ARCH" == "x86_64" ]]; then
    # Keep Intel builds dependent only on Xcode; nasm/yasm would otherwise be
    # an additional Homebrew-style build prerequisite.
    FFMPEG_ASM_ARGS+=(--disable-x86asm)
fi
if [[ "$REBUILD_NATIVE" == "1" ]] || \
   [[ ! -x "$BIN/ffmpeg" ]] || \
   ! "$BIN/ffmpeg" -version 2>&1 | grep -F "ffmpeg version $FFMPEG_VERSION" >/dev/null; then
    rm -rf "$FFMPEG_BUILD"
    mkdir -p "$FFMPEG_BUILD"
    pushd "$FFMPEG_BUILD" >/dev/null
    "$FFMPEG_SOURCE/configure" \
        --arch="$MAC_ARCH" \
        --target-os=darwin \
        --cc=clang \
        "${FFMPEG_ASM_ARGS[@]}" \
        --disable-autodetect \
        --disable-debug \
        --disable-doc \
        --disable-ffplay \
        --disable-ffprobe \
        --disable-network \
        --disable-shared \
        --enable-static \
        --enable-audiotoolbox \
        --enable-videotoolbox \
        --extra-cflags="-mmacosx-version-min=$DEPLOYMENT_TARGET" \
        --extra-ldflags="-mmacosx-version-min=$DEPLOYMENT_TARGET"
    make -j "$(sysctl -n hw.logicalcpu)" ffmpeg
    popd >/dev/null
    cp "$FFMPEG_BUILD/ffmpeg" "$BIN/ffmpeg"
fi
chmod 755 "$BIN/ffmpeg" "$BIN/whisper-cli"

for binary in "$BIN/ffmpeg" "$BIN/whisper-cli"; do
    if ! lipo -archs "$binary" | tr ' ' '\n' | grep -Fx "$MAC_ARCH" >/dev/null; then
        echo "Wrong architecture in $binary" >&2
        exit 1
    fi
    if otool -L "$binary" | tail -n +2 | grep -E '/opt/homebrew|/usr/local|/vendor/' >/dev/null; then
        echo "Non-system runtime dependency found in $binary:" >&2
        otool -L "$binary" >&2
        exit 1
    fi
done

rm -rf "$LICENSES"
"$PYTHON" "$PROJECT_ROOT/scripts/collect-macos-licenses.py" \
    "$LICENSES" "$WHISPER_SOURCE" "$FFMPEG_SOURCE"
cp "$LGPL3_LICENSE" "$LICENSES/Qt-PySide6-LGPL-3.0.txt"
cp "$GPL3_LICENSE" "$LICENSES/Qt-PySide6-GPL-3.0.txt"
cp "$APACHE2_LICENSE" "$LICENSES/Model-Apache-2.0.txt"
cp "$APACHE2_LICENSE" "$LICENSES/OpenSSL-Apache-2.0.txt"
cp "$FFMPEG_SOURCE/COPYING.LGPLv2.1" "$LICENSES/GNU-gettext-LGPL-2.1.txt"
cp "$XZ_LICENSE" "$LICENSES/XZ-Utils-COPYING.txt"

# Speaker diarization models (ONNX): pyannote segmentation + 3D-Speaker embedding.
DIAR="$VENDOR_ROOT/diarization"
mkdir -p "$DIAR"
SEG_ARCHIVE="$DOWNLOADS/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
download "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" "$SEG_ARCHIVE"
download "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx" "$DIAR/embedding.onnx"
rm -rf "$DOWNLOADS/sherpa-onnx-pyannote-segmentation-3-0"
tar -xjf "$SEG_ARCHIVE" -C "$DOWNLOADS"
cp "$DOWNLOADS/sherpa-onnx-pyannote-segmentation-3-0/model.onnx" "$DIAR/segmentation.onnx"

"$PYTHON" "$PROJECT_ROOT/scripts/create-macos-icon.py" "$ICON"

rm -rf "$PACKAGE_BUILD" "$APP"
PYINSTALLER_ARGS=(
    --noconfirm
    --clean
    --workpath "$PACKAGE_BUILD"
    --distpath "$PROJECT_ROOT/dist"
)
if [[ -n "$SIGN_IDENTITY" ]]; then
    PYINSTALLER_ARGS+=(--codesign-identity "$SIGN_IDENTITY")
fi
TAATIK_VENDOR_BIN="$BIN" \
TAATIK_VENDOR_DIAR="$DIAR" \
TAATIK_LICENSE_DIR="$LICENSES" \
TAATIK_MAC_ICON="$ICON" \
"$VENV/bin/pyinstaller" "${PYINSTALLER_ARGS[@]}" "$PROJECT_ROOT/taatik.spec"

APP_EXECUTABLE="$APP/Contents/MacOS/Taatik"
if [[ -n "$SIGN_IDENTITY" ]]; then
    codesign --force --deep --options runtime --timestamp --sign "$SIGN_IDENTITY" "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"

"$PYTHON" -m unittest discover -s "$PROJECT_ROOT/tests" -v
TAATIK_MAC_APP="$APP" "$PYTHON" -m unittest tests.test_macos_packaging.PackagedMacTests -v
"$APP_EXECUTABLE" --self-test

BUNDLED_FFMPEG="$(find "$APP/Contents" -path '*/bin/ffmpeg' -type f -print -quit)"
SMOKE_WAV="$PACKAGE_BUILD/packaged-ffmpeg-smoke.wav"
"$BUNDLED_FFMPEG" -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=0.1" \
    -ac 1 -ar 16000 -c:a pcm_s16le "$SMOKE_WAV"
if [[ ! -s "$SMOKE_WAV" ]]; then
    echo "Bundled FFmpeg did not generate the smoke-test WAV." >&2
    exit 1
fi

DMG_STAGE="$PACKAGE_BUILD/dmg-root"
rm -rf "$DMG_STAGE" "$DMG"
mkdir -p "$DMG_STAGE"
ditto "$APP" "$DMG_STAGE/Taatik.app"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -volname "Taatik" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG"
hdiutil verify "$DMG"

if [[ -n "$SIGN_IDENTITY" ]]; then
    codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"
    codesign --verify --verbose=2 "$DMG"
fi
if [[ -n "$NOTARY_PROFILE" ]]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
fi

echo
echo "macOS app: $APP"
echo "Disk image: $DMG"
if [[ -z "$SIGN_IDENTITY" ]]; then
    echo "This is an ad-hoc-signed local build; see README.md for Gatekeeper limitations."
fi
