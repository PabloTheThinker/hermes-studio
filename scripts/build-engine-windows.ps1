# Build the engine that ships inside the Windows app:
#   build\engine\python\   portable CPython with hermes-studio + deps installed
#   build\engine\bin\      ffmpeg.exe, ffprobe.exe (static, with libass)
#   build\engine\NOTICE, LICENSE, licenses\   third-party notices + license texts
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
# Exact PyAV / OpenCV versions: NOTICE names them and the FFmpeg libraries they bundle.
uv pip install --python $Py --no-cache -c "$Root\packaging\engine-constraints.txt" "$Root[reframe]"
if ($LASTEXITCODE -ne 0) { throw "engine install failed" }

# 3. yt-dlp beside the interpreter (download.py looks there first).
#    A .cmd wrapper, so it never pins this build path.
Set-Content -Encoding ascii -Path "$Out\python\yt-dlp.cmd" -Value "@`"%~dp0python.exe`" -m yt_dlp %*"

# 3b. The `hermes-studio` command: a relocatable .cmd beside the engine
#     (pip's Scripts\*.exe launchers pin this build path).
Remove-Item -Force -ErrorAction SilentlyContinue "$Out\python\Scripts\hermes-studio.exe", "$Out\python\Scripts\hermesclip.exe"
Set-Content -Encoding ascii -Path "$Out\hermes-studio.cmd" -Value @(
  "@echo off",
  "setlocal",
  "set `"PATH=%~dp0bin;%~dp0python;%PATH%`"",
  "set `"HERMES_STUDIO_EXE=%~f0`"",
  "set PYTHONNOUSERSITE=1",
  "set PYTHONUTF8=1",
  "set PYTHONHOME=",
  "set PYTHONPATH=",
  "`"%~dp0python\python.exe`" -m hermes_studio %*"
)

# 4. FFmpeg (a separate GPL program), plus the notices and license texts it needs.
Copy-Item "$FfDir\ffmpeg.exe", "$FfDir\ffprobe.exe" "$Out\bin\"
Copy-Item "$Root\NOTICE", "$Root\LICENSE" "$Out\"
Copy-Item -Recurse "$Root\licenses" "$Out\licenses"

# 5. Trim what the app never runs.
Get-ChildItem -Recurse -Directory -Filter "__pycache__" "$Out\python" | Remove-Item -Recurse -Force
foreach ($d in "Lib\test", "Lib\idlelib", "Lib\tkinter", "tcl") {
  if (Test-Path "$Out\python\$d") { Remove-Item -Recurse -Force "$Out\python\$d" }
}

# 6. Smoke test: imports, tools on PATH, and a real audio decode.
$env:PATH = "$Out\bin;$Out\python;$env:SystemRoot\System32"
$env:ENGINE_OUT = $Out
$env:REPO_ROOT = $Root
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
# NOTICE must name the exact FFmpeg build and PyAV/OpenCV wheels that ship.
import re, av
from importlib.metadata import version
notice = open(os.path.join(os.environ["ENGINE_OUT"], "NOTICE"), encoding="utf-8").read()
ver = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True).stdout.split()[2]
build = re.sub(r"-\d{8}$", "", ver)  # drop BtbN's date suffix
assert build in notice, f"NOTICE does not name the bundled ffmpeg build {build}"
assert f"PyAV {av.__version__}" in notice, f"NOTICE does not name PyAV {av.__version__}"
assert f"FFmpeg {av.ffmpeg_version_info}" in notice, f"NOTICE does not name PyAV's FFmpeg {av.ffmpeg_version_info}"
for lib, v in av.library_versions.items():
    assert f"{lib} {'.'.join(map(str, v))}" in notice, f"NOTICE does not list {lib} {v}"
assert f"opencv-python-headless {version('opencv-python-headless')}" in notice, "NOTICE does not name the bundled OpenCV wheel"
# Every library in the shipped ffmpeg and PyAV wheel must be the set NOTICE and
# packaging/third-party-sources.txt cover (tests/test_notices.py maps them).
pkg = os.path.join(os.environ["REPO_ROOT"], "packaging")
def listed(name):
    with open(os.path.join(pkg, name), encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}
conf = subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"], capture_output=True, text=True).stdout.split()
conf = {t for t in conf if t.startswith(("--enable-", "--disable-"))}
assert conf == listed('ffmpeg-buildconf-win64.txt'), f"ffmpeg -buildconf changed: {sorted(conf ^ listed('ffmpeg-buildconf-win64.txt'))}"
libs_dir = os.path.join(os.path.dirname(os.path.dirname(av.__file__)), "av.libs")
libs = {re.sub(r"-[0-9a-f]{32}(?=\.dll$)", "", re.sub(r"-[0-9a-f]{8}(?=\.so)", "", n)) for n in os.listdir(libs_dir)}
assert libs == listed('pyav-wheel-libs-win.txt'), f"PyAV av.libs changed: {sorted(libs ^ listed('pyav-wheel-libs-win.txt'))}"
# The native libraries the other wheels (OpenCV, numpy, ...) bundle, verbatim with their hashes.
sp = os.path.dirname(os.path.dirname(av.__file__))
others = {f"{d}/{n}" for d in os.listdir(sp) if d.endswith(".libs") and d != "av.libs" for n in os.listdir(os.path.join(sp, d))} | {f"{d}/{n}" for d in ("cv2", "ctranslate2") for n in os.listdir(os.path.join(sp, d)) if n.lower().endswith(".dll")}
assert others == listed('wheel-libs-win.txt'), f"bundled wheel libraries changed: {sorted(others ^ listed('wheel-libs-win.txt'))}"
print("libraries ok:", len(conf), "ffmpeg flags,", len(libs), "PyAV libraries,", len(others), "other wheel libraries")
print("notices ok: ffmpeg", build, "| PyAV", av.__version__, "FFmpeg", av.ffmpeg_version_info)
print("engine ok:", sys.version.split()[0])
'@
$smoke | & $Py -
if ($LASTEXITCODE -ne 0) { throw "engine smoke test failed" }
"engine size: {0:N0} MB" -f ((Get-ChildItem -Recurse -File $Out | Measure-Object Length -Sum).Sum / 1MB)
