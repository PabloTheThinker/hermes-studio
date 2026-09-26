"""Hermes Studio tool catalogue: one source of truth for the desk, the site and agents.

Each tool is a job mode with its own defaults and which settings it exposes.
Research basis (2026): Opus Clip / Vizard / Klap (clip + reframe + score),
Submagic (captions, silence removal), Descript (filler cut, transcript export).
HermesClip keeps all of it local and never posts.
"""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "id": "clip",
        "name": "Clips",
        "verb": "Find the moments",
        "line": "Long video in. Hook-first shorts out, scored and captioned.",
        "input": "Any long video, stream or link",
        "output": "3–8 short clips",
        "defaults": {"aspect": "9:16", "layout": "fit", "captions": True, "hook": True, "pacing": "tight"},
        "settings": ["hunt", "range", "format", "length", "captions"],
        "status": "Live",
    },
    {
        "id": "captions",
        "name": "Captions",
        "verb": "Caption the whole take",
        "line": "Word-by-word captions burned onto the full video. No cutting.",
        "input": "A finished short or a full take",
        "output": "1 captioned video",
        "defaults": {"aspect": "9:16", "layout": "fit", "captions": True, "hook": False, "pacing": "natural"},
        "settings": ["range", "format", "captions"],
        "status": "Live",
    },
    {
        "id": "reframe",
        "name": "Reframe",
        "verb": "Change the shape",
        "line": "Turn a 16:9 video into 9:16, 4:5 or 1:1. Blur pad or punch-in on the speaker.",
        "input": "Any video",
        "output": "1 reshaped video",
        "defaults": {"aspect": "9:16", "layout": "fill", "captions": False, "hook": False, "pacing": "natural"},
        "settings": ["range", "format", "captions"],
        "status": "Live",
    },
    {
        "id": "tighten",
        "name": "Tighten",
        "verb": "Cut the dead air",
        "line": "Drops ums, uhs and long pauses on real word timings. Keeps your frame.",
        "input": "A talking-head take",
        "output": "1 tighter video",
        "defaults": {"aspect": "source", "layout": "fit", "captions": False, "hook": False, "pacing": "tight"},
        "settings": ["range", "format", "captions"],
        "status": "Live",
    },
    {
        "id": "transcript",
        "name": "Transcript",
        "verb": "Get the words",
        "line": "Local Whisper to SRT, VTT and plain text. Nothing is rendered.",
        "input": "Any video or stream",
        "output": ".srt · .vtt · .txt",
        "defaults": {"captions": False, "hook": False},
        "settings": ["range", "quality"],
        "status": "Live",
    },
]

QUALITY = [
    {"id": "fast", "name": "Fast", "model": "tiny", "line": "Quickest. Fine for clean speech."},
    {"id": "balanced", "name": "Balanced", "model": "base.en", "line": "Better on accents and noise."},
    {"id": "accurate", "name": "Accurate", "model": "small.en", "line": "Best words. Slowest on CPU."},
]

LATER = [
    {"name": "Editor", "line": "Timeline under the Studio name. Not shipping yet."},
]


def catalogue() -> dict:
    return {"tools": TOOLS, "quality": QUALITY, "later": LATER}


def tool(tool_id: str) -> dict | None:
    return next((t for t in TOOLS if t["id"] == tool_id), None)
