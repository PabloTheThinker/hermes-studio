"""Smoke tests for the Studio tool catalogue and transcript exports (no media needed)."""
from pathlib import Path

from hermes_studio import tools
from hermes_studio.export import _stamp, write_exports
from hermes_studio.pipeline import MODES
from hermes_studio.transcribe import Transcript, Word


def test_catalogue_matches_pipeline_modes():
    ids = [t["id"] for t in tools.catalogue()["tools"]]
    assert ids == list(MODES)


def test_quality_presets():
    q = [p["id"] for p in tools.catalogue()["quality"]]
    assert q == ["fast", "balanced", "accurate"]


def test_srt_timestamp():
    assert _stamp(3723.456, ",") == "01:02:03,456"
    assert _stamp(3723.456, ".") == "01:02:03.456"


def test_exports(tmp_path: Path):
    words = [Word(text=w, start=i * 0.5, end=i * 0.5 + 0.4) for i, w in enumerate("Hello there. This is a test.".split())]
    tr = Transcript(language="en", duration=3.0, text=" ".join(w.text for w in words), words=words)
    files = write_exports(tr, tmp_path)
    names = sorted(f["file"] for f in files)
    assert names == ["transcript.srt", "transcript.txt", "transcript.vtt"]
    assert (tmp_path / "transcript.vtt").read_text().startswith("WEBVTT")
    assert "Hello there." in (tmp_path / "transcript.txt").read_text()
