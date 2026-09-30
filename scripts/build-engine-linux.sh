#!/usr/bin/env bash
# Build the engine that ships inside the Linux app:
#   build/engine/python/   portable CPython with hermes-studio + deps installed
#   build/engine/bin/      ffmpeg, ffprobe (static, with libass)
# The desktop app starts  build/engine/python/bin/python3 -c "...hermes-studio studio..."
# with build/engine/bin first on PATH. Nothing here depends on the build machine.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/engine"
PYVER="${PYVER:-3.12}"
FFMPEG_DIR="${FFMPEG_DIR:-}"   # folder holding static ffmpeg + ffprobe (with libass)

need() { command -v "$1" >/dev/null || { echo "missing: $1" >&2; exit 1; }; }
need uv

if [[ -z "$FFMPEG_DIR" || ! -x "$FFMPEG_DIR/ffmpeg" || ! -x "$FFMPEG_DIR/ffprobe" ]]; then
  echo "Set FFMPEG_DIR to a folder with static ffmpeg + ffprobe (libass)." >&2
  exit 1
fi
FILTERS="$("$FFMPEG_DIR/ffmpeg" -hide_banner -filters 2>/dev/null || true)"
if ! grep -qE '^ *[.A-Z|]+ +ass +' <<<"$FILTERS"; then
  echo "That ffmpeg has no libass 'ass' filter; captions would fail." >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT/bin"

# 1. Portable Python (python-build-standalone via uv). Relocatable by design.
TMPPY="$(mktemp -d)"
UV_PYTHON_INSTALL_DIR="$TMPPY" uv python install "$PYVER" >/dev/null
SRC="$(find "$TMPPY" -maxdepth 1 -mindepth 1 -type d -name "cpython-$PYVER*" | head -1)"
[[ -n "$SRC" ]] || { echo "uv did not install python $PYVER" >&2; exit 1; }
cp -a "$SRC" "$OUT/python"
rm -rf "$TMPPY"
PY="$OUT/python/bin/python3"
rm -f "$OUT/python/lib/python$PYVER/EXTERNALLY-MANAGED"

# 2. The engine and its libraries, installed into that Python.
uv pip install --python "$PY" --no-cache "${ROOT}[reframe]" >/dev/null

# 3. yt-dlp next to the interpreter (download.py looks there first).
#    A tiny wrapper, not the pip script, whose shebang would pin this build path.
rm -f "$OUT/python/bin/yt-dlp"
cat > "$OUT/python/bin/yt-dlp" <<'SH'
#!/bin/sh
exec "$(dirname "$0")/python3" -m yt_dlp "$@"
SH
chmod +x "$OUT/python/bin/yt-dlp"

# 3b. The `hermes-studio` command. pip's console scripts pin this build path in
#     their first line, so they are removed and replaced by a relocatable shim.
rm -f "$OUT/python/bin/hermes-studio" "$OUT/python/bin/hermesclip"
cat > "$OUT/hermes-studio" <<'SH'
#!/bin/sh
# The hermes-studio command, run by the engine inside the Hermes Studio app.
self="$(readlink -f "$0" 2>/dev/null || echo "$0")"
here="$(dirname "$self")"
PATH="$here/bin:$here/python/bin:$PATH"
HERMES_STUDIO_EXE="$self"
PYTHONNOUSERSITE=1
PYTHONUTF8=1
export PATH HERMES_STUDIO_EXE PYTHONNOUSERSITE PYTHONUTF8
unset PYTHONHOME PYTHONPATH
exec "$here/python/bin/python3" -m hermes_studio "$@"
SH
chmod +x "$OUT/hermes-studio"

# 4. FFmpeg.
cp "$FFMPEG_DIR/ffmpeg" "$FFMPEG_DIR/ffprobe" "$OUT/bin/"

# 5. Trim what the app never runs.
find "$OUT/python" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$OUT/python/lib/python$PYVER/test" "$OUT/python/lib/python$PYVER/idlelib" \
       "$OUT/python/lib/python$PYVER/tkinter" "$OUT/python/share"

# 6. Smoke test: the packed engine imports, sees its tools, and can decode
#    audio the way faster-whisper does (catches PyAV/faster-whisper API drift).
PATH="$OUT/bin:$OUT/python/bin:/usr/bin:/bin" "$PY" - <<'PY'
import os, shutil, subprocess, sys, tempfile
import hermes_studio.studio, hermes_studio.pipeline, faster_whisper, yt_dlp  # noqa: F401
from faster_whisper.audio import decode_audio
for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
    assert shutil.which(tool), f"{tool} not found on PATH"
wav = os.path.join(tempfile.mkdtemp(), "tone.wav")
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", wav], check=True)
assert len(decode_audio(wav)) > 8000, "audio decode returned nothing"
print("engine ok:", sys.version.split()[0])
PY
du -sh "$OUT" | awk '{print "engine size:", $1}'
