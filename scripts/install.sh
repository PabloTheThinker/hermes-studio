#!/usr/bin/env bash
# Hermes Studio installer for Linux. One line, no sudo:
#
#   curl -fsSL https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.sh | bash
#
# What it does:
#   1. Downloads the latest desktop app from GitHub Releases and checks its SHA-256.
#   2. Unpacks it into ~/.local/share/hermes-studio (no FUSE needed, nothing system-wide).
#   3. Adds Hermes Studio to your app menu and the `hermes-studio` command to ~/.local/bin.
# Run it again to update. Your clips (~/.hermes/clips) are never touched.
#
# Options (after `bash -s --` when piped):
#   --version vX.Y.Z   install that release instead of the latest
#   --from FILE        install from an AppImage you already have (skips the download)
#   --uninstall        remove the app, menu entry and command (keeps your clips)
#   --no-modify-path   don't add ~/.local/bin to your shell's PATH
#   -h, --help         show this help
set -euo pipefail

REPO="${HERMES_STUDIO_REPO:-PabloTheThinker/hermes-studio}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA_HOME/hermes-studio"
BIN_DIR="$HOME/.local/bin"
DESKTOP_FILE="$DATA_HOME/applications/hermes-studio.desktop"
INSTALLER_URL="https://raw.githubusercontent.com/$REPO/main/scripts/install.sh"

VERSION=""
FROM=""
UNINSTALL=false
MODIFY_PATH=true

usage() {
  cat <<EOF
Hermes Studio installer for Linux (no sudo).

  curl -fsSL $INSTALLER_URL | bash
  curl -fsSL $INSTALLER_URL | bash -s -- [options]

Options:
  --version vX.Y.Z   install that release instead of the latest
  --from FILE        install from an AppImage you already have (skips the download)
  --uninstall        remove the app, menu entry and command (keeps your clips)
  --no-modify-path   don't add ~/.local/bin to your shell's PATH
  -h, --help         show this help

Run it again to update. Your clips (~/.hermes/clips) are never touched.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version) [ $# -ge 2 ] || { echo "--version needs a value, e.g. v0.5.2" >&2; exit 2; }; VERSION="$2"; shift 2 ;;
    --from) [ $# -ge 2 ] || { echo "--from needs a file" >&2; exit 2; }; FROM="$2"; shift 2 ;;
    --uninstall) UNINSTALL=true; shift ;;
    --no-modify-path) MODIFY_PATH=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_AMBER=$'\033[38;2;255;200;61m' C_GREEN=$'\033[32m' C_RED=$'\033[31m' C_DIM=$'\033[2m' C_BOLD=$'\033[1m' C_NC=$'\033[0m'
else
  C_AMBER="" C_GREEN="" C_RED="" C_DIM="" C_BOLD="" C_NC=""
fi
say()  { printf '%s→%s %s\n' "$C_AMBER" "$C_NC" "$1"; }
ok()   { printf '%s✓%s %s\n' "$C_GREEN" "$C_NC" "$1"; }
warn() { printf '%s!%s %s\n' "$C_AMBER" "$C_NC" "$1" >&2; }
fail() { printf '%s✗%s %s\n' "$C_RED" "$C_NC" "$1" >&2; exit 1; }

