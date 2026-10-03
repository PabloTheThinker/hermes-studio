"""S4 media services: probe, proxy, thumbnail strip, waveform and words for one media file.

Everything here reads a source file and writes derived files under a project's ``cache/``. Nothing
here writes the timeline: ``import_media`` (project.py) probes, adds the media entry through the
op log (``add_media``), then runs :func:`build` in the background. Each derived file is written
with a temp name and replaced, so a reader sees an old file, a new file or none.

Times are timeline ticks (``timeline.TICK_RATE`` per second) wherever they leave this module.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from hermes_studio import timeline as T
from hermes_studio.api import HermesStudioError

Progress = Callable[[str, float], None]  # (stage, 0..1 within the stage)

PROXY_HEIGHT = 540  # never upscaled
PROXY_GOP_SEC = Fraction(1, 2)
THUMB_EVERY_SEC = 2
THUMB_HEIGHT = 90  # 160 px wide at 16:9
THUMB_COLS = 10
WAVE_RATE = 8000  # Hz, mono, decoded for peaks only
WAVE_PEAKS_PER_SEC = 100
STAGES = ("proxy", "thumbs", "wave", "words")


class MediaError(HermesStudioError):
    """A media file that can't be probed or processed."""

    def __init__(self, message: str, *, hint: str = "", code: str = "bad_input") -> None:
        super().__init__(message, code=code, hint=hint or "Check the file plays in a video player, then try again.")


# --------------------------------------------------------------------------- probe


def _ratio(raw: Any) -> Fraction | None:
    """ffprobe's "30000/1001"; None for "0/0", missing or malformed."""
    if not isinstance(raw, str) or "/" not in raw:
        return None
    a, _, b = raw.partition("/")
    try:
        num, den = int(a), int(b)
    except ValueError:
        return None
    if num <= 0 or den <= 0:
        return None
    return Fraction(num, den)


def _seconds_to_ticks(raw: Any) -> int | None:
    """ffprobe's decimal seconds as exact ticks (half up); None when missing or not positive."""
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d <= 0:
        return None
    ticks = Fraction(d) * T.TICK_RATE
    return int(ticks + Fraction(1, 2)) if ticks.denominator != 1 else int(ticks)


def _rotation(stream: dict) -> int:
    for sd in stream.get("side_data_list") or []:
        if isinstance(sd, dict) and "rotation" in sd:
            with contextlib.suppress(TypeError, ValueError):
                return int(float(sd["rotation"])) % 360
    with contextlib.suppress(TypeError, ValueError):
        return int((stream.get("tags") or {}).get("rotate", 0)) % 360
    return 0


