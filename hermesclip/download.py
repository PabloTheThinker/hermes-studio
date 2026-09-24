from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

LIVE_DEFAULT_SEC = 20 * 60
LIVE_MAX_SEC = 2 * 60 * 60
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".ts", ".m4v"}


@dataclass
class SourceInfo:
    src: str
    title: str
    extractor: str
    video_id: str
    is_live: bool
    live_status: str | None
    duration: float | None
    webpage_url: str


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


def _node_args() -> list[str]:
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        return []
    return ["--js-runtimes", f"node:{node}"]


def kind_of(src: str) -> str:
    if not is_url(src):
        return "file"
    host = (urlparse(src).hostname or "").lower()
    if host.endswith("youtube.com") or host == "youtu.be" or host.endswith("youtube-nocookie.com"):
        return "youtube"
    if host in {"x.com", "twitter.com", "mobile.twitter.com", "www.x.com"}:
        return "x"
    if "twitch.tv" in host:
        return "twitch"
    return "url"


def probe(src: str) -> SourceInfo:
    """Read title / live flag without downloading. Local files get a basename title."""
    if not is_url(src):
        p = Path(src).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        return SourceInfo(
            src=str(p),
            title=p.stem,
            extractor="file",
            video_id=p.stem[:32],
            is_live=False,
            live_status=None,
            duration=None,
            webpage_url=str(p),
        )
    ytdlp = _ytdlp()
    cmd = [
        ytdlp,
        "--no-playlist",
        "--no-update",
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
        *_node_args(),
        src,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "probe failed")[-800:]
        raise RuntimeError(err.strip() or "yt-dlp probe failed")
    data = json.loads(proc.stdout)
    live_status = data.get("live_status")
    is_live = bool(data.get("is_live")) or live_status in {"is_live", "is_upcoming"}
    dur = data.get("duration")
    return SourceInfo(
        src=src,
        title=str(data.get("title") or data.get("id") or src),
        extractor=str(data.get("extractor") or kind_of(src)),
        video_id=str(data.get("id") or ""),
        is_live=is_live,
        live_status=str(live_status) if live_status else None,
        duration=float(dur) if isinstance(dur, (int, float)) else None,
        webpage_url=str(data.get("webpage_url") or src),
    )


def fetch(
    src: str,
    work: Path,
    *,
    live_seconds: int = LIVE_DEFAULT_SEC,
    live_from_start: bool = False,
    info: SourceInfo | None = None,
) -> Path:
    """Return a local video path. Downloads with yt-dlp when src is a URL.

    Live YouTube / X / Twitch: record a slice (default 20 min, cap 2 h), then
    the same clip pipeline runs. Past livestreams (was_live VODs) download whole.
    """
    if not is_url(src):
        p = Path(src).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        return p

    work.mkdir(parents=True, exist_ok=True)
    ytdlp = _ytdlp()
    meta = info or probe(src)
    (work / "source.json").write_text(
        json.dumps(
            {
                "src": src,
                "title": meta.title,
                "extractor": meta.extractor,
                "id": meta.video_id,
                "is_live": meta.is_live,
                "live_status": meta.live_status,
                "duration": meta.duration,
            },
            indent=2,
        )
    )

    out_tmpl = str(work / "source.%(ext)s")
    cmd = [
        ytdlp,
        "--no-playlist",
        "--no-update",
        "--no-warnings",
        *_node_args(),
        "-o",
        out_tmpl,
        src,
    ]

    if meta.is_live:
        cap = max(60, min(int(live_seconds or LIVE_DEFAULT_SEC), LIVE_MAX_SEC))
        cmd += [
            "-f",
            "b/bv*+ba/best",
            "--hls-use-mpegts",
            "--merge-output-format",
            "mp4",
        ]
        if live_from_start:
            cmd.append("--live-from-start")
        # ffmpeg downloader can stop a live capture at N seconds.
        cmd += ["--downloader", "ffmpeg", "--downloader-args", f"ffmpeg_i:-t {cap}"]
        timeout = cap + 120
    else:
        cmd += ["-f", "bv*+ba/b", "--merge-output-format", "mp4"]
        timeout = 4 * 60 * 60

    try:
        subprocess.run(cmd, check=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if not meta.is_live:
            raise
        # Live capture often ends by timeout; keep whatever landed.
        _ = exc

    hits = _find_source(work)
    if not hits:
        raise RuntimeError("yt-dlp produced no file")
    src_path = hits[0]
    if src_path.suffix.lower() == ".ts":
        mp4 = work / "source.mp4"
        remux = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src_path), "-c", "copy", "-movflags", "+faststart", str(mp4)],
            capture_output=True,
            text=True,
        )
        if remux.returncode == 0 and mp4.is_file():
            return mp4
    return src_path


def _find_source(work: Path) -> list[Path]:
    return sorted(
        (p for p in work.glob("source.*") if p.suffix.lower() in VIDEO_EXTS),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
