# Build the engine that ships inside the Windows app:
#   build\engine\python\   portable CPython with hermes-studio + deps installed
#   build\engine\bin\      ffmpeg.exe, ffprobe.exe (static, with libass)
# The desktop app starts build\engine\python\python.exe with build\engine\bin first on PATH.
# Mirrors scripts/build-engine-linux.sh. Needs: uv on PATH, and FFMPEG_DIR set to a
# folder holding ffmpeg.exe + ffprobe.exe (with libass).
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path "$PSScriptRoot\..").Path
$Out = Join-Path $Root "build\engine"
$PyVer = if ($env:PYVER) { $env:PYVER } else { "3.12" }
$FfDir = $env:FFMPEG_DIR

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "missing: uv" }
if (-not $FfDir -or -not (Test-Path "$FfDir\ffmpeg.exe") -or -not (Test-Path "$FfDir\ffprobe.exe")) {
  throw "Set FFMPEG_DIR to a folder with static ffmpeg.exe + ffprobe.exe (libass)."
}
$filters = & "$FfDir\ffmpeg.exe" -hide_banner -filters 2>$null | Out-String
if ($filters -notmatch "(?m)^\s*[.A-Z|]+\s+ass\s+") { throw "That ffmpeg has no libass 'ass' filter; captions would fail." }

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path "$Out\bin" | Out-Null

# 1. Portable Python (python-build-standalone via uv).
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("hs-py-" + [guid]::NewGuid())
$env:UV_PYTHON_INSTALL_DIR = $tmp
uv python install $PyVer | Out-Null
Remove-Item Env:\UV_PYTHON_INSTALL_DIR
$src = Get-ChildItem $tmp -Directory | Where-Object { $_.Name -like "cpython-$PyVer*" } | Select-Object -First 1
if (-not $src) { throw "uv did not install python $PyVer" }
Copy-Item -Recurse $src.FullName "$Out\python"
Remove-Item -Recurse -Force $tmp
$Py = "$Out\python\python.exe"
Remove-Item -Force -ErrorAction SilentlyContinue "$Out\python\Lib\EXTERNALLY-MANAGED"

# 2. The engine and its libraries.
uv pip install --python $Py --no-cache "$Root[reframe]"
if ($LASTEXITCODE -ne 0) { throw "engine install failed" }

# 3. yt-dlp beside the interpreter (download.py looks there first).
#    A .cmd wrapper, so it never pins this build path.
Set-Content -Encoding ascii -Path "$Out\python\yt-dlp.cmd" -Value "@`"%~dp0python.exe`" -m yt_dlp %*"

# 4. FFmpeg.
Copy-Item "$FfDir\ffmpeg.exe", "$FfDir\ffprobe.exe" "$Out\bin\"

# 5. Trim what the app never runs.
Get-ChildItem -Recurse -Directory -Filter "__pycache__" "$Out\python" | Remove-Item -Recurse -Force
foreach ($d in "Lib\test", "Lib\idlelib", "Lib\tkinter", "tcl") {
  if (Test-Path "$Out\python\$d") { Remove-Item -Recurse -Force "$Out\python\$d" }
}

# 6. Smoke test: imports, tools on PATH, and a real audio decode.
$env:PATH = "$Out\bin;$Out\python;$env:SystemRoot\System32"
$smoke = @'
import os, shutil, subprocess, sys, tempfile
import hermes_studio.studio, hermes_studio.pipeline, faster_whisper, yt_dlp  # noqa: F401
from faster_whisper.audio import decode_audio
from hermes_studio.download import _ytdlp
for tool in ("ffmpeg", "ffprobe"):
    assert shutil.which(tool), f"{tool} not found on PATH"
print("yt-dlp:", _ytdlp())
wav = os.path.join(tempfile.mkdtemp(), "tone.wav")
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", wav], check=True)
assert len(decode_audio(wav)) > 8000, "audio decode returned nothing"
print("engine ok:", sys.version.split()[0])
'@
$smoke | & $Py -
if ($LASTEXITCODE -ne 0) { throw "engine smoke test failed" }
"engine size: {0:N0} MB" -f ((Get-ChildItem -Recurse -File $Out | Measure-Object Length -Sum).Sum / 1MB)