# Only ever delete inside our own folder (never an empty or foreign path).
safe_rm() {
  local p="$1"
  [ -n "$p" ] || fail "internal: refusing to delete an empty path"
  case "$p" in
    "$DEST"|"$DEST"/*) rm -rf -- "$p" ;;
    *) fail "internal: refusing to delete $p (outside $DEST)" ;;
  esac
}

uninstall() {
  say "Removing Hermes Studio"
  if [ -L "$BIN_DIR/hermes-studio" ]; then
    case "$(readlink "$BIN_DIR/hermes-studio")" in "$DEST"/*) rm -f "$BIN_DIR/hermes-studio" ;; esac
  fi
  [ -f "$DESKTOP_FILE" ] && rm -f "$DESKTOP_FILE"
  [ -d "$DEST" ] && safe_rm "$DEST"
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_HOME/applications" 2>/dev/null || true
  ok "Hermes Studio removed. Your clips in ~/.hermes/clips were kept."
}

check_platform() {
  case "$(uname -s)" in
    Linux) ;;
    Darwin) fail "macOS isn't available yet. The command line works today: uv tool install git+https://github.com/$REPO" ;;
    *) fail "This installer is for Linux. On Windows, run in PowerShell: irm https://raw.githubusercontent.com/$REPO/main/scripts/install.ps1 | iex" ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) ;;
    *) fail "The desktop app is built for 64-bit Intel/AMD (x86_64); this machine is $(uname -m). The command line works: uv tool install git+https://github.com/$REPO" ;;
  esac
  for t in curl sha256sum; do
    command -v "$t" >/dev/null 2>&1 || fail "Needs '$t'. Ubuntu/Debian: sudo apt install $t"
  done
}

# Writes the command shim into an unpacked app when the release predates it.
ensure_shim() {
  local engine="$1/resources/engine"
  [ -d "$engine/python" ] || fail "This download has no engine inside it; please report it: https://github.com/$REPO/issues"
  # Build-time scripts carry the build machine's path in their first line; they can't run here.
  rm -f "$engine/python/bin/hermes-studio" "$engine/python/bin/hermesclip"
  if [ ! -x "$engine/hermes-studio" ]; then
    cat > "$engine/hermes-studio" <<'SH'
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
    chmod +x "$engine/hermes-studio"
  fi
}

add_to_path() {
  case ":$PATH:" in *":$BIN_DIR:"*) return 0 ;; esac
  [ "$MODIFY_PATH" = true ] || { warn "$BIN_DIR is not on your PATH; add it to use the hermes-studio command."; return 0; }
  local rc line='export PATH="$HOME/.local/bin:$PATH"'
  case "${SHELL##*/}" in
    zsh) rc="$HOME/.zshrc" ;;
    fish) rc="$HOME/.config/fish/config.fish"; line='fish_add_path "$HOME/.local/bin"' ;;
    *) rc="$HOME/.bashrc" ;;
  esac
  if [ -f "$rc" ] && grep -qE '\.local/bin' "$rc" 2>/dev/null; then
    :
  else
    mkdir -p "$(dirname "$rc")"
    printf '\n# hermes-studio command\n%s\n' "$line" >> "$rc"
    ok "Added ~/.local/bin to your PATH in $rc"
  fi
  RELOAD_HINT="Open a new terminal (or run: source $rc) to use the hermes-studio command."
}

main() {
  if [ "$UNINSTALL" = true ]; then uninstall; return; fi
  check_platform
  printf '\n%sHermes Studio%s %s· local video tools for people and AI agents%s\n\n' "$C_BOLD" "$C_NC" "$C_DIM" "$C_NC"
  mkdir -p "$DEST"

  local base sums name want file have
  if [ -n "${HERMES_STUDIO_DOWNLOAD_BASE:-}" ]; then   # a mirror, or the test harness
    base="${HERMES_STUDIO_DOWNLOAD_BASE%/}"
  elif [ -n "$VERSION" ]; then
    case "$VERSION" in v*) ;; *) VERSION="v$VERSION" ;; esac
    base="https://github.com/$REPO/releases/download/$VERSION"
  else
    base="https://github.com/$REPO/releases/latest/download"
  fi

  if [ -n "$FROM" ]; then
    [ -f "$FROM" ] || fail "No file at $FROM"
    file="$(readlink -f "$FROM")"
    name="$(basename "$file")"
    want="$(sha256sum "$file" | cut -d' ' -f1)"
    say "Installing from $file"
  else
    say "Finding the ${VERSION:-latest} release"
    sums="$(curl -fsSL --retry 3 "$base/SHA256SUMS.txt")" \
      || fail "Couldn't reach GitHub Releases ($base). Check your connection and try again."
    name="$(printf '%s\n' "$sums" | awk '$2 ~ /\.AppImage$/ {print $2; exit}')"
    want="$(printf '%s\n' "$sums" | awk '$2 ~ /\.AppImage$/ {print $1; exit}')"
    [ -n "$name" ] && [ -n "$want" ] || fail "That release has no Linux app listed in SHA256SUMS.txt."

    if [ -f "$DEST/installed" ] && [ -x "$DEST/app/hermes-studio" ] && grep -q "$want" "$DEST/installed"; then
      ok "Already up to date (${name})"
      ensure_shim "$DEST/app"
      link_and_menu
      finish
      return
    fi

    file="$DEST/.download/$name"
    mkdir -p "$DEST/.download"
    say "Downloading $name"
    local progress=(-sS)
    [ -t 2 ] && progress=(--progress-bar)
    curl -fL --retry 3 --retry-delay 2 -C - "${progress[@]}" -o "$file" "$base/$name" \
      || { rm -f "$file"; fail "Download failed. Run the installer again; it resumes where it stopped."; }
    have="$(sha256sum "$file" | cut -d' ' -f1)"
    if [ "$have" != "$want" ]; then
      rm -f "$file"
      fail "The download doesn't match its published checksum (got $have). Nothing was installed. Run the installer again."
    fi
    ok "Checksum verified"
  fi

  say "Unpacking (no FUSE or admin rights needed)"
  local stage="$DEST/.stage"
  [ -d "$stage" ] && safe_rm "$stage"
  mkdir -p "$stage"
  chmod +x "$file" 2>/dev/null || true
  (cd "$stage" && "$file" --appimage-extract >/dev/null 2>&1) || fail "Couldn't unpack $name. Is the file complete?"
  [ -x "$stage/squashfs-root/hermes-studio" ] || fail "The unpacked app is missing its program; please report it."
  ensure_shim "$stage/squashfs-root"

  # Swap in the new version; the old one is removed only after the new one is in place.
  [ -d "$DEST/app.old" ] && safe_rm "$DEST/app.old"
  [ -d "$DEST/app" ] && mv "$DEST/app" "$DEST/app.old"
  mv "$stage/squashfs-root" "$DEST/app"
  [ -d "$DEST/app.old" ] && safe_rm "$DEST/app.old"
  safe_rm "$stage"
  [ -n "$FROM" ] || safe_rm "$DEST/.download"
  printf '%s  %s\n' "$want" "$name" > "$DEST/installed"
  ok "Installed to $DEST/app"

  link_and_menu
  check_libraries
  finish
}

