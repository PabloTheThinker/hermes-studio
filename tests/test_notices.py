"""NOTICE and the license texts must match what the desktop app ships, and must ship.

The app bundles FFmpeg (GPL) and PyAV/OpenCV wheels that carry FFmpeg libraries.
These checks fail when a pin changes without NOTICE, or when packaging drops the files.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
DESKTOP_YML = (ROOT / ".github/workflows/desktop.yml").read_text(encoding="utf-8")
SHIPPED = ["NOTICE", "LICENSE", "licenses"]
LICENSE_TEXTS = {
    "FFmpeg-GPL.txt": "GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007",
    "LGPL-3.0.txt": "GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007",
    "LGPL-2.1.txt": "GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 2.1, February 1999",
}


def workflow_env(name: str) -> str:
    m = re.search(rf"^\s+{name}:\s*(\S+)\s*$", DESKTOP_YML, re.M)
    assert m, f"{name} missing from desktop.yml"
    return m.group(1)


@pytest.mark.parametrize("platform", ["WIN", "LINUX"])
def test_notice_names_the_pinned_ffmpeg_download(platform):
    url = workflow_env(f"FFMPEG_{platform}_URL")
    sha = workflow_env(f"FFMPEG_{platform}_SHA256")
    assert url in NOTICE, "FFMPEG_*_URL changed: update the FFmpeg section of NOTICE"
    assert sha in NOTICE, "FFMPEG_*_SHA256 changed: update the FFmpeg section of NOTICE"
    tag = url.split("/")[7]
    build = re.search(r"ffmpeg-(n[\w.]+-\d+-g[0-9a-f]+)-", url).group(1)
    assert f"Release:         {tag}" in NOTICE
    assert f"releases/tag/{tag}" in NOTICE and f"tree/{tag}" in NOTICE
    assert f"Version string:  {build}" in NOTICE


def test_notice_links_the_exact_ffmpeg_commit():
    url = workflow_env("FFMPEG_LINUX_URL")
    short = re.search(r"-g([0-9a-f]+)-", url).group(1)
    commits = re.findall(r"FFmpeg/FFmpeg/(?:commit|archive)/([0-9a-f]{40})", NOTICE)
    assert commits, "NOTICE must link FFmpeg source by full commit, not just the tag"
    assert all(c.startswith(short) for c in commits), f"NOTICE commit is not g{short}"
    assert "GPL-3.0-or-later" in NOTICE and "separate programs" in NOTICE


def test_notice_names_the_pinned_wheels():
    pins = dict(
        line.split("==")
        for line in (ROOT / "packaging/engine-constraints.txt").read_text().splitlines()
        if "==" in line and not line.startswith("#")
    )
    assert set(pins) == {"av", "opencv-python-headless"}
    assert f"PyAV {pins['av']} (BSD-3-Clause)" in NOTICE
    assert f"PyAV-Org/PyAV/tree/v{pins['av']}" in NOTICE
    assert f"opencv-python-headless {pins['opencv-python-headless']}" in NOTICE
    assert "libx264 and libx265" in NOTICE  # the GPL parts of the PyAV wheel


@pytest.mark.parametrize("name,header", LICENSE_TEXTS.items())
def test_license_texts_are_complete(name, header):
    text = (ROOT / "licenses" / name).read_text(encoding="utf-8")
    assert header in text
    assert len(text) > 7000, f"{name} looks truncated"
    assert name in NOTICE or name in (ROOT / "licenses/README.md").read_text()


@pytest.mark.parametrize("platform", ["linux", "win", "mac"])
def test_app_resources_carry_notice_and_licenses(platform):
    cfg = json.loads((ROOT / "electron-builder.json").read_text())
    extra = {(e["from"], e["to"]) for e in cfg[platform]["extraResources"]}
    for f in SHIPPED:
        assert (f, f) in extra, f"electron-builder {platform}.extraResources must ship {f}"


@pytest.mark.parametrize(
    "script,needles",
    [
        (
            "scripts/build-engine-linux.sh",
            ['cp "$ROOT/NOTICE" "$ROOT/LICENSE" "$OUT/"', 'cp -r "$ROOT/licenses" "$OUT/licenses"'],
        ),
        (
            "scripts/build-engine-windows.ps1",
            ['Copy-Item "$Root\\NOTICE", "$Root\\LICENSE" "$Out\\"', 'Copy-Item -Recurse "$Root\\licenses" "$Out\\licenses"'],
        ),
    ],
)
def test_engine_build_copies_notices_and_pins_wheels(script, needles):
    text = (ROOT / script).read_text(encoding="utf-8")
    for n in needles + ["engine-constraints.txt", "NOTICE does not name"]:
        assert n in text, f"{script} lost: {n}"


def test_release_attaches_source():
    assert "git -C .. archive" in DESKTOP_YML
    assert '"${src[@]}" SHA256SUMS.txt' in DESKTOP_YML


def test_versions_agree():
    want = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    found = {
        "package.json": json.loads((ROOT / "package.json").read_text())["version"],
        "hermes_studio/__init__.py": re.search(
            r'__version__ = "([^"]+)"', (ROOT / "hermes_studio/__init__.py").read_text()
        ).group(1),
        "plugin.yaml": re.search(
            r"^version:\s*\"?([\w.]+)", (ROOT / "hermes_plugin/hermes-studio/plugin.yaml").read_text(), re.M
        ).group(1),
        "plugin __init__.py": re.search(
            r'__plugin_version__ = "([^"]+)"', (ROOT / "hermes_plugin/hermes-studio/__init__.py").read_text()
        ).group(1),
    }
    assert found == dict.fromkeys(found, want)
    assert (ROOT / f"docs/releases/v{want}.md").exists()
