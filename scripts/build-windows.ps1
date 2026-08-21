$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Vendor = Join-Path $ProjectRoot "vendor"
$Bin = Join-Path $Vendor "bin"
$Downloads = Join-Path $Vendor "downloads"

New-Item -ItemType Directory -Force -Path $Bin, $Downloads | Out-Null

$WhisperVersion = "v1.9.1"
$WhisperZip = Join-Path $Downloads "whisper-bin-x64.zip"
$WhisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperVersion/whisper-bin-x64.zip"
$FfmpegZip = Join-Path $Downloads "ffmpeg-release-essentials.zip"
$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

if (-not (Test-Path $WhisperZip)) { Invoke-WebRequest $WhisperUrl -OutFile $WhisperZip }
if (-not (Test-Path $FfmpegZip)) { Invoke-WebRequest $FfmpegUrl -OutFile $FfmpegZip }

$WhisperExtract = Join-Path $Vendor "whisper"
$FfmpegExtract = Join-Path $Vendor "ffmpeg"
Remove-Item $WhisperExtract, $FfmpegExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $WhisperZip $WhisperExtract
Expand-Archive $FfmpegZip $FfmpegExtract

$WhisperExe = Get-ChildItem $WhisperExtract -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
$FfmpegExe = Get-ChildItem $FfmpegExtract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
if (-not $WhisperExe -or -not $FfmpegExe) { throw "Could not find required executables in downloaded archives." }

# whisper-cli uses DLLs shipped beside it. Preserve all runtime files from that directory.
Copy-Item (Join-Path $WhisperExe.DirectoryName "*") $Bin -Recurse -Force
Copy-Item $FfmpegExe.FullName (Join-Path $Bin "ffmpeg.exe") -Force

Set-Location $ProjectRoot
if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install ".[dev]"
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean taatik.spec

$Iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $DefaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $DefaultIscc) { $Iscc = Get-Item $DefaultIscc }
}
if (-not $Iscc) {
    throw "The app was built in dist\Taatik, but Inno Setup 6 is required to create the installer."
}
& $Iscc.Source (Join-Path $ProjectRoot "installer\Taatik.iss")
Write-Host "Installer created in release\"