link_and_menu() {
  mkdir -p "$BIN_DIR" "$DATA_HOME/applications"
  ln -sfn "$DEST/app/resources/engine/hermes-studio" "$BIN_DIR/hermes-studio"
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Hermes Studio
Comment=Local video tools. Clips, captions, library.
Exec="$DEST/app/hermes-studio" --no-sandbox %U
Icon=$DEST/app/hermes-studio.png
Terminal=false
Type=Application
Categories=AudioVideo;Video;
StartupWMClass=Hermes Studio
EOF
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_HOME/applications" 2>/dev/null || true
  ok "Added to your app menu and linked the hermes-studio command"
}

check_libraries() {
  command -v ldd >/dev/null 2>&1 || return 0
  local missing
  missing="$(ldd "$DEST/app/hermes-studio" 2>/dev/null | awk '/not found/ {print $1}' | tr '\n' ' ')"
  if [ -n "$missing" ]; then
    warn "The window needs a few desktop libraries this machine lacks: $missing"
    warn "Ubuntu/Debian: sudo apt install libgtk-3-0 libnss3 libasound2 libgbm1 libxss1 libxtst6"
    warn "The hermes-studio command works without them."
  fi
}

finish() {
  local v
  v="$("$DEST/app/resources/engine/hermes-studio" --version 2>/dev/null | tail -1)" || v=""
  [ -n "$v" ] || fail "Installed, but the engine didn't start. Run: $DEST/app/resources/engine/hermes-studio doctor"
  RELOAD_HINT=""
  add_to_path
  printf '\n%s✓ Hermes Studio is ready%s %s(%s)%s\n\n' "$C_GREEN$C_BOLD" "$C_NC" "$C_DIM" "$v" "$C_NC"
  printf '  Open the app      from your app menu, or: hermes-studio app\n'
  printf '  Check the setup   hermes-studio doctor\n'
  printf '  Make shorts       hermes-studio run talk.mp4\n'
  printf '  Use with your AI  hermes-studio mcp install claude   %s(or grok, codex, cursor, hermes)%s\n' "$C_DIM" "$C_NC"
  printf '  Update later      hermes-studio update   %s(or run this installer again)%s\n' "$C_DIM" "$C_NC"
  [ -z "$RELOAD_HINT" ] || printf '\n  %s\n' "$RELOAD_HINT"
  printf '\n'
}

export HERMES_STUDIO_INSTALLER_URL="$INSTALLER_URL"
main
