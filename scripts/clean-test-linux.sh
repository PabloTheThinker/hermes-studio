#!/usr/bin/env bash
# Clean-machine test for the Linux AppImage.
# Runs inside a fresh ubuntu:24.04 container: installs ONLY what a desktop
# user already has (a display server + the libraries Electron needs), NOT
# python, ffmpeg or hermes-studio. Then opens the app, waits for its own engine,
# screenshots the window, runs one real clip job through the engine's API,
# and screenshots the finished run.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  xvfb xauth x11-apps imagemagick curl ca-certificates \
  libgtk-3-0t64 libnss3 libasound2t64 libgbm1 libxss1 libxtst6 libatk-bridge2.0-0t64 libdrm2 \
  libfuse2t64 libatomic1 fonts-dejavu-core >/dev/null

echo "== clean machine check =="
for t in python3 ffmpeg hermes-studio yt-dlp; do
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
  PORT=$(for p in /proc/[0-9]*/cmdline; do tr "\0" " " < "$p" 2>/dev/null; echo; done | grep "hermes_studio.cli" | grep -oE "\-\-port [0-9]+" | head -1 | cut -d" " -f2 || true)
  if [ -n "$PORT" ] && curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then break; fi
  sleep 1
done
echo "engine port: ${PORT:-none}"
sleep 4
import -window root /work/out/clean-01-open.png
[ -n "$PORT" ] || { echo "ENGINE NEVER CAME UP"; tail -20 app.log; exit 1; }

echo "== tools the engine sees =="
curl -s "http://127.0.0.1:$PORT/api/tools" | head -c 160; echo

# >>> job helpers (POSIX sh; tests/test_clean_test_script.py runs this block) >>>
# Each job is tracked by the id its own submit returned, never by list order.
API="http://127.0.0.1:$PORT"
POLL_SLEEP="${POLL_SLEEP:-2}"
POLL_FILE="$HOME/.clean-test-poll.json"
submit_job() { # $1 = JSON body, $2 = label; sets JOB_ID
  R=$(curl -s -X POST -H "Content-Type: application/json" -H "Origin: $API" "$API/api/jobs" -d "$1" || true)
  printf "%s" "$R" | head -c 300; echo
  JOB_ID=$(printf "%s" "$R" | grep -oE "\"id\": ?\"[A-Za-z0-9_-]+\"" | head -1 | grep -oE "[A-Za-z0-9_-]+\"$" | tr -d "\"" || true)
  [ -n "$JOB_ID" ] || { echo "FAIL: $2 job: submit returned no job id"; exit 1; }
  echo "$2 job id: $JOB_ID"
}
wait_job() { # $1 = job id, $2 = max polls, $3 = label
  n=0; S=""; CODE=""
  while [ "$n" -lt "$2" ]; do
    n=$((n + 1))
    CODE=$(curl -s -o "$POLL_FILE" -w "%{http_code}" "$API/api/jobs/$1" || true)
    if [ "$CODE" = "404" ]; then echo "FAIL: $3 job $1 is missing (GET /api/jobs/$1 returned 404)"; exit 1; fi
    if [ "$CODE" = "200" ]; then
      S=$(grep -oE "\"status\": ?\"[a-z]+\"" "$POLL_FILE" | head -1 | grep -oE "[a-z]+\"$" | tr -d "\"" || true)
      case "$S" in
        completed) echo "$3 job $1: completed"; return 0;;
        failed) echo "FAIL: $3 job $1 failed: $(grep -oE "\"error\": ?\"[^\"]*\"" "$POLL_FILE" | head -1 || true)"; exit 1;;
      esac
    fi
    sleep "$POLL_SLEEP"
  done
  echo "FAIL: $3 job $1 did not finish after $2 polls (last status: ${S:-none}, last HTTP: ${CODE:-none})"; exit 1
}
# <<< job helpers <<<

echo "== real clip job (local file) =="
submit_job "{\"src\":\"$HOME/sample.mp4\",\"mode\":\"captions\",\"whisper\":\"tiny\",\"aspect\":\"9:16\"}" captions
wait_job "$JOB_ID" 240 captions
echo "== real CLIP job (find moments + captions) =="
submit_job "{\"src\":\"$HOME/sample.mp4\",\"mode\":\"clip\",\"whisper\":\"tiny\",\"aspect\":\"9:16\",\"max_clips\":2,\"min_sec\":12,\"max_sec\":25}" clip
wait_job "$JOB_ID" 300 clip
echo "== outputs =="
N=$(find "$HOME/.hermes/clips/library" -name "clip-*.mp4" 2>/dev/null | wc -l)
find "$HOME/.hermes/clips/library" -name "*.mp4" 2>/dev/null | head -8
[ "$N" -ge 1 ] || { echo "FAIL: no clips written"; exit 1; }
# Drive the real window to its screens (xdotool keys a hash change via the URL bar is not
# available; instead reload the window on each route through the engine page itself).
sleep 3
import -window root /work/out/clean-02-after-job.png
kill $APP; sleep 2
if for p in /proc/[0-9]*/cmdline; do tr "\0" " " < "$p" 2>/dev/null; echo; done | grep -qE "^[^ ]*/python3 -c .* studio --port [0-9]+"; then echo "FAIL: ENGINE STILL RUNNING AFTER QUIT"; exit 1; else echo "engine stopped on quit"; fi
if [ -f /work/pw/shots.js ] && [ -x /work/node/bin/node ]; then
  echo "== screenshots of the real window (fresh launch) =="
  /work/node/bin/node /work/pw/shots.js
fi
echo "== libraries: nothing missing on a clean machine =="
bash /work/check-appimage-libs.sh "$HOME/squashfs-root"
echo "LINUX CLEAN TEST PASSED"
'