def probe(path: str | os.PathLike) -> dict:
    """What the timeline and the services need to know about one file.

    Returns ``{dur, fps, width, height, rotation, vfr, has_video, has_audio, video_codec,
    audio_codec}``: ``dur`` in ticks, ``fps`` a ``[num, den]`` pair or None (audio only),
    ``width``/``height`` as displayed (rotation applied), ``vfr`` true when the average and
    nominal frame rates differ. Raises :class:`MediaError` for anything ffprobe can't read or a
    file with neither audio nor video."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise MediaError("ffprobe is not installed", hint="Run: hermes-studio doctor", code="missing_dependency") from None
    except subprocess.TimeoutExpired:
        raise MediaError(f"ffprobe took too long on {Path(path).name}") from None
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["ffprobe failed"])[-1]
        raise MediaError(f"can't read {Path(path).name}: {last.replace(str(path), Path(path).name)[:200]}")
    try:
        info = json.loads(proc.stdout)
    except ValueError:
        raise MediaError(f"can't read {Path(path).name}: ffprobe gave no JSON") from None
    streams = [s for s in info.get("streams") or [] if isinstance(s, dict)]
    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None and audio is None:
        raise MediaError(f"{Path(path).name} has no audio or video")
    fmt = info.get("format") or {}
    dur = _seconds_to_ticks(fmt.get("duration"))
    for s in (video, audio):
        if dur is None and s is not None:
            dur = _seconds_to_ticks(s.get("duration"))
    if dur is None:
        raise MediaError(f"{Path(path).name} has no duration (a live stream or a broken file?)")
    out: dict[str, Any] = {
        "dur": dur,
        "fps": None,
        "width": None,
        "height": None,
        "rotation": 0,
        "vfr": False,
        "has_video": video is not None,
        "has_audio": audio is not None,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
    }
    if video is not None:
        avg, nominal = _ratio(video.get("avg_frame_rate")), _ratio(video.get("r_frame_rate"))
        fps = avg or nominal
        if fps is None:
            raise MediaError(f"{Path(path).name}: the video stream has no frame rate")
        out["fps"] = [fps.numerator, fps.denominator]
        out["vfr"] = bool(avg and nominal and avg != nominal)
        rot = _rotation(video)
        w, h = video.get("width"), video.get("height")
        if isinstance(w, int) and isinstance(h, int):
            out["width"], out["height"] = (h, w) if rot in (90, 270) else (w, h)
        out["rotation"] = rot
    return out


def media_entry(path: str | os.PathLike, info: dict) -> dict:
    """The timeline ``media`` entry for a probed file (docs/timeline.md: ``{path, dur, fps}``)."""
    return {"path": str(Path(path).resolve()), "dur": info["dur"], "fps": info["fps"]}


# --------------------------------------------------------------------------- cache layout


def cache_paths(project_dir: Path, mid: str) -> dict[str, Path]:
    c = project_dir / "cache"
    return {
        "proxy": c / "proxy" / f"{mid}.mp4",
        "thumbs": c / "thumbs" / f"{mid}.jpg",
        "thumbs_index": c / "thumbs" / f"{mid}.json",
        "wave": c / "wave" / f"{mid}.json",
        "words": c / "words" / f"{mid}.json",
        "status": c / "media" / f"{mid}.json",
    }


def _tmp(p: Path) -> Path:
    return p.with_name(f".{p.stem}.tmp{p.suffix}")


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    t = _tmp(p)
    fd = os.open(str(t), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, separators=(",", ":"))
    os.replace(t, p)


def read_json(p: Path) -> Any:
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- ffmpeg with progress


def _ffmpeg(args: list[str], dur_ticks: int, stage: str, on_progress: Progress | None, cancel: Callable[[], bool]) -> None:
    """Run ffmpeg with ``-progress pipe:1`` and report ``out_time`` / ``dur`` for ``stage``."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error", "-progress", "pipe:1", "-y", *args]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise MediaError("ffmpeg is not installed", hint="Run: hermes-studio doctor", code="missing_dependency") from None
    total_us = max(1, dur_ticks * 1_000_000 // T.TICK_RATE)
    err = ""
    try:
        assert p.stdout is not None
        for line in p.stdout:
            if cancel():
                p.kill()
                break
            key, _, val = line.strip().partition("=")
            if key == "out_time_us" and on_progress and val.isdigit():
                on_progress(stage, min(1.0, int(val) / total_us))
        p.wait()
        err = p.stderr.read() if p.stderr else ""
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        for s in (p.stdout, p.stderr):
            if s:
                s.close()
    if cancel():
        raise MediaError(f"{stage} cancelled", code="failed")
    if p.returncode != 0:
        raise MediaError(f"{stage} failed: {err.strip()[-300:] or f'ffmpeg exit {p.returncode}'}", code="failed")
    if on_progress:
        on_progress(stage, 1.0)


def _even(n: int) -> int:
    return max(2, n - n % 2)


def make_proxy(src: Path, dest: Path, info: dict, on_progress: Progress | None = None, cancel=lambda: False) -> None:
    """540p (never upscaled) H.264, constant frame rate at the source's rate, a keyframe every
    0.5 s, AAC: cheap to seek and play in the Edit page. Audio-only media get an AAC-only proxy."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = _tmp(dest)
    args = ["-i", str(src)]
    if info["has_video"]:
        fps = Fraction(*info["fps"])
        h = min(PROXY_HEIGHT, info["height"] or PROXY_HEIGHT)
        gop = max(1, round(fps * PROXY_GOP_SEC))
        args += ["-map", "0:v:0", "-vf", f"scale=-2:{_even(h)},fps={fps.numerator}/{fps.denominator},format=yuv420p"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", str(gop), "-keyint_min", str(gop)]
        args += ["-sc_threshold", "0", "-fps_mode", "cfr"]
    else:
        args += ["-vn"]
    if info["has_audio"]:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "96k", "-ac", "2"]
    args += ["-movflags", "+faststart", "-f", "mp4", str(t)]
    _ffmpeg(args, info["dur"], "proxy", on_progress, cancel)
    os.replace(t, dest)


def make_thumbs(
    src: Path, sprite: Path, index: Path, info: dict, on_progress: Progress | None = None, cancel=lambda: False
) -> dict:
    """One frame every ``THUMB_EVERY_SEC`` s, ``THUMB_HEIGHT`` px high, tiled ``THUMB_COLS`` wide
    into one JPEG sprite. The index says where frame ``i`` (time ``i * every``) sits."""
    if not info["has_video"]:
        raise MediaError("no video stream for thumbnails", code="bad_input")
    sec = info["dur"] / T.TICK_RATE
    n = max(1, int(sec // THUMB_EVERY_SEC) + (1 if sec % THUMB_EVERY_SEC else 0))
    rows = -(-n // THUMB_COLS)
    w, h = info["width"] or 16, info["height"] or 9
    tw = _even(round(THUMB_HEIGHT * w / h))
    sprite.parent.mkdir(parents=True, exist_ok=True)
    t = _tmp(sprite)
    vf = f"fps=1/{THUMB_EVERY_SEC},scale={tw}:{THUMB_HEIGHT},tile={THUMB_COLS}x{rows}"
    _ffmpeg(
        ["-i", str(src), "-an", "-vf", vf, "-frames:v", "1", "-q:v", "5", "-f", "image2", str(t)],
        info["dur"],
        "thumbs",
        on_progress,
        cancel,
    )
    os.replace(t, sprite)
    idx = {
        "every_s": THUMB_EVERY_SEC,
        "count": n,
        "cols": THUMB_COLS,
        "rows": rows,
        "width": tw,
        "height": THUMB_HEIGHT,
        "sprite": sprite.name,
    }
    _write_json(index, idx)
    return idx


def make_wave(src: Path, dest: Path, info: dict, on_progress: Progress | None = None, cancel=lambda: False) -> dict:
    """Peaks for drawing: ``WAVE_PEAKS_PER_SEC`` [min, max] pairs per second of mono audio, as
    ints in -128..127. Decoded once at ``WAVE_RATE`` Hz through a pipe; nothing is kept but peaks."""
    import numpy as np

    if not info["has_audio"]:
        raise MediaError("no audio stream for a waveform", code="bad_input")
    per = WAVE_RATE // WAVE_PEAKS_PER_SEC
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(WAVE_RATE),
        "-f",
        "s16le",
        "-",
    ]
    total = max(1, info["dur"] * WAVE_RATE // T.TICK_RATE)
    peaks: list[list[int]] = []
    carry = b""
    got = 0
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        assert p.stdout is not None
        while True:
            if cancel():
                p.kill()
                raise MediaError("wave cancelled", code="failed")
            chunk = p.stdout.read(per * 2 * WAVE_PEAKS_PER_SEC * 10)  # 10 s at a time
            if not chunk:
                break
            buf = carry + chunk
            whole = len(buf) // (per * 2) * (per * 2)
            carry = buf[whole:]
            if whole:
                a = np.frombuffer(buf[:whole], dtype="<i2").reshape(-1, per)
                lo, hi = (a.min(axis=1) >> 8).astype(int), (a.max(axis=1) >> 8).astype(int)
                peaks.extend([int(x), int(y)] for x, y in zip(lo, hi, strict=True))
                got += whole // 2
                if on_progress:
                    on_progress("wave", min(1.0, got / total))
        if carry:
            a = np.frombuffer(carry[: len(carry) // 2 * 2], dtype="<i2")
            if a.size:
                peaks.append([int(a.min() >> 8), int(a.max() >> 8)])
        if p.wait() != 0:
            raise MediaError("wave failed: ffmpeg could not decode the audio", code="failed")
    data = {"peaks_per_s": WAVE_PEAKS_PER_SEC, "count": len(peaks), "peaks": peaks}
    _write_json(dest, data)
    if on_progress:
        on_progress("wave", 1.0)
    return {"peaks_per_s": WAVE_PEAKS_PER_SEC, "count": len(peaks)}


def make_words(src: Path, dest: Path, work: Path, model: str = "tiny", on_progress: Progress | None = None) -> dict:
    """Whisper words in source ticks: ``{"words": [{"w", "in", "out"}]}`` (``in < out``)."""
    from hermes_studio.transcribe import transcribe

    if on_progress:
        on_progress("words", 0.0)
    tr = transcribe(src, work, model)
    words = []
    for w in tr.words:
        a = _seconds_to_ticks(max(w.start, 0) or "0") or 0
        b = _seconds_to_ticks(w.end) or 0
        if b > a and w.text.strip():
            words.append({"w": w.text.strip(), "in": a, "out": b})
    _write_json(dest, {"words": words})
    if on_progress:
        on_progress("words", 1.0)
    return {"count": len(words)}


# --------------------------------------------------------------------------- transcript -> timeline


def timeline_words(doc: dict, words: dict[str, list[dict]]) -> list[dict]:
    """Map each media's words (source ticks) onto the timeline, through every clip that shows
    them. A word is kept when its midpoint lies inside the clip's ``src`` range; its timeline
    span is clamped to the clip. Sorted by timeline time, then clip id. Each row:
    ``{w, at, end, clip, media, src_in, src_out}`` (ticks)."""
    spans = T.resolve(doc)
    out = []
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it.get("type") != "clip" or it["media"] not in words or it["id"] not in spans:
                continue
            start = spans[it["id"]][0]
            src_in, src_out = it["src"]
            speed = Fraction(*it["props"]["speed"]) if isinstance((it.get("props") or {}).get("speed"), list) else Fraction(1)
            for w in words[it["media"]]:
                if not (2 * src_in <= w["in"] + w["out"] < 2 * src_out):  # the midpoint, in whole ticks
                    continue
                a, b = max(w["in"], src_in), min(w["out"], src_out)
                at = start + int((a - src_in) / speed)
                end = start + int((b - src_in) / speed)
                out.append(
                    {
                        "w": w["w"],
                        "at": at,
                        "end": max(end, at),
                        "clip": it["id"],
                        "media": it["media"],
                        "src_in": w["in"],
                        "src_out": w["out"],
                    }
                )
    out.sort(key=lambda r: (r["at"], r["clip"]))
    return out
