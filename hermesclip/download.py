from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def is_url(src: str) -> bool:
    return src.startswith("http://") or src.startswith("https://")


def _ytdlp() -> str:
    sibling = Path(sys.executable).resolve().parent / "yt-dlp"
    if sibling.is_file():
        return str(sibling)
    found = shutil.which("yt-dlp")
    if not found:
        raise RuntimeError("yt-dlp is not on PATH")
    return found


def fetch(src: str, work: Path) -> Path:
    """Return a local video path. Downloads with yt-dlp when src is a URL."""
    if not is_url(src):
        p = Path(src).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        return p
    ytdlp = _ytdlp()
    out = work / "source.%(ext)s"
    cmd = [
        ytdlp,
        "--no-playlist",
        "--no-update",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        str(out),
        src,
    ]
    node = shutil.which("node") or shutil.which("nodejs")
    if node:
        cmd[3:3] = ["--js-runtimes", f"node:{node}"]
    subprocess.run(cmd, check=True)
    hits = sorted(
        (p for p in work.glob("source.*") if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not hits:
        raise RuntimeError("yt-dlp produced no file")
    return hits[0]
