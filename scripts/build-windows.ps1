$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Vendor = Join-Path $ProjectRoot "vendor"
$Bin = Join-Path $Vendor "bin"
$Downloads = Join-Path $Vendor "downloads"

New-Item -ItemType Directory -Force -Path $Bin, $Downloads | Out-Null

function Get-RemoteFile {
    param([Parameter(Mandatory)][string]$Url, [Parameter(Mandatory)][string]$OutFile)
    $name = Split-Path $OutFile -Leaf
    $req = [System.Net.HttpWebRequest]::Create($Url)
    $req.UserAgent = "Taatik-Build"
    $resp = $req.GetResponse()
    $total = $resp.ContentLength
    $in = $resp.GetResponseStream()
    $out = [System.IO.File]::Create($OutFile)
    try {
        $buffer = New-Object byte[] (1MB)
        $done = 0L
        $lastReport = 0L
        while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $out.Write($buffer, 0, $read)
            $done += $read
            if (($done - $lastReport) -ge 1MB -or $done -eq $total) {
                $lastReport = $done
                if ($total -gt 0) {
                    $pct = [int]($done / $total * 100)
                    Write-Progress -Activity "Downloading $name" `
                        -Status ("{0:N1} / {1:N1} MB" -f ($done / 1MB), ($total / 1MB)) `
                        -PercentComplete $pct
                } else {
                    Write-Progress -Activity "Downloading $name" -Status ("{0:N1} MB" -f ($done / 1MB))
                }
            }
        }
        Write-Progress -Activity "Downloading $name" -Completed
    } finally {
        $out.Dispose(); $in.Dispose(); $resp.Dispose()
    }
}

$WhisperVersion = "v1.9.1"
$WhisperZip = Join-Path $Downloads "whisper-bin-x64.zip"
$WhisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperVersion/whisper-bin-x64.zip"
$FfmpegZip = Join-Path $Downloads "ffmpeg-release-essentials.zip"
$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

if (-not (Test-Path $WhisperZip)) { Get-RemoteFile $WhisperUrl $WhisperZip }
if (-not (Test-Path $FfmpegZip)) { Get-RemoteFile $FfmpegUrl $FfmpegZip }

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
$WinIcon = Join-Path $ProjectRoot "build\windows-icon\Taatik.ico"
& .\.venv\Scripts\python.exe scripts\create-windows-icon.py $WinIcon
$env:TAATIK_WIN_ICON = $WinIcon
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean taatik.spec
& .\dist\Taatik\Taatik.exe --self-test
if ($LASTEXITCODE -ne 0) { throw "The packaged app failed its bundled-component self-check." }

$IsccPath = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
if (-not $IsccPath) {
    $DefaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $DefaultIscc) { $IsccPath = $DefaultIscc }
}
if (-not $IsccPath) {
    throw "The app was built in dist\Taatik, but Inno Setup 6 is required to create the installer."
}
& $IsccPath (Join-Path $ProjectRoot "installer\Taatik.iss")
Write-Host "Installer created in release\"
