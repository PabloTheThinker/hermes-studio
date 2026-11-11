"""Burn caption lines written by the calling Hermes agent.

The speech model is not the caption writer. An agent may ask for a draft
transcript, then it writes the lines. This module only burns those lines.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hermes_studio.plan import ClipPlan
from hermes_studio.transcribe import Transcript, Word


def words_from_lines(lines: list, duration: float) -> list[Word]:
    """Turn agent lines into timed words. A line is a string or {text, start, end}."""
    if not lines:
        return []
    parsed: list[tuple[float, float, str]] = []
    bare: list[str] = []
    for item in lines:
        if isinstance(item, str) and item.strip():
            bare.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("line") or "").strip()
        if not text:
            continue
        start = item.get("start")
        end = item.get("end")
        if start is None or end is None:
            bare.append(text)
            continue
        parsed.append((float(start), float(end), text))
    if bare and not parsed:
        span = max(float(duration) - 0.4, 0.8)
        step = span / len(bare)
        for i, text in enumerate(bare):
            parsed.append((0.2 + i * step, 0.2 + (i + 1) * step, text))
    words: list[Word] = []
    for start, end, text in parsed:
        if end <= start:
            end = start + 0.4
        parts = text.split()
        if not parts:
            continue
        step = (end - start) / len(parts)
        for i, part in enumerate(parts):
            words.append(Word(part, round(start + i * step, 3), round(start + (i + 1) * step, 3)))
    return words


def load_cues(path: str | Path) -> tuple[list, str]:
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, ""
    if isinstance(data, dict):
        return list(data.get("lines") or []), str(data.get("hook") or "")
    raise ValueError("cues must be a list of lines or {lines, hook}")


def _has_audio(video: Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video)],
        capture_output=True,
        text=True,
    )
    return "audio" in (out.stdout or "")


def _with_audio(video: Path, work: Path) -> Path:
    if _has_audio(video):
        return video
    dest = work / "with-audio.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-shortest", "-c:v", "copy", "-c:a", "aac", str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def burn(src: Path, lines: list, dest: Path, work: Path, *, style: str = "pop", layout: str = "fit",
         width: int = 1080, height: int = 1920, hook: str = "") -> Path:
    from hermes_studio.render import probe_duration, render_clip

    work.mkdir(parents=True, exist_ok=True)
    video = _with_audio(src, work)
    dur = probe_duration(video)
    words = words_from_lines(lines, dur)
    if not words:
        raise ValueError("the agent must pass caption lines")
    tr = Transcript("agent", dur, " ".join(w.text for w in words), words)
    title = hook or words[0].text
    plan = ClipPlan(0.0, dur, title[:60], [], 1.0)
    render_clip(
        video, plan, tr, dest, work,
        width=width, height=height, pacing="natural", style=style, layout=layout, hook=hook or title[:40],
    )
    return dest
