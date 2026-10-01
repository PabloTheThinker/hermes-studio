#!/usr/bin/env bash
# Checks an extracted AppImage (squashfs-root): the libraries scripts/electron-builder-before-pack.js
# leaves out are absent from usr/lib, and ldd finds every dependency of the main binary and of every
# shared library in the tree, with usr/lib on LD_LIBRARY_PATH as AppRun sets it. A dependency that
# ldd cannot find on its own but that sits next to the library (an auditwheel sibling, loaded
# through the Python extension's RPATH) counts as present.
set -euo pipefail
root="$(cd "${1:?usage: check-appimage-libs.sh SQUASHFS_ROOT}" && pwd)"
export LD_LIBRARY_PATH="$root/usr/lib"
fail=0
for lib in libappindicator.so.1 libindicator.so.7 libgconf-2.so.4 libnotify.so.4; do
  if [ -e "$root/usr/lib/$lib" ]; then echo "FAIL: usr/lib/$lib is bundled"; fail=1; fi
done
echo "usr/lib: $(ls "$root/usr/lib" | tr '\n' ' ')"
n=0
while IFS= read -r -d '' f; do
  [ "$(head -c 4 "$f" | tail -c 3)" = ELF ] || continue
  n=$((n + 1))
  while read -r lib; do
    [ -n "$lib" ] || continue
    if [ -e "$(dirname "$f")/$lib" ]; then
      echo "  ${f#"$root"/}: $lib found next to it (loaded via the extension's RPATH)"
    else
      echo "FAIL: ${f#"$root"/} needs $lib: not found"; fail=1
    fi
  done < <(ldd "$f" 2>&1 | awk '/not found/ {print $1}')
done < <(find "$root" -type f \( -name '*.so' -o -name '*.so.*' -o -path "$root/hermes-studio" -o -path "$root/chrome_crashpad_handler" \) -print0)
echo "ldd checked $n ELF files (hermes-studio, chrome_crashpad_handler and every .so)"
[ "$fail" = 0 ] && echo "APPIMAGE LIBS OK"
exit "$fail"
