#!/usr/bin/env bash
# Clean-machine test for the one-line Linux installer.
# Runs in a fresh ubuntu:24.04 container as a normal user with NO sudo, NO FUSE,
# no python, no ffmpeg. Serves a fake "GitHub Releases" folder over HTTP so the
# exact files under test are what the installer downloads.
# Expects /work/HermesStudio.AppImage, /work/install.sh, /work/sample.mp4.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# curl is the only thing the installer needs; python3 is only for the fake release server here.
apt-get install -y -qq --no-install-recommends curl ca-certificates python3 \
  libgtk-3-0t64 libnss3 libasound2t64 libgbm1 libxss1 libxtst6 libatk-bridge2.0-0t64 libdrm2 \
  xvfb xauth >/dev/null

# A fake release: the same layout as github.com/<repo>/releases/latest/download/.
REL=/srv/rel/PabloTheThinker/hermes-studio/releases/latest/download
mkdir -p "$REL"
cp /work/HermesStudio.AppImage "$REL/Hermes-Studio-9.9.9.AppImage"
(cd "$REL" && sha256sum Hermes-Studio-9.9.9.AppImage > SHA256SUMS.txt)
(cd /srv/rel && python3 -m http.server 8765 >/dev/null 2>&1 &)
sleep 1

# A user who cannot become root and has no FUSE.
useradd -m -s /bin/bash tester
cp /work/install.sh /work/sample.mp4 /home/tester/
chown tester /home/tester/*
# The container's python3 is only for the fake server; hide it from the tester.
chmod 700 /usr/bin/python3*

su - tester -c '
set -euo pipefail
echo "== clean user check =="
for t in python3 ffmpeg hermes-studio yt-dlp sudo fusermount; do
  if command -v "$t" >/dev/null 2>&1 && "$t" --version >/dev/null 2>&1; then echo "  $t: PRESENT"; else echo "  $t: absent"; fi
done

echo "== 1. install (the one line, served locally) =="
export HERMES_STUDIO_DOWNLOAD_BASE=http://127.0.0.1:8765/PabloTheThinker/hermes-studio/releases/latest/download
cp install.sh install-local.sh
bash install-local.sh < /dev/null

echo "== 2. the command works in a new login shell =="
bash -lc "hermes-studio --version"
bash -lic "command -v hermes-studio" 2>/dev/null
readlink -f ~/.local/bin/hermes-studio

echo "== 3. doctor from the installed app =="
~/.local/bin/hermes-studio doctor --json | head -c 1200; echo
~/.local/bin/hermes-studio doctor --json | grep -q "\"ok\": true" || { echo "FAIL: doctor not ready"; exit 1; }

echo "== 4. MCP config points at a path that survives =="
CFG=$(~/.local/bin/hermes-studio mcp config --json)
echo "$CFG"
case "$CFG" in *"/.local/share/hermes-studio/app/resources/engine/hermes-studio"*) echo "mcp path stable";; *) echo "FAIL: mcp path"; exit 1;; esac

echo "== 5. MCP handshake over stdio =="
printf "%s\n" "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"t\",\"version\":\"1\"}}}" "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}" "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}" \
  | timeout 60 ~/.local/bin/hermes-studio mcp > mcp.out 2>/dev/null || true
grep -c "\"jsonrpc\"" mcp.out
grep -q "\"name\": \"run\"" mcp.out || { echo "FAIL: no tools over MCP"; head -c 400 mcp.out; exit 1; }
echo "mcp tools listed"

echo "== 6. a real captions job from the command line =="
~/.local/bin/hermes-studio run ~/sample.mp4 --mode captions --whisper tiny --json > run.json 2> run.err || { tail -5 run.err; exit 1; }
head -c 400 run.json; echo
grep -q "\"ok\": true" run.json || { echo "FAIL: captions job"; exit 1; }

echo "== 7. app menu entry =="
cat ~/.local/share/applications/hermes-studio.desktop
grep -q "^Exec=\"$HOME/.local/share/hermes-studio/app/hermes-studio\"" ~/.local/share/applications/hermes-studio.desktop

echo "== 8. the app window opens from the menu entry (engine starts) =="
Xvfb :9 -screen 0 1280x820x24 >/dev/null 2>&1 &
export DISPLAY=:9
sleep 2
EXEC=$(sed -n "s/^Exec=//p" ~/.local/share/applications/hermes-studio.desktop | sed "s/ %U//")
eval "$EXEC" >app.log 2>&1 &
APP=$!
PORT=""
for i in $(seq 1 90); do
  PORT=$(for p in /proc/[0-9]*/cmdline; do tr "\0" " " < "$p" 2>/dev/null; echo; done | grep "hermes_studio.cli" | grep -oE "\-\-port [0-9]+" | head -1 | cut -d" " -f2 || true)
  if [ -n "$PORT" ] && curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then break; fi
  sleep 1
done
[ -n "$PORT" ] || { echo "FAIL: app engine never came up"; tail -20 app.log; exit 1; }
echo "app engine on port $PORT"
kill $APP 2>/dev/null || true; sleep 2

echo "== 9. re-run = already up to date, no re-download =="
bash install-local.sh < /dev/null | tee rerun.log
grep -q "Already up to date" rerun.log || { echo "FAIL: re-run re-downloaded"; exit 1; }

echo "== 10. uninstall keeps clips =="
N=$(find "$HOME/.hermes/clips" -name "*.mp4" | wc -l)
bash install-local.sh --uninstall < /dev/null
[ ! -e ~/.local/bin/hermes-studio ] && [ ! -d ~/.local/share/hermes-studio ] && [ ! -f ~/.local/share/applications/hermes-studio.desktop ] || { echo "FAIL: uninstall left files"; exit 1; }
M=$(find "$HOME/.hermes/clips" -name "*.mp4" | wc -l)
[ "$N" -ge 1 ] && [ "$N" = "$M" ] || { echo "FAIL: clips changed ($N -> $M)"; exit 1; }
echo "uninstall clean; $M clip files kept"
echo "INSTALLER CLEAN TEST PASSED"
'
