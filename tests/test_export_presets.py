"""M5 export presets: validation and the preset table (no ffmpeg)."""

import pytest

from hermes_studio.export_presets import (
    PRESETS,
    ExportPresetError,
    default_filename,
    list_presets,
    resolve,
)


def test_every_preset_has_even_dimensions_and_an_extension():
    for p in PRESETS.values():
        assert p.width % 2 == 0 and p.height % 2 == 0
        assert p.extension in ("mp4", "mov")
        assert p.id in PRESETS


def test_list_presets_matches_the_table():
    rows = {r["id"]: r for r in list_presets()}
    assert set(rows) == set(PRESETS)
    assert rows["prores"]["video_codec"] == "prores_ks"
    assert rows["1080p"]["width"] == 1920


def test_resolve_quality_tiers_for_x264():
    r = resolve("1080p", quality="draft")
    assert r.crf == 28 and r.x264_preset == "veryfast"
    r = resolve("4k", quality="high")
    assert r.crf == 18 and r.x264_preset == "slow"


def test_prores_ignores_crf():
    r = resolve("prores", quality="high")
    assert r.crf is None and r.x264_preset is None


def test_unknown_preset_and_quality_are_refused():
    with pytest.raises(ExportPresetError):
        resolve("8k")
    with pytest.raises(ExportPresetError):
        resolve("1080p", quality="ultra")


def test_fps_bounds():
    with pytest.raises(ExportPresetError):
        resolve("1080p", fps=0)
    assert resolve("1080p", fps=30).fps == 30.0


def test_legacy_export_without_preset():
    r = resolve(None)
    assert r.preset is None
    assert default_filename("demo", r) == "demo-render.mp4"


def test_default_filename_includes_preset():
    r = resolve("vertical")
    assert default_filename("p1", r) == "p1-vertical.mp4"
    r = resolve("prores")
    assert default_filename("p1", r) == "p1-prores.mov"
