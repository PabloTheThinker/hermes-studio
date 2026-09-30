#!/usr/bin/env bash
# Clean-machine test for the Linux AppImage.
# Runs inside a fresh ubuntu:24.04 container: installs ONLY what a desktop
# user already has (a display server + the libraries Electron needs), NOT
# python, ffmpeg or hermesclip. Then opens the app, waits for its own engine,
# screenshots the window, runs one real clip job through the engine's API,
# and screenshots the finished run.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  xvfb xauth x11-apps imagemagick curl ca-certificates \
  libgtk-3-0t64 libnss3 libasound2t64 libgbm1 libxss1 libxtst6 libatk-bridge2.0-0t64 libdrm2 \
  libfuse2t64 fonts-dejavu-core >/dev/null

echo "== clean machine check =="
for t in python3 ffmpeg hermesclip yt-dlp; do
  if command -v "$t" >/dev/null; then echo "  $t: PRESENT (not clean!)"; else echo "  $t: absent"; fi
done

useradd -m tester
cp /work/HermesStudio.AppImage /home/tester/
cp /work/sample.mp4 /home/tester/sample.mp4
chown tester /home/tester/*
chmod +x /home/tester/HermesStudio.AppImage

su tester -c '
set -e
cd ~
./HermesStudio.AppImage --appimage-extract >/dev/null
Xvfb :9 -screen 0 1280x820x24 >/dev/null 2>&1 &
export DISPLAY=:9
sleep 2
./squashfs-root/hermes-studio --no-sandbox >app.log 2>&1 &
APP=$!
PORT=""
for i in $(seq 1 90); do
  PORT=$(for p in /proc/[0-9]*/cmdline; do tr "\0" " " < "$p" 2>/dev/null; echo; done | grep "hermesclip.cli" | grep -oE "\-\-port [0-9]+" | head -1 | cut -d" " -f2 || true)
  if [ -n "$PORT" ] && curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then break; fi
  sleep 1
done
echo "engine port: ${PORT:-none}"
sleep 4
import -window root /work/out/clean-01-open.png
[ -n "$PORT" ] || { echo "ENGINE NEVER CAME UP"; tail -20 app.log; exit 1; }

echo "== tools the engine sees =="
curl -s "http://127.0.0.1:$PORT/api/tools" | head -c 160; echo

echo "== real clip job (local file) =="
curl -s -X POST -H "Content-Type: application/json" -H "Origin: http://127.0.0.1:$PORT" \
  "http://127.0.0.1:$PORT/api/jobs" \
  -d "{\"src\":\"$HOME/sample.mp4\",\"mode\":\"captions\",\"whisper\":\"tiny\",\"aspect\":\"9:16\"}" | head -c 300; echo
for i in $(seq 1 240); do
  S=$(curl -s "http://127.0.0.1:$PORT/api/jobs" | grep -oE "\"status\": ?\"[a-z]+\"" | head -1 || true)
  case "$S" in *completed*|*failed*) break;; esac
  sleep 2
done
echo "job: $S"
curl -s "http://127.0.0.1:$PORT/api/jobs" | head -c 600; echo
echo "== real CLIP job (find moments + captions) =="
curl -s -X POST -H "Content-Type: application/json" -H "Origin: http://127.0.0.1:$PORT" \
  "http://127.0.0.1:$PORT/api/jobs" \
  -d "{\"src\":\"$HOME/sample.mp4\",\"mode\":\"clip\",\"whisper\":\"tiny\",\"aspect\":\"9:16\",\"max_clips\":2,\"min_sec\":12,\"max_sec\":25}" | head -c 120; echo
for i in $(seq 1 300); do
  S=$(curl -s "http://127.0.0.1:$PORT/api/jobs" | grep -oE "\"status\": ?\"[a-z]+\"" | head -1 || true)
  case "$S" in *completed*|*failed*) break;; esac
  sleep 2
done
echo "clip job: $S"
curl -s "http://127.0.0.1:$PORT/api/jobs" | grep -oE "\"error\": ?[^,]+" | head -1
echo "== outputs =="
find "$HOME/.hermes/clips/library" -name "*.mp4" 2>/dev/null | head -8
# Drive the real window to its screens (xdotool keys a hash change via the URL bar is not
# available; instead reload the window on each route through the engine page itself).
sleep 3
import -window root /work/out/clean-02-after-job.png
kill $APP; sleep 2
if for p in /proc/[0-9]*/cmdline; do tr "\0" " " < "$p" 2>/dev/null; echo; done | grep -qE "^[^ ]*/python3 -c .* studio --port [0-9]+"; then echo "ENGINE STILL RUNNING AFTER QUIT"; else echo "engine stopped on quit"; fi
if [ -f /work/pw/shots.js ] && [ -x /work/node/bin/node ]; then
  echo "== screenshots of the real window (fresh launch) =="
  /work/node/bin/node /work/pw/shots.js
fi
'
