"""Edit-page export presets: resolution, codec, container, and x264 quality tiers.

Pure data and validation — no ffmpeg. Timeline ``apply_preset`` lives in ``presets.py``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PRESET_IDS = ("1080p", "4k", "vertical", "prores")
QUALITY_TIERS = ("draft", "standard", "high")

X264_QUALITY = {
    "draft": {"crf": 28, "preset": "veryfast"},
    "standard": {"crf": 20, "preset": "medium"},
    "high": {"crf": 18, "preset": "slow"},
}

MIN_FPS = 1.0
MAX_FPS = 120.0


@dataclass(frozen=True)
class ExportPreset:
    id: str
    label: str
    width: int
    height: int
    extension: str
    video_codec: str  # libx264 | prores_ks
    pix_fmt: str
    audio_codec: str  # aac | pcm_s16le
    prores_profile: int | None = None  # ffmpeg profile:v for prores_ks
    movflags: bool = True


PRESETS: dict[str, ExportPreset] = {
    "1080p": ExportPreset(
        "1080p",
        "1080p H.264",
        1920,
        1080,
        "mp4",
        "libx264",
        "yuv420p",
        "aac",
    ),
    "4k": ExportPreset(
        "4k",
        "4K H.264",
        3840,
        2160,
        "mp4",
        "libx264",
        "yuv420p",
        "aac",
    ),
    "vertical": ExportPreset(
        "vertical",
        "1080p vertical",
        1080,
        1920,
        "mp4",
        "libx264",
        "yuv420p",
        "aac",
    ),
    "prores": ExportPreset(
        "prores",
        "ProRes 422 HQ",
        1920,
        1080,
        "mov",
        "prores_ks",
        "yuv422p10le",
        "pcm_s16le",
        prores_profile=3,
        movflags=False,
    ),
}


class ExportPresetError(ValueError):
    pass


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "width": p.width,
            "height": p.height,
            "extension": p.extension,
            "video_codec": p.video_codec,
            "audio_codec": p.audio_codec,
        }
        for p in PRESETS.values()
    ]


def _norm_preset(name: str | None) -> str | None:
    if name is None or name == "":
        return None
    key = str(name).strip().lower()
    aliases = {"1080": "1080p", "4K": "4k", "2160p": "4k", "vertical1080": "vertical"}
    key = aliases.get(key, key)
    if key not in PRESETS:
        raise ExportPresetError(f"unknown preset '{name}' (choose: {', '.join(PRESET_IDS)})")
    return key


def _norm_quality(tier: str | None) -> str:
    if tier is None or tier == "":
        return "standard"
    key = str(tier).strip().lower()
    if key not in QUALITY_TIERS:
        raise ExportPresetError(f"unknown quality '{tier}' (choose: {', '.join(QUALITY_TIERS)})")
    return key


def _norm_fps(fps: float | int | None) -> float | None:
    if fps is None:
        return None
    try:
        v = float(fps)
    except (TypeError, ValueError) as exc:
        raise ExportPresetError("fps must be a number") from exc
    if not (MIN_FPS <= v <= MAX_FPS):
        raise ExportPresetError(f"fps must be between {MIN_FPS:g} and {MAX_FPS:g}")
    return v


@dataclass(frozen=True)
class ResolvedExport:
    preset: ExportPreset | None
    quality: str
    fps: float | None
    crf: int | None
    x264_preset: str | None


def resolve(
    preset: str | None = None,
    *,
    quality: str | None = "standard",
    fps: float | int | None = None,
) -> ResolvedExport:
    """Validate preset / quality / fps. ``preset=None`` keeps the timeline canvas size and default x264."""
    pid = _norm_preset(preset)
    q = _norm_quality(quality)
    f = _norm_fps(fps)
    p = PRESETS[pid] if pid else None
    if p and p.video_codec == "libx264":
        tier = X264_QUALITY[q]
        return ResolvedExport(p, q, f, tier["crf"], tier["preset"])
    return ResolvedExport(p, q, f, None, None)


def default_filename(project_id: str, resolved: ResolvedExport) -> str:
    if resolved.preset:
        return f"{project_id}-{resolved.preset.id}.{resolved.preset.extension}"
    return f"{project_id}-render.mp4"
