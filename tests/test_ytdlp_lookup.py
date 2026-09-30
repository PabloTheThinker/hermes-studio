"""yt-dlp is found the same way on every system."""

import sys

from hermesclip import download


def test_ytdlp_prefers_own_interpreter_when_importable(monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "yt_dlp" else None)
    assert download._ytdlp() == [sys.executable, "-m", "yt_dlp"]


def test_ytdlp_falls_back_to_path(monkeypatch, tmp_path):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(download.sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(download.shutil, "which", lambda name: "/opt/bin/yt-dlp" if name == "yt-dlp" else None)
    assert download._ytdlp() == ["/opt/bin/yt-dlp"]


def test_ytdlp_finds_windows_sibling(monkeypatch, tmp_path):
    import importlib.util

    (tmp_path / "yt-dlp.exe").write_bytes(b"")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(download.sys, "executable", str(tmp_path / "python.exe"))
    assert download._ytdlp() == [str(tmp_path / "yt-dlp.exe")]
